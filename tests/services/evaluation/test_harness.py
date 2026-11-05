from typing import Self

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.domain import TargetVariable
from app.services.evaluation import (
    Baseline,
    BaselineForecaster,
    EvaluationHarness,
    EvaluationSettings,
    ForecastTask,
)
from app.services.features import TargetArm, TargetTransformer

REVENUE = TargetVariable.REVENUE
TASK = ForecastTask(variable=REVENUE, arm=TargetArm.LOG_DIFF4, horizon=1)
N_ORIGINS = 4
QUARTERS = pd.date_range("2020-03-31", periods=20, freq="QE")
SEASON = np.tile([1.0, 1.2, 1.1, 1.3], 5)


class SpyForecaster:
    """Predicts zero change and remembers the columns it was shown."""

    def __init__(self) -> None:
        self.columns_seen: set[str] = set()

    def fit(self, _train: pd.DataFrame, /) -> Self:
        return self

    def predict(self, test: pd.DataFrame, /) -> pd.DataFrame:
        self.columns_seen |= set(test.columns)
        return pd.DataFrame({"y_hat": 0.0}, index=test.index)


class SilentOnOneCompany:
    """Predicts zero change, except for one company it leaves missing."""

    def __init__(self, ticker: str) -> None:
        self._ticker = ticker

    def fit(self, _train: pd.DataFrame, /) -> Self:
        return self

    def predict(self, test: pd.DataFrame, /) -> pd.DataFrame:
        silent = test["ticker"] == self._ticker
        return pd.DataFrame({"y_hat": np.where(silent, np.nan, 0.0)}, index=test.index)


@pytest.fixture
def panels() -> dict[str, pd.DataFrame]:
    # Steady year-over-year growth plus 1 % noise: seasonal naive with growth
    # beats seasonal naive, which misses the whole year's growth.
    rng = np.random.default_rng(0)
    return {
        ticker: pd.DataFrame({
            "ticker": ticker,
            "sector": sector,
            "date": QUARTERS,
            REVENUE: 100.0
            * SEASON
            * growth ** (np.arange(len(QUARTERS)) / 4)
            * np.exp(rng.normal(0.0, 0.01, len(QUARTERS))),
        })
        for ticker, sector, growth in (
            ("AAA", "Technology", 1.10),
            ("BBB", "Energy", 1.05),
        )
    }


@pytest.fixture
def dataset(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    transformer = TargetTransformer(arm=TASK.arm, horizon=TASK.horizon)
    return pd.concat(
        [
            pd.DataFrame({
                "ticker": panel["ticker"],
                "origin_date": panel["date"],
                "target_date": panel["date"] + pd.offsets.QuarterEnd(TASK.horizon),
                "growth_yoy_lag1": panel[REVENUE].pct_change(4),
                "target_level": panel[REVENUE].shift(-TASK.horizon),
                "y": transformer.make(panel[REVENUE]),
            })
            for panel in panels.values()
        ],
        ignore_index=True,
    )


@pytest.fixture
def harness() -> EvaluationHarness:
    return EvaluationHarness(settings=EvaluationSettings(n_origins=N_ORIGINS))


def test_every_company_is_scored_at_each_of_the_last_labelled_origins(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    scored = evaluation.scored
    assert len(scored) == len(panels) * N_ORIGINS
    # The last origin with a known target is the one before the last quarter.
    assert sorted(scored["origin_date"].unique()) == list(QUARTERS[-5:-1])
    assert (scored["target_date"] > scored["origin_date"]).all()
    assert scored["mase_scale"].notna().all()


def test_the_forecaster_never_sees_a_test_label(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    spy = SpyForecaster()

    harness.evaluate(spy, dataset, panels=panels, task=TASK)

    assert "growth_yoy_lag1" in spy.columns_seen
    assert not spy.columns_seen & {"y", "target_level"}


def test_the_baseline_to_beat_is_the_seasonal_baseline_with_the_lower_mae(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    assert evaluation.baseline_to_beat is Baseline.SEASONAL_NAIVE_GROWTH


def test_the_baseline_to_beat_has_zero_out_of_sample_r2(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    forecaster = BaselineForecaster(
        Baseline.SEASONAL_NAIVE_GROWTH,
        panels=panels,
        variable=TASK.variable,
        arm=TASK.arm,
        horizon=TASK.horizon,
    )

    evaluation = harness.evaluate(forecaster, dataset, panels=panels, task=TASK)

    np.testing.assert_allclose(
        evaluation.scored["y_hat_scaled"], evaluation.scored["baseline_scaled"]
    )
    assert evaluation.metrics.pooled["oos_r2"][0] == pytest.approx(0.0, abs=1e-9)


def test_missing_predictions_are_counted_not_dropped(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(
        SilentOnOneCompany("BBB"), dataset, panels=panels, task=TASK
    )

    pooled = evaluation.metrics.pooled
    assert pooled["rows"][0] == len(panels) * N_ORIGINS
    assert pooled["missing"][0] == N_ORIGINS
    assert pooled["mae"].isna()[0]
    by_company = evaluation.metrics.by_company.set_index("ticker")
    assert by_company["mae"].notna()["AAA"]
    assert by_company["mae"].isna()["BBB"]


def test_a_task_refuses_an_arm_its_variable_cannot_use() -> None:
    with pytest.raises(ValidationError, match="cannot be forecast in the"):
        ForecastTask(variable=TargetVariable.EBITDA, arm=TargetArm.LOG_DIFF4, horizon=1)

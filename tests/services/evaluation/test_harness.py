from typing import Self, override

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.domain import Forecaster, TargetVariable
from app.services.evaluation import (
    Baseline,
    BaselineForecaster,
    EvaluationHarness,
    EvaluationSettings,
    ForecastTask,
    RunProvenance,
)
from app.services.features import TargetArm, TargetTransformer

REVENUE = TargetVariable.REVENUE
TASK = ForecastTask(variable=REVENUE, arm=TargetArm.LOG_DIFF4, horizon=1)
N_ORIGINS = 4
# Protocol B's histories: the settings' four, then all of it.
HISTORIES = (8, 12, 20, 40, None)
KEYS = ["ticker", "origin_date"]
# Two companies give 20 errors per calibration window: enough for a finite
# quantile at these levels, not at 0.95.
LEVELS = (0.5, 0.8)
QUARTERS = pd.date_range("2020-03-31", periods=20, freq="QE")
SEASON = np.tile([1.0, 1.2, 1.1, 1.3], 5)


class SpyForecaster(Forecaster):
    """Predicts zero change and remembers the columns it was shown."""

    def __init__(self) -> None:
        self.columns_seen: set[str] = set()

    @override
    def fit(self, _train: pd.DataFrame, /) -> Self:
        return self

    @override
    def predict(
        self, test: pd.DataFrame, /, *, history: int | None = None
    ) -> pd.DataFrame:
        self.columns_seen |= set(test.columns)
        return pd.DataFrame({"y_hat": 0.0}, index=test.index)


class RecordingForecaster(Forecaster):
    """Predicts zero change and keeps every frame it was fit on or shown."""

    def __init__(self) -> None:
        self.trained: list[pd.DataFrame] = []
        self.shown: list[pd.DataFrame] = []

    @override
    def fit(self, train: pd.DataFrame, /) -> Self:
        self.trained.append(train)
        return self

    @override
    def predict(
        self, test: pd.DataFrame, /, *, history: int | None = None
    ) -> pd.DataFrame:
        self.shown.append(test)
        return pd.DataFrame({"y_hat": 0.0}, index=test.index)


class SilentOnOneCompany(Forecaster):
    """Predicts zero change, except for one company it leaves missing."""

    def __init__(self, ticker: str) -> None:
        self._ticker = ticker

    @override
    def fit(self, _train: pd.DataFrame, /) -> Self:
        return self

    @override
    def predict(
        self, test: pd.DataFrame, /, *, history: int | None = None
    ) -> pd.DataFrame:
        silent = test["ticker"] == self._ticker
        return pd.DataFrame({"y_hat": np.where(silent, np.nan, 0.0)}, index=test.index)


@pytest.fixture
def panels(request: pytest.FixtureRequest) -> dict[str, pd.DataFrame]:
    # Steady year-over-year growth plus 1 % noise: seasonal naive with growth
    # beats seasonal naive, which misses the whole year's growth.
    season = getattr(request, "param", SEASON)
    rng = np.random.default_rng(0)
    return {
        ticker: pd.DataFrame({
            "ticker": ticker,
            "sector": sector,
            "date": QUARTERS,
            REVENUE: 100.0
            * season
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
    return _features(panels)


def _features(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
    return EvaluationHarness(
        settings=EvaluationSettings(
            n_origins=N_ORIGINS, calibration_window=10, interval_levels=LEVELS
        )
    )


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
    assert evaluation.significance.origins == N_ORIGINS


def test_the_forecaster_never_sees_a_test_label(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    spy = SpyForecaster()

    harness.evaluate(spy, dataset, panels=panels, task=TASK)

    assert "growth_yoy_lag1" in spy.columns_seen
    assert not spy.columns_seen & {"y", "target_level"}


def test_the_baseline_to_beat_is_the_baseline_with_the_lowest_mae(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    assert evaluation.baseline_to_beat is Baseline.SEASONAL_NAIVE_GROWTH


@pytest.mark.parametrize("panels", [np.ones(len(QUARTERS))], indirect=True)
def test_a_non_seasonal_baseline_can_be_the_one_to_beat(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    # Without seasonality, last quarter is fresher than the same quarter a year ago.
    assert evaluation.baseline_to_beat in {Baseline.NAIVE, Baseline.DRIFT}


def test_the_baseline_to_beat_has_zero_out_of_sample_r2(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    forecaster = BaselineForecaster(
        Baseline.SEASONAL_NAIVE_GROWTH, panels=panels, task=TASK
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


def test_every_scored_row_becomes_a_record_with_its_provenance(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    provenance = RunProvenance(
        harness_version="nb02-v0.1.0",
        data_freeze="thesis_2026-10-30-0123456789ab",
        git_commit="0" * 40,
    )
    evaluation = harness.evaluate(
        SilentOnOneCompany("BBB"), dataset, panels=panels, task=TASK
    )

    records = evaluation.records(model="silent", provenance=provenance)

    assert len(records) == len(evaluation.scored) * len(LEVELS)
    assert set(records["git_commit"]) == {"0" * 40}
    assert set(records["arm"]) == {TASK.arm.value}
    assert set(records["level"]) == set(LEVELS)
    silent = records[records["ticker"] == "BBB"]
    assert silent[["y_hat_scaled", "lower_scaled", "upper_scaled"]].isna().all().all()


def test_every_scored_row_has_an_ordered_finite_interval_at_each_level(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    intervals = evaluation.intervals
    assert len(intervals) == len(evaluation.scored) * len(LEVELS)
    # The calibration origins are refit but never reported.
    assert set(intervals["origin_date"]) == set(evaluation.scored["origin_date"])
    bounds = intervals[["lower_scaled", "upper_scaled"]]
    assert np.isfinite(bounds.to_numpy()).all()
    assert (intervals["lower_scaled"] <= intervals["upper_scaled"]).all()


def test_the_intervals_are_scored_at_each_level_pooled_and_by_sector(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    pooled = evaluation.interval_metrics.pooled
    assert list(pooled["level"]) == list(LEVELS)
    assert (pooled["rows"] == len(evaluation.scored)).all()
    assert pooled["coverage"].between(0.0, 1.0).all()
    assert (pooled["mean_winkler_score"] >= pooled["mean_width"]).all()
    assert set(evaluation.interval_metrics.by_sector["sector"]) == {
        "Technology",
        "Energy",
    }


def test_a_higher_level_is_never_narrower(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    width = evaluation.intervals.assign(
        width=lambda f: f["upper_scaled"] - f["lower_scaled"]
    ).pivot_table(index=["ticker", "origin_date"], columns="level", values="width")
    assert (width[LEVELS[1]] >= width[LEVELS[0]]).all()


def test_each_company_s_interval_scales_with_its_own_errors(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluation = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    intervals = evaluation.intervals.merge(
        evaluation.scored[["ticker", "origin_date", "mase_scale"]]
    )
    width = intervals["upper_scaled"] - intervals["lower_scaled"]
    # AAA grows twice as fast, so its errors and its interval are wider than BBB's.
    relative = (width / intervals["mase_scale"]).groupby([
        intervals["origin_date"],
        intervals["level"],
    ])
    np.testing.assert_allclose(relative.max(), relative.min())
    assert (
        width[intervals["ticker"] == "AAA"].mean()
        > width[intervals["ticker"] == "BBB"].mean()
    )


def test_protocol_b_scores_every_company_at_each_history(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluations = harness.evaluate_new_companies(
        SpyForecaster(), dataset, panels=panels, task=TASK
    )

    assert [evaluation.history for evaluation in evaluations] == list(HISTORIES)
    for evaluation in evaluations:
        assert evaluation.protocol == "B"
        assert len(evaluation.scored) == len(panels) * N_ORIGINS
        assert len(evaluation.intervals) == len(evaluation.scored) * len(LEVELS)
        bounds = evaluation.intervals
        assert (bounds["lower_scaled"] <= bounds["upper_scaled"]).all()


def test_a_new_company_is_never_in_the_rows_its_model_trained_on(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    forecaster = RecordingForecaster()

    harness.evaluate_new_companies(forecaster, dataset, panels=panels, task=TASK)

    # One fit per company and origin serves every history.
    assert len(forecaster.shown) == len(forecaster.trained) * len(HISTORIES)
    for call, test in enumerate(forecaster.shown):
        train = forecaster.trained[call // len(HISTORIES)]
        assert not set(train["ticker"]) & set(test["ticker"])


def test_protocol_b_models_never_see_the_seasonality_regime(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    forecaster = RecordingForecaster()

    harness.evaluate_new_companies(
        forecaster, dataset.assign(seasonality_regime=0), panels=panels, task=TASK
    )

    frames = forecaster.trained + forecaster.shown
    assert not any("seasonality_regime" in frame.columns for frame in frames)


def test_only_eight_quarters_of_history_blank_the_eighth_growth_lag(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    forecaster = RecordingForecaster()

    harness.evaluate_new_companies(
        forecaster, dataset.assign(growth_yoy_lag8=0.1), panels=panels, task=TASK
    )

    blank = [bool(test["growth_yoy_lag8"].isna().all()) for test in forecaster.shown]
    fits = len(forecaster.trained)
    assert blank == [True, False, False, False, False] * fits


def test_with_all_its_history_a_new_company_gets_protocol_a_s_forecasts(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    protocol_a = harness.evaluate(SpyForecaster(), dataset, panels=panels, task=TASK)

    all_history = harness.evaluate_new_companies(
        SpyForecaster(), dataset, panels=panels, task=TASK
    )[-1]

    # Only the error scale differs: Protocol B blends it with the peers'.
    pd.testing.assert_frame_equal(
        all_history.scored.drop(columns="mase_scale").sort_values(
            KEYS, ignore_index=True
        ),
        protocol_a.scored.drop(columns="mase_scale").sort_values(
            KEYS, ignore_index=True
        ),
    )


def test_a_new_company_s_drift_runs_only_over_the_history_it_has(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    drift = BaselineForecaster(Baseline.DRIFT, panels=panels, task=TASK)

    evaluations = harness.evaluate_new_companies(
        drift, dataset, panels=panels, task=TASK
    )

    eight_quarters, all_history = (
        evaluations[index].scored.sort_values(KEYS, ignore_index=True)
        for index in (0, -1)
    )
    assert eight_quarters["y_hat_scaled"].notna().all()
    assert not np.allclose(eight_quarters["y_hat_scaled"], all_history["y_hat_scaled"])


def test_a_short_history_changes_the_error_scale(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    evaluations = harness.evaluate_new_companies(
        SpyForecaster(), dataset, panels=panels, task=TASK
    )

    eight_quarters, all_history = evaluations[0].scored, evaluations[-1].scored
    assert eight_quarters["mase_scale"].notna().all()
    assert not np.allclose(eight_quarters["mase_scale"], all_history["mase_scale"])


def test_a_short_history_interval_leans_on_its_peers_error_size(
    dataset: pd.DataFrame, panels: dict[str, pd.DataFrame]
) -> None:
    def eight_quarter_widths(prior_errors: int) -> pd.Series:
        harness = EvaluationHarness(
            settings=EvaluationSettings(
                n_origins=N_ORIGINS,
                calibration_window=10,
                interval_levels=LEVELS,
                scale_prior_errors=prior_errors,
            )
        )
        intervals = harness.evaluate_new_companies(
            SpyForecaster(), dataset, panels=panels, task=TASK
        )[0].intervals
        return intervals["upper_scaled"] - intervals["lower_scaled"]

    assert not np.allclose(eight_quarter_widths(0), eight_quarter_widths(10_000))


def test_protocol_b_records_carry_their_protocol_and_history(
    harness: EvaluationHarness,
    dataset: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
) -> None:
    provenance = RunProvenance(
        harness_version="nb02-v0.1.0",
        data_freeze="thesis_2026-10-30-0123456789ab",
        git_commit="0" * 40,
    )
    evaluations = harness.evaluate_new_companies(
        SpyForecaster(), dataset, panels=panels, task=TASK
    )

    eight_quarters = evaluations[0].records(model="zero", provenance=provenance)
    all_history = evaluations[-1].records(model="zero", provenance=provenance)

    assert set(eight_quarters["protocol"]) == {"B"}
    assert set(eight_quarters["history"]) == {HISTORIES[0]}
    assert all_history["history"].isna().all()


def test_a_company_with_a_zero_error_scale_does_not_break_the_others(
    harness: EvaluationHarness, panels: dict[str, pd.DataFrame]
) -> None:
    # Revenue that never changes: every seasonal-naive error, and so the
    # company's scale, is exactly zero.
    flat = {**panels, "BBB": panels["BBB"].assign(**{REVENUE: 100.0})}

    evaluation = harness.evaluate(
        SpyForecaster(), _features(flat), panels=flat, task=TASK
    )

    assert (evaluation.scored.set_index("ticker")["mase_scale"]["BBB"] == 0).all()
    assert np.isfinite(evaluation.metrics.pooled["mase"][0])
    # BBB's errors do not calibrate, so AAA's 10 may leave an interval
    # unbounded; none is left without bounds.
    other = evaluation.intervals[evaluation.intervals["ticker"] == "AAA"]
    assert other[["lower_scaled", "upper_scaled"]].notna().all().all()


def test_a_task_refuses_an_arm_its_variable_cannot_use() -> None:
    with pytest.raises(ValidationError, match="cannot be forecast in the"):
        ForecastTask(variable=TargetVariable.EBITDA, arm=TargetArm.LOG_DIFF4, horizon=1)

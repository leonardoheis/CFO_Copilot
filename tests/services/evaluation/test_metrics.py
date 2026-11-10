import numpy as np
import pandas as pd
import pytest

from app.domain import TargetVariable
from app.services.evaluation import (
    UndefinedMetricError,
    in_sample_scale,
    interval_metric_tables,
    interval_metrics,
    mape,
    point_metric_tables,
    point_metrics,
    winkler_score,
)


@pytest.fixture
def scored() -> pd.DataFrame:
    # Errors 0.1, -0.2, 0.3, 0.0; baseline errors 0.2, 0.0, 0.0, -0.5.
    return pd.DataFrame({
        "ticker": ["AAA", "AAA", "BBB", "BBB"],
        "sector": ["Technology", "Technology", "Energy", "Energy"],
        "y_scaled": [1.0, 2.0, 0.0, 1.0],
        "y_hat_scaled": [1.1, 1.8, 0.3, 1.0],
        "baseline_scaled": [1.2, 2.0, 0.0, 0.5],
        "mase_scale": [0.2, 0.2, 0.1, 0.1],
        "y_level": [100.0, 200.0, 50.0, 100.0],
        "y_hat_level": [110.0, 180.0, 60.0, 100.0],
    })


@pytest.fixture
def intervals() -> pd.DataFrame:
    # The interval [-1, 1] at both levels: y inside, 1 above, 2 below, inside.
    return pd.DataFrame({
        "sector": ["Technology", "Technology", "Energy", "Energy"] * 2,
        "level": [0.8] * 4 + [0.9] * 4,
        "y_scaled": [0.0, 2.0, -3.0, 0.5] * 2,
        "lower_scaled": -1.0,
        "upper_scaled": 1.0,
    })


def test_pooled_metrics_match_hand_computed_values(scored: pd.DataFrame) -> None:
    pooled = point_metrics(scored, variable=TargetVariable.REVENUE).iloc[0]

    assert pooled["rows"] == len(scored)
    assert pooled["missing"] == 0
    assert pooled["mae"] == pytest.approx(0.15)
    assert pooled["rmse"] == pytest.approx(np.sqrt(0.14 / 4))
    assert pooled["mase"] == pytest.approx((0.5 + 1.0 + 3.0 + 0.0) / 4)
    assert pooled["oos_r2"] == pytest.approx(1 - 0.14 / 0.29)
    assert pooled["mape"] == pytest.approx((0.1 + 0.1 + 0.2 + 0.0) / 4)


def test_a_signed_target_reports_no_mape(scored: pd.DataFrame) -> None:
    pooled = point_metrics(scored, variable=TargetVariable.EBITDA)

    assert "mape" not in pooled.columns


def test_asking_for_mape_on_operating_income_raises(scored: pd.DataFrame) -> None:
    with pytest.raises(UndefinedMetricError, match="MAPE is undefined"):
        mape(scored["y_level"], scored["y_hat_level"], TargetVariable.OPERATING_INCOME)


def test_a_forecaster_against_itself_has_zero_out_of_sample_r2(
    scored: pd.DataFrame,
) -> None:
    itself = scored.assign(baseline_scaled=scored["y_hat_scaled"])

    pooled = point_metrics(itself, variable=TargetVariable.REVENUE).iloc[0]

    assert pooled["oos_r2"] == pytest.approx(0.0)


def test_seasonal_naive_on_its_own_training_rows_has_a_mase_of_one() -> None:
    rng = np.random.default_rng(0)
    training = pd.DataFrame({
        "ticker": np.repeat(["AAA", "BBB"], 8),
        "sector": "Technology",
        "target_date": np.tile(pd.date_range("2020-03-31", periods=8, freq="QE"), 2),
        "y_scaled": rng.normal(size=16),
    })
    naive_error = rng.normal(0.0, [0.05] * 8 + [0.3] * 8)
    training["y_hat_scaled"] = training["y_scaled"] + naive_error
    training["error"] = naive_error
    scale = in_sample_scale(training, origin=training["target_date"].max())
    training["mase_scale"] = training["ticker"].map(scale)
    training["baseline_scaled"] = training["y_hat_scaled"]

    by_company = point_metrics(training, variable=TargetVariable.EBITDA, by=["ticker"])

    np.testing.assert_allclose(by_company["mase"], 1.0)


def test_the_in_sample_scale_uses_only_rows_that_train_at_the_origin() -> None:
    errors = pd.DataFrame({
        "ticker": ["AAA"] * 3,
        "target_date": pd.date_range("2020-03-31", periods=3, freq="QE"),
        "error": [0.1, -0.3, 9.0],
    })

    scale = in_sample_scale(errors, origin=errors["target_date"][1])

    assert scale["AAA"] == pytest.approx(0.2)


def test_a_missing_prediction_voids_the_groups_metrics(scored: pd.DataFrame) -> None:
    scored.loc[2, "y_hat_scaled"] = np.nan

    by_sector = point_metrics(
        scored, variable=TargetVariable.REVENUE, by=["sector"]
    ).set_index("sector")

    assert by_sector.loc["Energy", "missing"] == 1
    assert by_sector["mae"].isna()["Energy"]
    assert by_sector.loc["Technology", "mae"] == pytest.approx(0.15)


def test_the_tables_score_pooled_by_sector_and_by_company(
    scored: pd.DataFrame,
) -> None:
    tables = point_metric_tables(scored, variable=TargetVariable.REVENUE)

    assert len(tables.pooled) == 1
    assert sorted(tables.by_sector["sector"]) == ["Energy", "Technology"]
    assert sorted(tables.by_company["ticker"]) == ["AAA", "BBB"]


def test_the_winkler_score_charges_2_over_alpha_per_unit_outside(
    intervals: pd.DataFrame,
) -> None:
    at_80_percent = intervals.head(4)

    np.testing.assert_allclose(winkler_score(at_80_percent), [2.0, 12.0, 22.0, 2.0])


def test_pooled_interval_metrics_match_hand_computed_values(
    intervals: pd.DataFrame,
) -> None:
    pooled = interval_metrics(intervals).set_index("level")

    np.testing.assert_allclose(pooled["coverage"], [0.5, 0.5])
    np.testing.assert_allclose(pooled["mean_width"], [2.0, 2.0])
    # Misses cost 2 / 0.2 = 10 per unit at 80 %, 2 / 0.1 = 20 per unit at 90 %.
    np.testing.assert_allclose(pooled["mean_winkler_score"], [38.0 / 4, 68.0 / 4])


def test_a_missing_interval_voids_the_groups_metrics(intervals: pd.DataFrame) -> None:
    intervals.loc[2, "lower_scaled"] = np.nan

    by_sector = interval_metrics(intervals, by=["sector"]).set_index([
        "level",
        "sector",
    ])

    assert by_sector.loc[(0.8, "Energy"), "missing"] == 1
    assert by_sector["coverage"].isna()[0.8, "Energy"]
    assert by_sector.loc[(0.8, "Technology"), "coverage"] == pytest.approx(0.5)
    assert by_sector.loc[(0.9, "Energy"), "missing"] == 0


def test_the_interval_tables_score_each_level_pooled_and_by_sector(
    intervals: pd.DataFrame,
) -> None:
    tables = interval_metric_tables(intervals)

    assert list(tables.pooled["level"]) == [0.8, 0.9]
    assert len(tables.by_sector) == 2 * 2

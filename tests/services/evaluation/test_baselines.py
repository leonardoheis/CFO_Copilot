import numpy as np
import pandas as pd
import pytest

from app.domain import Forecaster, TargetVariable
from app.services.evaluation import (
    Baseline,
    BaselineForecaster,
    baseline_levels,
    reconstruct_on_error_scale,
)
from app.services.features import SEASONAL_LAG, TargetArm, arms_for

# Year two is year one grown 10 %, so every answer below can be checked by hand.
REVENUE = [100.0, 120.0, 110.0, 130.0, 110.0, 132.0, 121.0, 143.0, 121.0]
EBITDA = [10.0, -5.0, 8.0, 12.0, 14.0, -2.0, 9.0, 15.0, 13.0]
ORIGIN = 7


@pytest.fixture
def panel() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": "AAA",
        "date": pd.date_range("2020-03-31", periods=len(REVENUE), freq="QE"),
        TargetVariable.REVENUE: REVENUE,
        TargetVariable.EBITDA: EBITDA,
    })


@pytest.mark.parametrize(
    ("baseline", "expected"),
    [
        (Baseline.SEASONAL_NAIVE, 110.0),
        (Baseline.SEASONAL_NAIVE_GROWTH, 110.0 * 143.0 / 130.0),
        (Baseline.NAIVE, 143.0),
        (Baseline.DRIFT, 143.0 * (143.0 / 100.0) ** (1 / 7)),
    ],
)
def test_revenue_baselines_extrapolate_in_logs(
    panel: pd.DataFrame, baseline: Baseline, expected: float
) -> None:
    levels = baseline_levels(
        panel, variable=TargetVariable.REVENUE, horizon=1, baseline=baseline
    )

    assert levels[ORIGIN] == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize(
    ("baseline", "expected"),
    [
        (Baseline.SEASONAL_NAIVE, 14.0),
        (Baseline.SEASONAL_NAIVE_GROWTH, 14.0 + 15.0 - 12.0),
        (Baseline.NAIVE, 15.0),
        (Baseline.DRIFT, 15.0 + (15.0 - 10.0) / 7),
    ],
)
def test_signed_baselines_extrapolate_in_levels(
    panel: pd.DataFrame, baseline: Baseline, expected: float
) -> None:
    levels = baseline_levels(
        panel, variable=TargetVariable.EBITDA, horizon=1, baseline=baseline
    )

    assert levels[ORIGIN] == pytest.approx(expected, rel=1e-12)


def test_at_four_quarters_ahead_seasonal_naive_is_naive(panel: pd.DataFrame) -> None:
    seasonal, naive = (
        baseline_levels(
            panel, variable=TargetVariable.REVENUE, horizon=4, baseline=baseline
        )
        for baseline in (Baseline.SEASONAL_NAIVE, Baseline.NAIVE)
    )

    pd.testing.assert_series_equal(seasonal, naive)


@pytest.mark.parametrize(
    ("baseline", "first_defined"),
    [(Baseline.SEASONAL_NAIVE_GROWTH, 4), (Baseline.DRIFT, 1)],
)
def test_a_history_too_short_gives_no_forecast(
    panel: pd.DataFrame, baseline: Baseline, first_defined: int
) -> None:
    levels = baseline_levels(
        panel, variable=TargetVariable.REVENUE, horizon=1, baseline=baseline
    )

    assert levels[:first_defined].isna().all()
    assert levels[first_defined:].notna().all()


@pytest.mark.parametrize(
    "variable", [TargetVariable.REVENUE, TargetVariable.EBITDA]
)
@pytest.mark.parametrize("baseline", list(Baseline))
def test_the_forecaster_path_scores_the_baselines_own_levels(
    panel: pd.DataFrame, variable: TargetVariable, baseline: Baseline
) -> None:
    for arm in arms_for(variable):
        forecaster: Forecaster = BaselineForecaster(
            baseline, panels={"AAA": panel}, variable=variable, arm=arm, horizon=1
        )
        test = panel.rename(columns={"date": "origin_date"})
        prediction = forecaster.fit(test).predict(test)["y_hat"]

        scored = reconstruct_on_error_scale(
            panel,
            variable=variable,
            arm=arm,
            horizon=1,
            prediction=pd.Series(prediction.to_numpy(), index=panel["date"]),
        )

        expected = baseline_levels(
            panel, variable=variable, horizon=1, baseline=baseline
        )
        # An arm built on the year-earlier quarter needs a year of history.
        after_first_year = slice(SEASONAL_LAG, None)
        np.testing.assert_allclose(
            scored["y_hat_level"][after_first_year],
            expected[after_first_year],
            rtol=1e-9,
        )


@pytest.mark.parametrize(
    ("baseline", "arm"),
    [
        (Baseline.SEASONAL_NAIVE, TargetArm.LOG_DIFF4),
        (Baseline.SEASONAL_NAIVE_GROWTH, TargetArm.SEASNAIVE_RESIDUAL),
        (Baseline.NAIVE, TargetArm.LOG_DIFF1),
    ],
)
def test_a_baseline_is_zero_in_the_arm_built_around_it(
    panel: pd.DataFrame, baseline: Baseline, arm: TargetArm
) -> None:
    forecaster = BaselineForecaster(
        baseline,
        panels={"AAA": panel},
        variable=TargetVariable.REVENUE,
        arm=arm,
        horizon=1,
    )
    test = panel.rename(columns={"date": "origin_date"})

    y_hat = forecaster.predict(test)["y_hat"].dropna()

    np.testing.assert_allclose(y_hat, 0.0, atol=1e-12)


def test_a_company_without_a_panel_gets_no_prediction(panel: pd.DataFrame) -> None:
    forecaster = BaselineForecaster(
        Baseline.NAIVE,
        panels={"AAA": panel},
        variable=TargetVariable.REVENUE,
        arm=TargetArm.LOG_DIFF1,
        horizon=1,
    )
    test = pd.DataFrame(
        {"ticker": ["AAA", "ZZZ"], "origin_date": [panel["date"][ORIGIN]] * 2},
        index=[10, 11],
    )

    y_hat = forecaster.predict(test)["y_hat"]

    assert y_hat.index.tolist() == [10, 11]
    assert y_hat[10] == pytest.approx(0.0)
    assert np.isnan(y_hat[11])

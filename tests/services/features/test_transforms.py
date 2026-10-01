import numpy as np
import pandas as pd
import pytest

from app.data.schema import FINANCIAL_COLUMNS
from app.services.features import (
    SEASONAL_LAG,
    InvalidHorizonError,
    MissingRevenueError,
    NonPositiveValueError,
    TargetArm,
    TargetTransformer,
    TargetVariable,
    arms_for,
    default_arm,
    log_level,
    revenue_scaled_yoy_change,
    yoy_log_growth,
)

QUARTERS = 30
BASE_REVENUE = 100.0
QUARTERLY_GROWTH = 0.02
SEASONAL_AMPLITUDE = 0.1


@pytest.fixture
def seasonal_revenue() -> pd.Series:
    quarter = np.arange(QUARTERS)
    season = np.sin(2 * np.pi * quarter / SEASONAL_LAG)
    return pd.Series(
        BASE_REVENUE * np.exp(QUARTERLY_GROWTH * quarter + SEASONAL_AMPLITUDE * season)
    )


@pytest.mark.parametrize("arm", list(TargetArm))
@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_round_trip_recovers_the_actual_level(
    seasonal_revenue: pd.Series, arm: TargetArm, horizon: int
) -> None:
    transformer = TargetTransformer(arm=arm, horizon=horizon)
    target = transformer.make(seasonal_revenue, revenue=seasonal_revenue)

    rebuilt = transformer.reconstruct(
        seasonal_revenue, target, revenue=seasonal_revenue
    )

    actual = seasonal_revenue.shift(-horizon)
    known = rebuilt.notna() & actual.notna()
    assert known.sum() > 0
    np.testing.assert_allclose(rebuilt[known], actual[known], rtol=1e-9)


@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_zero_prediction_on_residual_arm_is_seasonal_naive_growth(
    seasonal_revenue: pd.Series, horizon: int
) -> None:
    transformer = TargetTransformer(arm=TargetArm.SEASNAIVE_RESIDUAL, horizon=horizon)
    zero = pd.Series(0.0, index=seasonal_revenue.index)

    rebuilt = transformer.reconstruct(seasonal_revenue, zero)

    expected = (
        seasonal_revenue.shift(SEASONAL_LAG - horizon)
        * seasonal_revenue
        / seasonal_revenue.shift(SEASONAL_LAG)
    )
    known = expected.notna()
    np.testing.assert_allclose(rebuilt[known], expected[known], rtol=1e-9)
    assert rebuilt[~known].isna().all()


def test_shrinkage_scales_only_the_residual_arm(seasonal_revenue: pd.Series) -> None:
    ones = pd.Series(1.0, index=seasonal_revenue.index)
    residual = TargetTransformer(arm=TargetArm.SEASNAIVE_RESIDUAL, horizon=1)
    plain = TargetTransformer(arm=TargetArm.LOG_DIFF4, horizon=1)

    full = residual.reconstruct(seasonal_revenue, ones, shrinkage=1.0)
    half = residual.reconstruct(seasonal_revenue, ones, shrinkage=0.5)
    plain_full = plain.reconstruct(seasonal_revenue, ones, shrinkage=1.0)
    plain_half = plain.reconstruct(seasonal_revenue, ones, shrinkage=0.5)

    known = full.notna()
    np.testing.assert_allclose(
        np.log(half[known]), np.log(full[known]) - 0.5, rtol=1e-9
    )
    pd.testing.assert_series_equal(plain_full, plain_half)


def test_missing_values_stay_missing(seasonal_revenue: pd.Series) -> None:
    seasonal_revenue.iloc[10] = np.nan

    target = TargetTransformer(arm=TargetArm.LOG_DIFF1, horizon=1).make(
        seasonal_revenue
    )

    assert np.isnan(target.iloc[10])
    assert np.isnan(target.iloc[9])
    assert target.iloc[8] == pytest.approx(
        np.log(seasonal_revenue.iloc[9] / seasonal_revenue.iloc[8])
    )


@pytest.mark.parametrize("bad_value", [0.0, -5.0])
def test_non_positive_values_are_refused_with_a_count(
    seasonal_revenue: pd.Series, bad_value: float
) -> None:
    seasonal_revenue.iloc[[3, 7]] = bad_value

    with pytest.raises(NonPositiveValueError, match="for 2 non-positive") as caught:
        log_level(seasonal_revenue)
    assert caught.value.count == len([3, 7])


@pytest.mark.parametrize("horizon", [0, 5])
def test_horizon_outside_one_to_four_is_refused_at_construction(horizon: int) -> None:
    with pytest.raises(InvalidHorizonError) as caught:
        TargetTransformer(arm=TargetArm.LOG_DIFF4, horizon=horizon)
    assert caught.value.horizon == horizon


def test_yoy_growth_is_the_four_quarter_log_difference(
    seasonal_revenue: pd.Series,
) -> None:
    growth = yoy_log_growth(seasonal_revenue)

    first_year_over_year = np.log(
        seasonal_revenue.iloc[SEASONAL_LAG] / seasonal_revenue.iloc[0]
    )
    assert growth.iloc[:SEASONAL_LAG].isna().all()
    assert growth.iloc[SEASONAL_LAG] == pytest.approx(first_year_over_year)


def test_the_five_target_variables_are_panel_financial_columns() -> None:
    values = {variable.value for variable in TargetVariable}

    assert values == {
        "revenue_usd_m",
        "gross_profit_usd_m",
        "opex_usd_m",
        "ebitda_usd_m",
        "free_cash_flow_usd_m",
    }
    assert values <= set(FINANCIAL_COLUMNS)


@pytest.fixture
def signed_ebitda() -> pd.Series:
    quarter = np.arange(QUARTERS)
    season = np.sin(2 * np.pi * quarter / SEASONAL_LAG)
    # Crosses zero: a loss-making stretch that log growth cannot represent.
    return pd.Series(40.0 * season + 2.0 * quarter - 20.0)


@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_revenue_scaled_arm_round_trips_through_negative_values(
    signed_ebitda: pd.Series, seasonal_revenue: pd.Series, horizon: int
) -> None:
    transformer = TargetTransformer(arm=TargetArm.REVENUE_SCALED_YOY, horizon=horizon)
    target = transformer.make(signed_ebitda, revenue=seasonal_revenue)

    rebuilt = transformer.reconstruct(signed_ebitda, target, revenue=seasonal_revenue)

    actual = signed_ebitda.shift(-horizon)
    known = rebuilt.notna() & actual.notna()
    assert (signed_ebitda < 0).any()
    assert known.sum() > 0
    np.testing.assert_allclose(rebuilt[known], actual[known], rtol=1e-9)


def test_revenue_scaled_target_is_the_change_over_trailing_revenue(
    signed_ebitda: pd.Series, seasonal_revenue: pd.Series
) -> None:
    horizon = 2
    origin = 10
    target = TargetTransformer(arm=TargetArm.REVENUE_SCALED_YOY, horizon=horizon).make(
        signed_ebitda, revenue=seasonal_revenue
    )

    change = (
        signed_ebitda.iloc[origin + horizon]
        - signed_ebitda.iloc[origin + horizon - SEASONAL_LAG]
    )
    trailing_revenue = seasonal_revenue.iloc[
        origin - SEASONAL_LAG + 1 : origin + 1
    ].sum()
    assert target.iloc[origin] == pytest.approx(change / trailing_revenue)


def test_revenue_scaled_arm_needs_revenue(signed_ebitda: pd.Series) -> None:
    transformer = TargetTransformer(arm=TargetArm.REVENUE_SCALED_YOY, horizon=1)

    with pytest.raises(MissingRevenueError, match="revenue_scaled_yoy"):
        transformer.make(signed_ebitda)


def test_revenue_scaled_growth_is_the_yearly_change_over_trailing_revenue(
    signed_ebitda: pd.Series, seasonal_revenue: pd.Series
) -> None:
    growth = revenue_scaled_yoy_change(signed_ebitda, seasonal_revenue)

    expected = (signed_ebitda - signed_ebitda.shift(SEASONAL_LAG)) / (
        seasonal_revenue.rolling(SEASONAL_LAG).sum()
    )
    pd.testing.assert_series_equal(growth, expected)


def test_revenue_keeps_the_log_arms_and_the_rest_the_scaled_arm() -> None:
    assert arms_for(TargetVariable.REVENUE) == (
        TargetArm.LOG_DIFF1,
        TargetArm.LOG_DIFF4,
        TargetArm.SEASNAIVE_RESIDUAL,
    )
    for variable in TargetVariable:
        if variable is not TargetVariable.REVENUE:
            assert arms_for(variable) == (TargetArm.REVENUE_SCALED_YOY,)


def test_each_variables_default_arm_is_one_of_its_own() -> None:
    assert default_arm(TargetVariable.REVENUE) is TargetArm.SEASNAIVE_RESIDUAL
    for variable in TargetVariable:
        assert default_arm(variable) in arms_for(variable)

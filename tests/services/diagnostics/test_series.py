import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.diagnostic import acorr_ljungbox

from app.services.diagnostics import (
    DiagnosticsSettings,
    SeriesDiagnostician,
    observed_since_last_gap,
    prepared_for_diagnosis,
)

QUARTERS = 80
BASE_REVENUE = 100.0
QUARTERLY_GROWTH = 0.02
SEASONAL_AMPLITUDE = 0.1
STRONG = 0.9
WEAK = 0.4
SETTINGS = DiagnosticsSettings()


@pytest.fixture
def diagnostician() -> SeriesDiagnostician:
    return SeriesDiagnostician(settings=SETTINGS)


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(0)


def test_series_after_the_last_gap_is_kept_without_splicing() -> None:
    series = pd.Series([np.nan, 1.0, 2.0, np.nan, 4.0, 5.0, 6.0])

    assert observed_since_last_gap(series).tolist() == [4.0, 5.0, 6.0]


def test_series_without_gaps_is_unchanged() -> None:
    series = pd.Series([1.0, 2.0, 3.0])

    assert observed_since_last_gap(series).tolist() == [1.0, 2.0, 3.0]


def test_all_missing_series_is_empty() -> None:
    assert observed_since_last_gap(pd.Series([np.nan, np.nan])).empty


def test_preparation_fills_short_gaps_and_counts_only_the_kept_ones() -> None:
    # The first gap is dropped with the run before the long gap; the last is filled.
    series = pd.Series([1.0, np.nan, 3.0, np.nan, np.nan, np.nan, 7.0, np.nan, 9.0])

    observed, interpolated = prepared_for_diagnosis(series, max_gap=1)

    assert observed.tolist() == [7.0, 8.0, 9.0]
    assert interpolated == 1


@pytest.mark.parametrize(("times_integrated", "expected"), [(0, 0), (1, 1), (2, 2)])
def test_differencing_order_matches_integration_order(
    diagnostician: SeriesDiagnostician,
    times_integrated: int,
    expected: int,
    rng: np.random.Generator,
) -> None:
    series = pd.Series(rng.normal(size=300))
    for _ in range(times_integrated):
        series = series.cumsum()

    assert diagnostician.differencing_order(series) == expected


def test_ljung_box_tests_the_series_the_differencing_order_accepted(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    twice_integrated = pd.Series(rng.normal(size=300)).cumsum().cumsum()
    second_difference = twice_integrated.diff().diff().dropna()
    lag_two_difference = twice_integrated.diff(2).dropna()
    lag = SETTINGS.ljung_box_lag

    record = diagnostician.diagnose("AAA", "revenue_usd_m", twice_integrated)

    assert record.d_levels == SETTINGS.max_differencing_order
    assert record.ljung_box_p == pytest.approx(
        acorr_ljungbox(second_difference, lags=[lag])["lb_pvalue"].iloc[0]
    )
    assert record.ljung_box_p != pytest.approx(
        acorr_ljungbox(lag_two_difference, lags=[lag])["lb_pvalue"].iloc[0]
    )


def test_seasonal_series_scores_high_and_noise_scores_low(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    steps = np.arange(QUARTERS)
    seasonal = pd.Series(np.sin(steps * np.pi / 2) + 0.05 * rng.normal(size=QUARTERS))
    noise = pd.Series(rng.normal(size=QUARTERS))

    assert diagnostician.seasonal_and_trend_strength(seasonal)[0] > STRONG
    assert diagnostician.seasonal_and_trend_strength(noise)[0] < WEAK


def test_trending_series_has_high_trend_strength(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    trend = pd.Series(np.arange(QUARTERS) + 0.1 * rng.normal(size=QUARTERS))

    assert diagnostician.seasonal_and_trend_strength(trend)[1] > STRONG


def test_short_series_is_reported_not_raised(
    diagnostician: SeriesDiagnostician,
) -> None:
    short = pd.Series(np.arange(1.0, SETTINGS.min_observations))

    result = diagnostician.diagnose("AAA", "revenue_usd_m", short)

    assert result.status == "insufficient_data"
    assert result.n_obs == SETTINGS.min_observations - 1
    assert result.d_levels is None


def test_non_positive_values_switch_off_log_fields_only(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    values = pd.Series(np.linspace(-5, 50, 60) + rng.normal(size=60))

    result = diagnostician.diagnose("AAA", "free_cash_flow_usd_m", values)

    assert result.status == "ok"
    assert result.log_defined is False
    assert result.d_levels is not None
    assert result.d_log is None
    assert result.box_cox_lambda is None


def test_positive_series_fills_every_field(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    steps = np.arange(QUARTERS)
    season = np.sin(steps * np.pi / 2)
    noise = 0.01 * rng.normal(size=QUARTERS)
    values = pd.Series(
        BASE_REVENUE
        * np.exp(QUARTERLY_GROWTH * steps + SEASONAL_AMPLITUDE * season + noise)
    )

    result = diagnostician.diagnose("AAA", "revenue_usd_m", values)

    assert result.log_defined is True
    assert None not in result.model_dump().values()


def test_gapped_series_counts_only_the_run_after_the_gap(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    values = pd.Series(np.linspace(10, 100, 40) + rng.normal(size=40))
    last_gap = 9
    # A two-quarter gap is too long to fill, so it cuts the analysed run.
    values.iloc[[0, 1, 8, last_gap]] = np.nan

    result = diagnostician.diagnose("TSLA", "revenue_usd_m", values)

    assert result.n_obs == len(values) - last_gap - 1


@pytest.mark.parametrize("level", [0.0, 2.5])
def test_constant_series_is_reported_not_raised(
    diagnostician: SeriesDiagnostician, level: float
) -> None:
    quarters = 40

    result = diagnostician.diagnose(
        "ADBE", "dividend_yield", pd.Series(np.full(quarters, level))
    )

    assert result.status == "constant"
    assert result.n_obs == quarters
    assert result.log_defined is (level > 0)
    assert result.d_levels is None
    assert result.seasonal_strength is None


SERIES_LENGTH = 40


def _gapped(gap_positions: list[int], rng: np.random.Generator) -> pd.Series:
    values = pd.Series(
        np.linspace(10, 100, SERIES_LENGTH) + rng.normal(size=SERIES_LENGTH)
    )
    values.iloc[gap_positions] = np.nan
    return values


def test_a_single_interior_gap_is_filled_for_diagnosis(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    result = diagnostician.diagnose("ADBE", "revenue_usd_m", _gapped([20], rng))

    assert result.n_obs == SERIES_LENGTH
    assert result.interpolated == 1


def test_a_two_quarter_gap_still_cuts_the_history(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    last_gap = 21
    result = diagnostician.diagnose(
        "TSLA", "revenue_usd_m", _gapped([20, last_gap], rng)
    )

    assert result.n_obs == SERIES_LENGTH - last_gap - 1
    assert result.interpolated == 0


def test_a_leading_gap_is_not_filled(
    diagnostician: SeriesDiagnostician, rng: np.random.Generator
) -> None:
    result = diagnostician.diagnose("TSLA", "revenue_usd_m", _gapped([0], rng))

    assert result.n_obs == SERIES_LENGTH - 1
    assert result.interpolated == 0


def test_interpolation_can_be_switched_off(rng: np.random.Generator) -> None:
    diagnostician = SeriesDiagnostician(
        settings=DiagnosticsSettings(max_interpolated_gap=0)
    )
    gap = 20

    result = diagnostician.diagnose("ADBE", "revenue_usd_m", _gapped([gap], rng))

    assert result.n_obs == SERIES_LENGTH - gap - 1
    assert result.interpolated == 0

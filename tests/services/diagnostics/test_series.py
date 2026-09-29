import numpy as np
import pandas as pd
import pytest

from app.services.diagnostics import (
    DiagnosticsSettings,
    SeriesDiagnostician,
    observed_since_last_gap,
)

RNG = np.random.default_rng(0)

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


def test_series_after_the_last_gap_is_kept_without_splicing() -> None:
    series = pd.Series([np.nan, 1.0, 2.0, np.nan, 4.0, 5.0, 6.0])

    assert observed_since_last_gap(series).tolist() == [4.0, 5.0, 6.0]


def test_series_without_gaps_is_unchanged() -> None:
    series = pd.Series([1.0, 2.0, 3.0])

    assert observed_since_last_gap(series).tolist() == [1.0, 2.0, 3.0]


def test_all_missing_series_is_empty() -> None:
    assert observed_since_last_gap(pd.Series([np.nan, np.nan])).empty


@pytest.mark.parametrize(("times_integrated", "expected"), [(0, 0), (1, 1), (2, 2)])
def test_differencing_order_matches_integration_order(
    diagnostician: SeriesDiagnostician, times_integrated: int, expected: int
) -> None:
    series = pd.Series(RNG.normal(size=300))
    for _ in range(times_integrated):
        series = series.cumsum()

    assert diagnostician.differencing_order(series) == expected


def test_seasonal_series_scores_high_and_noise_scores_low(
    diagnostician: SeriesDiagnostician,
) -> None:
    steps = np.arange(QUARTERS)
    seasonal = pd.Series(np.sin(steps * np.pi / 2) + 0.05 * RNG.normal(size=QUARTERS))
    noise = pd.Series(RNG.normal(size=QUARTERS))

    assert diagnostician.seasonal_and_trend_strength(seasonal)[0] > STRONG
    assert diagnostician.seasonal_and_trend_strength(noise)[0] < WEAK


def test_trending_series_has_high_trend_strength(
    diagnostician: SeriesDiagnostician,
) -> None:
    trend = pd.Series(np.arange(QUARTERS) + 0.1 * RNG.normal(size=QUARTERS))

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
    diagnostician: SeriesDiagnostician,
) -> None:
    values = pd.Series(np.linspace(-5, 50, 60) + RNG.normal(size=60))

    result = diagnostician.diagnose("AAA", "free_cash_flow_usd_m", values)

    assert result.status == "ok"
    assert result.log_defined is False
    assert result.d_levels is not None
    assert result.d_log is None
    assert result.box_cox_lambda is None


def test_positive_series_fills_every_field(
    diagnostician: SeriesDiagnostician,
) -> None:
    steps = np.arange(QUARTERS)
    season = np.sin(steps * np.pi / 2)
    values = pd.Series(
        BASE_REVENUE * np.exp(QUARTERLY_GROWTH * steps + SEASONAL_AMPLITUDE * season)
    )

    result = diagnostician.diagnose("AAA", "revenue_usd_m", values)

    assert result.log_defined is True
    assert None not in result.model_dump().values()


def test_gapped_series_counts_only_the_run_after_the_gap(
    diagnostician: SeriesDiagnostician,
) -> None:
    values = pd.Series(np.linspace(10, 100, 40))
    last_gap = 8
    values.iloc[[0, 1, last_gap]] = np.nan

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

import pytest
from pydantic import ValidationError

from app.services.diagnostics import (
    CompanyMacroSensitivity,
    DiagnosticsError,
    DiagnosticsSettings,
    MacroCorrelation,
    RegimeSettings,
    SeriesDiagnostics,
    TooFewCompaniesError,
)


def test_defaults_are_todays_values() -> None:
    settings = DiagnosticsSettings()

    assert settings.model_dump() == {
        "min_observations": 16,
        "significance": 0.05,
        "seasonal_period": 4,
        "ljung_box_lag": 8,
        "max_differencing_order": 2,
    }
    assert RegimeSettings().model_dump() == {
        "n_regimes": 3,
        "seed": 42,
        "n_init": 10,
    }


@pytest.mark.parametrize("significance", [0.0, 1.0, 1.5])
def test_significance_must_lie_strictly_between_zero_and_one(
    significance: float,
) -> None:
    with pytest.raises(ValidationError, match="significance"):
        DiagnosticsSettings(significance=significance)


def test_floor_must_cover_two_seasonal_cycles() -> None:
    with pytest.raises(ValidationError, match="two seasonal cycles"):
        DiagnosticsSettings(min_observations=8, seasonal_period=4)


def test_one_regime_is_refused() -> None:
    with pytest.raises(ValidationError):
        RegimeSettings(n_regimes=1)


def test_zero_clustering_restarts_are_refused() -> None:
    with pytest.raises(ValidationError, match="n_init"):
        RegimeSettings(n_init=0)


def test_constant_is_a_valid_status() -> None:
    record = SeriesDiagnostics(
        ticker="AAA",
        variable="dividend_yield",
        n_obs=40,
        status="constant",
        log_defined=False,
    )

    assert record.status == "constant"


def test_too_few_companies_names_both_counts() -> None:
    error = TooFewCompaniesError(companies=2, regimes=3)

    assert isinstance(error, DiagnosticsError)
    assert str(error) == "2 fully diagnosed companies cannot fill 3 regimes"


def test_sensitivity_row_has_one_column_per_macro_series_then_sector() -> None:
    sensitivity = CompanyMacroSensitivity(
        ticker="XOM",
        sector="Energy",
        correlations=(
            MacroCorrelation(macro_column="wti_oil", correlation=0.8),
            MacroCorrelation(macro_column="vix", correlation=-0.3),
        ),
    )

    assert sensitivity.as_table_row() == {
        "wti_oil": 0.8,
        "vix": -0.3,
        "sector": "Energy",
    }

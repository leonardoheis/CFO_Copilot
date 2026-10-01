import numpy as np
import pandas as pd
import pytest

from app.services.diagnostics import (
    DataDictionary,
    DiagnosticsService,
    DiagnosticsSettings,
    MacroCorrelator,
    OutlierRegister,
    OutlierSettings,
    RegimeSettings,
    SeasonalityRegimeClusterer,
    SeriesDiagnostician,
    SeriesDiagnostics,
)
from tests.conftest import PanelFactory

QUARTERS = 40
VARIABLES = ["revenue_usd_m", "eps"]


@pytest.fixture
def service() -> DiagnosticsService:
    return DiagnosticsService(
        diagnostician=SeriesDiagnostician(settings=DiagnosticsSettings()),
        clusterer=SeasonalityRegimeClusterer(settings=RegimeSettings(n_regimes=2)),
        correlator=MacroCorrelator(macro_columns=("vix", "fed_funds")),
        outlier_register=OutlierRegister(settings=OutlierSettings()),
        data_dictionary=DataDictionary(settings=OutlierSettings()),
    )


@pytest.fixture
def panels(make_panel: PanelFactory) -> dict[str, pd.DataFrame]:
    # Real series carry noise and differ by company; exact curves leave ADF's
    # regression rank-deficient and give KMeans identical points.
    rng = np.random.default_rng(0)
    return {
        ticker: make_panel(ticker=ticker, quarters=QUARTERS).assign(
            revenue_usd_m=lambda panel: (
                panel["revenue_usd_m"] * np.exp(0.05 * rng.normal(size=QUARTERS))
            ),
            eps=lambda panel: panel["eps"] + 0.1 * rng.normal(size=QUARTERS),
        )
        for ticker in ("AAA", "BBB", "CCC")
    }


def test_panel_diagnostics_yield_one_row_per_company_and_variable(
    service: DiagnosticsService, panels: dict[str, pd.DataFrame]
) -> None:
    table = service.diagnose_panel(panels, VARIABLES)

    assert len(table) == len(panels) * len(VARIABLES)
    assert set(table.columns) == set(SeriesDiagnostics.model_fields)


def test_regimes_come_from_the_injected_clusterer(
    service: DiagnosticsService, panels: dict[str, pd.DataFrame]
) -> None:
    diagnostics = service.diagnose_panel(panels, VARIABLES)

    regimes = service.seasonality_regimes(diagnostics, variable="revenue_usd_m")

    assert set(regimes.index) == set(panels)
    assert set(regimes) <= {0, 1}


def test_correlations_use_the_injected_macro_columns(
    service: DiagnosticsService, panels: dict[str, pd.DataFrame]
) -> None:
    table = service.growth_macro_correlations(panels, variable="revenue_usd_m")

    assert list(table.columns) == ["vix", "fed_funds", "sector"]
    assert list(table.index) == list(panels)


def test_the_audit_registers_and_describes_through_the_service(
    service: DiagnosticsService, panels: dict[str, pd.DataFrame]
) -> None:
    columns = ["revenue_usd_m", "eps"]
    pooled = pd.concat(panels.values(), ignore_index=True)

    register = service.register_outliers(panels, columns)
    dictionary = service.describe_columns(pooled, columns, register=register)

    assert set(register["column"]) <= set(columns)
    assert dictionary["column"].tolist() == columns

import pandas as pd
import pytest

from app.services.diagnostics import (
    DiagnosticsService,
    DiagnosticsSettings,
    MacroCorrelator,
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
    )


@pytest.fixture
def panels(make_panel: PanelFactory) -> dict[str, pd.DataFrame]:
    return {
        ticker: make_panel(ticker=ticker, quarters=QUARTERS)
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

from collections.abc import Mapping, Sequence

import pandas as pd

from app.services.diagnostics.panel import MacroCorrelator, SeasonalityRegimeClusterer
from app.services.diagnostics.series import SeriesDiagnostician


class DiagnosticsService:
    """Diagnose every company's series and summarise the panel for NB01.

    Usage::

        service = container.diagnostics_service()
        diagnostics = service.diagnose_panel(panels, ["revenue_usd_m"])
        regimes = service.seasonality_regimes(diagnostics, variable="revenue_usd_m")
    """

    def __init__(
        self,
        diagnostician: SeriesDiagnostician,
        clusterer: SeasonalityRegimeClusterer,
        correlator: MacroCorrelator,
    ) -> None:
        self._diagnostician = diagnostician
        self._clusterer = clusterer
        self._correlator = correlator

    def diagnose_panel(
        self, panels: Mapping[str, pd.DataFrame], variables: Sequence[str]
    ) -> pd.DataFrame:
        """Diagnose every company and variable.

        Returns:
            One row per (ticker, variable), columns from ``SeriesDiagnostics``.
        """
        records = [
            self._diagnostician.diagnose(ticker, variable, panel[variable]).model_dump()
            for ticker, panel in panels.items()
            for variable in variables
        ]
        return pd.DataFrame(records)

    def seasonality_regimes(
        self, diagnostics: pd.DataFrame, *, variable: str
    ) -> pd.Series:
        return self._clusterer.assign(diagnostics, variable=variable)

    def growth_macro_correlations(
        self, panels: Mapping[str, pd.DataFrame], *, variable: str
    ) -> pd.DataFrame:
        return self._correlator.correlate(panels, variable=variable)

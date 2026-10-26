from collections.abc import Mapping, Sequence

import pandas as pd

from app.services.diagnostics.series import SeriesDiagnostician


class DiagnosticsService:
    """Diagnose every company's series for NB01.

    Usage::

        service = container.diagnostics_service()
        diagnostics = service.diagnose_panel(panels, ["revenue_usd_m"])
    """

    def __init__(self, diagnostician: SeriesDiagnostician) -> None:
        self._diagnostician = diagnostician

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

from datetime import date
from typing import Final, Protocol

import pandas as pd
import requests

from app.data.dates import align_series_to_quarters, quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError
from app.data.schema import FRED_MACRO_COLUMNS

FRED_SERIES_BY_COLUMN: Final[dict[str, str]] = {
    "gdp_yoy": "A191RL1Q225SBEA",
    "fed_funds": "FEDFUNDS",
    "unemployment_rate": "UNRATE",
    "cpi_yoy": "CPIAUCSL",
    "dxy": "DTWEXBGS",
    "vix": "VIXCLS",
    "wti_oil": "DCOILWTICO",
    "yield_spread_10y2y": "T10Y2Y",
    "mfg_confidence": "BSCICP02USM460S",
}

CPI_COLUMN: Final = "cpi_yoy"
CPI_UNITS: Final = "pc1"
MISSING_FRED_API_KEY_MESSAGE: Final = (
    "FRED_API_KEY is not set. Add it to your .env file (see .env.example)."
)


class FredClient(Protocol):
    """The slice of fredapi's ``Fred`` this source relies on."""

    api_key: str | None

    def get_series(self, series_id: str, **kwargs: str) -> pd.Series: ...


class FredSource:
    def __init__(self, client: FredClient) -> None:
        self._client = client

    def fetch_macro_series(
        self,
        series_id: str,
        start: date,
        end: date,
        *,
        units: str | None = None,
    ) -> pd.Series:
        if not self._client.api_key:
            raise DataSourceUnavailableError(MISSING_FRED_API_KEY_MESSAGE)
        # fredapi appends every keyword to the URL, so an unset one is left out.
        options = {} if units is None else {"units": units}
        try:
            return self._client.get_series(
                series_id,
                observation_start=start.isoformat(),
                observation_end=end.isoformat(),
                **options,
            )
        except (ValueError, requests.RequestException) as error:
            message = f"Failed to fetch FRED series {series_id}: {error}"
            raise DataSourceUnavailableError(message) from error

    def fetch_macro_panel(self, start: date, end: date) -> pd.DataFrame:
        quarter_dates = quarter_end_dates(start, end)
        panel_data: dict[str, object] = {"date": quarter_dates}

        for column in FRED_MACRO_COLUMNS:
            raw_series = self.fetch_macro_series(
                FRED_SERIES_BY_COLUMN[column],
                start,
                end,
                units=CPI_UNITS if column == CPI_COLUMN else None,
            )
            aligned = align_series_to_quarters(raw_series, quarter_dates)
            panel_data[column] = aligned.tolist()

        return pd.DataFrame(panel_data)

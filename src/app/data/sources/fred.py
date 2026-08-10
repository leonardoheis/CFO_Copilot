from datetime import date
from typing import Any, Final

import pandas as pd
from fredapi import Fred

from app.data.dates import align_series_to_quarters, quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError
from app.data.schema import MACRO_COLUMNS

FRED_SERIES_BY_COLUMN: Final[dict[str, str]] = {
    "gdp_yoy": "A191RL1Q225SBEA",
    "fed_funds": "FEDFUNDS",
    "unemployment_rate": "UNRATE",
    "cpi_yoy": "CPIAUCSL",
    "dxy": "DTWEXBGS",
    "vix": "VIXCLS",
    "wti_oil": "DCOILWTICO",
}

CPI_COLUMN: Final = "cpi_yoy"
CPI_UNITS: Final = "pc1"
MISSING_FRED_API_KEY_MESSAGE: Final = (
    "FRED_API_KEY is not set. Add it to your .env file (see .env.example)."
)


class FredSource:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: Fred | None = None

    def _ensure_api_key(self) -> None:
        if not self._api_key:
            raise DataSourceUnavailableError(MISSING_FRED_API_KEY_MESSAGE)

    @property
    def _fred(self) -> Fred:
        self._ensure_api_key()
        if self._client is None:
            self._client = Fred(api_key=self._api_key)
        return self._client

    def fetch_macro_series(
        self,
        series_id: str,
        start: date,
        end: date,
        **kwargs: Any,
    ) -> pd.Series:
        self._ensure_api_key()
        try:
            return self._fred.get_series(
                series_id,
                observation_start=start.isoformat(),
                observation_end=end.isoformat(),
                **kwargs,
            )
        except ValueError as error:
            message = f"Failed to fetch FRED series {series_id}: {error}"
            raise DataSourceUnavailableError(message) from error

    def fetch_macro_panel(self, start: date, end: date) -> pd.DataFrame:
        quarter_dates = quarter_end_dates(start, end)
        panel_data: dict[str, object] = {"date": quarter_dates}

        for column in MACRO_COLUMNS:
            series_id = FRED_SERIES_BY_COLUMN[column]
            extra_kwargs: dict[str, str] = {}
            if column == CPI_COLUMN:
                extra_kwargs["units"] = CPI_UNITS

            raw_series = self.fetch_macro_series(
                series_id,
                start,
                end,
                **extra_kwargs,
            )
            aligned = align_series_to_quarters(raw_series, quarter_dates)
            panel_data[column] = aligned.tolist()

        return pd.DataFrame(panel_data)

    @property
    def macro_columns(self) -> tuple[str, ...]:
        return MACRO_COLUMNS

    @property
    def series_by_column(self) -> dict[str, str]:
        return FRED_SERIES_BY_COLUMN

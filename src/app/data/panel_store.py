from pathlib import Path
from typing import Final

import pandas as pd

from app.data.exceptions import MalformedPanelError, PanelNotFoundError
from app.data.schema import FINANCIAL_COLUMNS, MACRO_COLUMNS, METADATA_COLUMNS

REQUIRED_COLUMNS: Final = (*METADATA_COLUMNS, *FINANCIAL_COLUMNS, *MACRO_COLUMNS)
_PANEL_SUFFIX: Final = "_panel.parquet"


def _require_columns(ticker: str, panel: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in panel.columns]
    if missing:
        missing_list = ", ".join(missing)
        message = f"Panel for {ticker} is missing columns: {missing_list}"
        raise MalformedPanelError(message)


def _require_consecutive_quarter_ends(ticker: str, dates: pd.Series) -> None:
    expected = pd.date_range(dates.iloc[0], periods=len(dates), freq="QE")
    if not (dates.reset_index(drop=True) == pd.Series(expected)).all():
        message = f"Panel for {ticker} does not hold consecutive calendar quarter-ends"
        raise MalformedPanelError(message)


class PanelStore:
    """Read the per-company panel parquet files that ``write_panel`` produces."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, ticker: str) -> Path:
        return self._directory / f"{ticker.upper()}{_PANEL_SUFFIX}"

    def tickers(self) -> tuple[str, ...]:
        names = (path.name for path in self._directory.glob(f"*{_PANEL_SUFFIX}"))
        return tuple(sorted(name.removesuffix(_PANEL_SUFFIX) for name in names))

    def load(self, ticker: str) -> pd.DataFrame:
        """Load and validate one company's panel.

        Returns:
            The panel with ``date`` as datetime, one row per quarter.

        Raises:
            PanelNotFoundError: No file exists for the ticker.
        """
        path = self.path_for(ticker)
        if not path.exists():
            message = f"No panel for {ticker.upper()} at {path}"
            raise PanelNotFoundError(message)
        panel = pd.read_parquet(path)
        _require_columns(ticker.upper(), panel)
        panel["date"] = pd.to_datetime(panel["date"])
        _require_consecutive_quarter_ends(ticker.upper(), panel["date"])
        return panel

    def load_all(self) -> dict[str, pd.DataFrame]:
        """Load every panel on disk.

        Returns:
            Validated panels keyed by upper-case ticker.
        """
        return {ticker: self.load(ticker) for ticker in self.tickers()}

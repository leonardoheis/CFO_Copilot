from pathlib import Path
from typing import Final

import pandas as pd

from app.data.exceptions import MalformedPanelError, PanelNotFoundError
from app.data.schema import FINANCIAL_COLUMNS, MACRO_COLUMNS, METADATA_COLUMNS

REQUIRED_COLUMNS: Final = (*METADATA_COLUMNS, *FINANCIAL_COLUMNS, *MACRO_COLUMNS)
_PANEL_SUFFIX: Final = "_panel.parquet"
_PANEL_LONG_FILE: Final = "panel_long.parquet"
_MACRO_Q_FILE: Final = "macro_q.parquet"


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


def _iso_dates(dates: pd.Series) -> str:
    unique_dates = sorted(pd.to_datetime(dates).drop_duplicates())
    return ", ".join(date.date().isoformat() for date in unique_dates)


def _require_macro_row_for_every_panel_date(
    panel_long: pd.DataFrame, macro_q: pd.DataFrame
) -> None:
    covered = pd.to_datetime(panel_long["date"]).isin(pd.to_datetime(macro_q["date"]))
    if not covered.all():
        uncovered = panel_long.loc[~covered, "date"]
        message = f"macro_q has no row for panel dates: {_iso_dates(uncovered)}"
        raise MalformedPanelError(message)


def _require_complete_macro_values(merged: pd.DataFrame) -> None:
    missing = merged[list(MACRO_COLUMNS)].isna()
    dates = merged["date"]
    gaps = [
        f"{column} on {_iso_dates(dates[missing[column]])}"
        for column in MACRO_COLUMNS
        if missing[column].any()
    ]
    if gaps:
        gap_list = "; ".join(gaps)
        message = f"macro_q has missing values: {gap_list}"
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

    @property
    def panel_long_path(self) -> Path:
        return self._directory / _PANEL_LONG_FILE

    @property
    def macro_q_path(self) -> Path:
        return self._directory / _MACRO_Q_FILE

    def load_consolidated(self) -> dict[str, pd.DataFrame]:
        """Load NB00's outputs per ticker, refusing macro gaps in dates or values.

        Returns:
            Per-ticker frames with macro columns and flags; projected rows dropped.

        Raises:
            PanelNotFoundError: An NB00 output file is absent.
        """
        absent = [
            str(path)
            for path in (self.panel_long_path, self.macro_q_path)
            if not path.exists()
        ]
        if absent:
            absent_list = ", ".join(absent)
            message = f"NB00 outputs missing: {absent_list}"
            raise PanelNotFoundError(message)
        panel_long = pd.read_parquet(self.panel_long_path)
        macro_q = pd.read_parquet(self.macro_q_path)
        _require_macro_row_for_every_panel_date(panel_long, macro_q)
        merged = panel_long.merge(
            macro_q, on="date", how="left", validate="many_to_one"
        )
        _require_complete_macro_values(merged)
        reported = merged.loc[~merged["is_projected"]]
        return {
            str(ticker): frame.reset_index(drop=True)
            for ticker, frame in reported.groupby("ticker", sort=True)
        }

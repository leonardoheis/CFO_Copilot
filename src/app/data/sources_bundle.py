from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


class MacroSource(Protocol):
    def fetch_macro_panel(self, start: date, end: date) -> pd.DataFrame: ...


class MarketSource(Protocol):
    def fetch_market_panel(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> pd.DataFrame: ...

    def fetch_splits(self, ticker: str) -> pd.Series: ...


class FinancialsSource(Protocol):
    def fetch_financials_panel(
        self,
        ticker: str,
        start: date,
        end: date,
        splits: pd.Series,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True, slots=True)
class IngestionSources:
    fred: MacroSource
    yfinance: MarketSource
    sec_edgar: FinancialsSource

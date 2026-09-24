from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd

from app.data.companies import CompanyRegistry
from app.data.sources import AlphaVantageSource, FredSource, SecEdgarSource

MacroPanelFetcher = Callable[[date, date], pd.DataFrame]
FinancialsFetcher = Callable[[str, date, date, pd.Series], pd.DataFrame]
FallbackFinancialsFetcher = Callable[[str, date, date], pd.DataFrame]


class MarketSource(Protocol):
    def fetch_market_panel(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> pd.DataFrame: ...

    def fetch_index_return_panel(self, start: date, end: date) -> pd.DataFrame: ...

    def fetch_splits(self, ticker: str) -> pd.Series: ...


@dataclass(frozen=True, slots=True)
class IngestionSources:
    fetch_macro_panel: MacroPanelFetcher
    yfinance: MarketSource
    fetch_sec_financials: FinancialsFetcher
    registry: CompanyRegistry
    fetch_fallback_financials: FallbackFinancialsFetcher | None = None

    @classmethod
    def from_sources(
        cls,
        *,
        fred: FredSource,
        yfinance: MarketSource,
        sec_edgar: SecEdgarSource,
        registry: CompanyRegistry,
        alpha_vantage: AlphaVantageSource | None = None,
    ) -> "IngestionSources":
        """Bind each source's fetch method; the fallback is optional.

        Returns:
            Sources ready for ``merge_panel``.
        """
        return cls(
            fetch_macro_panel=fred.fetch_macro_panel,
            yfinance=yfinance,
            fetch_sec_financials=sec_edgar.fetch_financials_panel,
            registry=registry,
            fetch_fallback_financials=(
                alpha_vantage.fetch_financials_panel if alpha_vantage else None
            ),
        )

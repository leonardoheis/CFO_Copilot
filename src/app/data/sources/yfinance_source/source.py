"""Yahoo Finance market data source, including per-company ticker fallback."""

import logging
from datetime import date, timedelta
from typing import Final

import pandas as pd
import yfinance as yf

from app.data.companies import CompanyRegistry
from app.data.dates import (
    align_series_to_quarters,
    normalize_datetime_index,
    quarter_end_dates,
)
from app.data.exceptions import TickerNotFoundError
from app.data.schema import INDEX_COLUMNS, MARKET_COLUMNS

from .fetching import quarterly_dividend_yield, try_splits, try_stock_history

logger = logging.getLogger(__name__)

SP500_TICKER: Final = "^GSPC"
TWO_QUARTERS: Final = timedelta(days=190)
(SP500_RETURN_COLUMN,) = INDEX_COLUMNS


class YfinanceSource:
    def __init__(self, registry: CompanyRegistry) -> None:
        self._registry = registry

    def fetch_stock_history(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return the daily price history for a ticker.

        Falls back through the registry's other market tickers for a
        dual-listed company (e.g. GOOGL falling back to GOOG) when the
        primary symbol has no data.

        Returns:
            A DataFrame of OHLCV rows indexed by trading day.

        Raises:
            TickerNotFoundError: If Yahoo Finance has no history for the ticker.
        """
        for candidate in self._registry.market_history_tickers(ticker):
            history = try_stock_history(yf.Ticker(candidate), candidate, start, end)
            if not history.empty:
                return history

        message = f"No Yahoo Finance history found for ticker {ticker.upper()}"
        raise TickerNotFoundError(message)

    def fetch_market_panel(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        normalized_ticker = ticker.upper()
        quarter_dates = quarter_end_dates(start, end)
        close = self._combined_close_history(normalized_ticker, start, end)
        yahoo_ticker = yf.Ticker(normalized_ticker)

        stock_price = align_series_to_quarters(close, quarter_dates)
        dividend_yield = quarterly_dividend_yield(yahoo_ticker, close, quarter_dates)

        return pd.DataFrame(
            {
                "date": quarter_dates,
                "stock_price_usd": stock_price.tolist(),
                "dividend_yield": dividend_yield.tolist(),
            },
        )

    def fetch_index_return_panel(self, start: date, end: date) -> pd.DataFrame:
        """Return the S&P 500 return of the prior quarter for each quarter end.

        Returns:
            A DataFrame with ``date`` and ``sp500_return_lag1`` columns.
        """
        quarter_dates = quarter_end_dates(start, end)
        # The first row's lagged return needs the two quarter ends before it.
        lookback_dates = quarter_end_dates(start - TWO_QUARTERS, end)
        close = self.fetch_stock_history(SP500_TICKER, start - TWO_QUARTERS, end)[
            "Close"
        ]
        quarterly_close = align_series_to_quarters(close, lookback_dates)
        lagged_return = quarterly_close.pct_change(fill_method=None).shift(1)
        return pd.DataFrame(
            {
                "date": quarter_dates,
                SP500_RETURN_COLUMN: lagged_return.reindex(quarter_dates).tolist(),
            },
        )

    def fetch_splits(self, ticker: str) -> pd.Series:
        """Return the raw split history for a ticker.

        Returns:
            A series indexed by split effective date and valued by ratio; empty
            when the company has never split.
        """
        normalized_ticker = ticker.upper()
        splits = pd.Series(dtype=float)
        for market_ticker in self._registry.market_history_tickers(normalized_ticker):
            ticker_splits = try_splits(yf.Ticker(market_ticker), market_ticker)
            if ticker_splits.empty:
                logger.warning("No split data available for %s", market_ticker)
                continue
            splits = (
                ticker_splits
                if splits.empty
                else pd.concat([splits, ticker_splits]).sort_index()
            )
        return splits[~splits.index.duplicated(keep="last")]

    def _combined_close_history(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> pd.Series:
        combined = pd.Series(dtype=float)
        history_tickers = self._registry.market_history_tickers(ticker)
        for market_ticker in reversed(history_tickers):
            history = try_stock_history(
                yf.Ticker(market_ticker),
                market_ticker,
                start,
                end,
            )
            if history.empty:
                logger.warning("No price history available for %s", market_ticker)
                continue
            close = history["Close"].copy()
            close.index = normalize_datetime_index(close.index)
            combined = close if combined.empty else close.combine_first(combined)

        if combined.empty:
            message = f"No Yahoo Finance history found for ticker {ticker}"
            raise TickerNotFoundError(message)
        return combined

    @property
    def market_columns(self) -> tuple[str, ...]:
        return MARKET_COLUMNS

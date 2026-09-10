import logging
from datetime import date
from typing import Protocol, cast

import pandas as pd
import yfinance as yf

from app.data.companies import resolve_market_history_tickers
from app.data.dates import (
    align_series_to_quarters,
    inclusive_history_end,
    normalize_datetime_index,
    quarter_end_dates,
)
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import MARKET_COLUMNS

logger = logging.getLogger(__name__)


TRAILING_DIVIDEND_DAYS = 365


class _YahooTicker(Protocol):
    @property
    def splits(self) -> pd.Series: ...

    @property
    def dividends(self) -> pd.Series: ...


class YfinanceSource:
    @staticmethod
    def fetch_stock_history(
        ticker: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        normalized_ticker = ticker.upper()
        try:
            history = yf.Ticker(normalized_ticker).history(
                start=start.isoformat(),
                end=inclusive_history_end(end).isoformat(),
                auto_adjust=False,
            )
        except Exception as error:
            message = (
                "Failed to fetch Yahoo Finance history for "
                f"{normalized_ticker}: {error}"
            )
            raise DataSourceUnavailableError(message) from error

        if history.empty:
            message = f"No Yahoo Finance history found for ticker {normalized_ticker}"
            raise TickerNotFoundError(message)

        return history  # type: ignore[no-any-return]

    def fetch_market_panel(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        normalized_ticker = ticker.upper()
        quarter_dates = quarter_end_dates(start, end)
        close = self._combined_close_history(normalized_ticker, start, end)
        yahoo_ticker = yf.Ticker(normalized_ticker)

        stock_price = align_series_to_quarters(close, quarter_dates)
        dividend_yield = self._quarterly_dividend_yield(
            yahoo_ticker,
            close,
            quarter_dates,
        )

        return pd.DataFrame(
            {
                "date": quarter_dates,
                "stock_price_usd": stock_price.tolist(),
                "dividend_yield": dividend_yield.tolist(),
            },
        )

    def fetch_splits(self, ticker: str) -> pd.Series:
        """Return the raw split history for a ticker.

        Returns:
            A series indexed by split effective date and valued by ratio.

        Raises:
            TickerNotFoundError: If Yahoo Finance has no data for any market ticker.
        """
        normalized_ticker = ticker.upper()
        splits = pd.Series(dtype=float)
        for market_ticker in resolve_market_history_tickers(normalized_ticker):
            ticker_splits = self._fetch_splits(yf.Ticker(market_ticker), market_ticker)
            if ticker_splits.empty:
                logger.warning("No split data available for %s", market_ticker)
                continue
            splits = (
                ticker_splits
                if splits.empty
                else pd.concat([splits, ticker_splits]).sort_index()
            )
        if splits.empty:
            message = f"No Yahoo Finance data found for ticker {normalized_ticker}"
            raise TickerNotFoundError(message)
        return splits[~splits.index.duplicated(keep="last")]

    def _combined_close_history(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> pd.Series:
        combined = pd.Series(dtype=float)
        for market_ticker in reversed(resolve_market_history_tickers(ticker)):
            history = self._try_stock_history(market_ticker, start, end)
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

    @staticmethod
    def _try_stock_history(ticker: str, start: date, end: date) -> pd.DataFrame:
        """Fetch price history; return an empty DataFrame when the ticker has no data.

        Unlike ``fetch_stock_history``, this method never raises
        ``TickerNotFoundError`` — callers check emptiness instead of catching.

        Returns:
            A DataFrame with OHLCV columns, or an empty DataFrame if no data exists.

        Raises:
            DataSourceUnavailableError: If the API call itself fails.
        """
        try:
            history = yf.Ticker(ticker).history(
                start=start.isoformat(),
                end=inclusive_history_end(end).isoformat(),
                auto_adjust=False,
            )
        except Exception as error:
            message = f"Failed to fetch Yahoo Finance history for {ticker}: {error}"
            raise DataSourceUnavailableError(message) from error
        return cast("pd.DataFrame", history)

    @staticmethod
    def _fetch_splits(
        yahoo_ticker: _YahooTicker,
        ticker: str,
    ) -> pd.Series:
        """Fetch split history; return an empty Series when the ticker has no data.

        Unlike ``fetch_splits``, this method never raises ``TickerNotFoundError``
        — callers check emptiness instead of catching.

        Returns:
            A float Series indexed by split date, or an empty Series if no data exists.

        Raises:
            DataSourceUnavailableError: If the API call itself fails.
        """
        try:
            result = yahoo_ticker.splits
        except Exception as error:
            message = f"Failed to fetch Yahoo Finance splits for {ticker}: {error}"
            raise DataSourceUnavailableError(message) from error
        if result is None:
            return pd.Series(dtype=float)
        return result

    @property
    def market_columns(self) -> tuple[str, ...]:
        return MARKET_COLUMNS

    @staticmethod
    def _quarterly_dividend_yield(
        yahoo_ticker: _YahooTicker,
        close: pd.Series,
        quarter_dates: list[date],
    ) -> pd.Series:
        dividends = yahoo_ticker.dividends
        if dividends.empty:
            return pd.Series([0.0] * len(quarter_dates), index=quarter_dates)

        dividends.index = normalize_datetime_index(dividends.index)
        yields: list[float] = []
        for quarter_date in quarter_dates:
            quarter_end = pd.Timestamp(quarter_date)
            window_start = quarter_end - pd.Timedelta(days=TRAILING_DIVIDEND_DAYS)
            trailing_dividends = dividends.loc[
                (dividends.index > window_start) & (dividends.index <= quarter_end)
            ].sum()
            prices_to_date = close.loc[:quarter_end]
            if prices_to_date.empty or pd.isna(prices_to_date.iloc[-1]):
                yields.append(0.0)
                continue
            price = float(prices_to_date.iloc[-1])
            yields.append(float(trailing_dividends / price) if price > 0 else 0.0)

        return pd.Series(yields, index=quarter_dates)

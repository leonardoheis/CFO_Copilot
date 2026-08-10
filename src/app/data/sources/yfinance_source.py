from datetime import date

import pandas as pd
import yfinance as yf

from app.data.dates import (
    align_series_to_quarters,
    inclusive_history_end,
    normalize_datetime_index,
    quarter_end_dates,
)
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import MARKET_COLUMNS

TRAILING_DIVIDEND_DAYS = 365


class YfinanceSource:
    def fetch_stock_history(  # ruff: ignore[no-self-use]
        self,
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

        return history

    def fetch_market_panel(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        normalized_ticker = ticker.upper()
        quarter_dates = quarter_end_dates(start, end)
        history = self.fetch_stock_history(normalized_ticker, start, end)
        yahoo_ticker = yf.Ticker(normalized_ticker)

        close = history["Close"].copy()
        close.index = normalize_datetime_index(close.index)

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
        """
        normalized_ticker = ticker.upper()
        return self._fetch_splits(yf.Ticker(normalized_ticker), normalized_ticker)

    @staticmethod
    def _fetch_splits(
        yahoo_ticker: yf.Ticker,
        ticker: str,
    ) -> pd.Series:
        try:
            return yahoo_ticker.splits
        except Exception as error:
            message = f"Failed to fetch Yahoo Finance splits for {ticker}: {error}"
            raise DataSourceUnavailableError(message) from error

    @property
    def market_columns(self) -> tuple[str, ...]:
        return MARKET_COLUMNS

    @staticmethod
    def _quarterly_dividend_yield(
        yahoo_ticker: yf.Ticker,
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

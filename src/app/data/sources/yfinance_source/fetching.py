"""Yahoo Finance ticker access and per-ticker derivations.

These helpers take an injected ticker object rather than constructing one, so
they can be exercised with a fake. None of them raise ``TickerNotFoundError``:
they return empty sentinels when a ticker has no data, leaving the decision to
give up to the public methods on ``YfinanceSource``.
"""

from datetime import date
from typing import Final, Protocol

import pandas as pd

from app.data.dates import inclusive_history_end, normalize_datetime_index
from app.data.exceptions import DataSourceUnavailableError

TRAILING_DIVIDEND_DAYS: Final = 365


class YahooTicker(Protocol):
    @property
    def splits(self) -> pd.Series: ...

    @property
    def dividends(self) -> pd.Series: ...

    def history(
        self,
        *,
        start: str,
        end: str,
        auto_adjust: bool,
    ) -> pd.DataFrame: ...


def try_stock_history(
    yahoo_ticker: YahooTicker,
    ticker: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Fetch price history; return an empty DataFrame when the ticker has no data.

    Returns:
        A DataFrame with OHLCV columns, or an empty DataFrame if no data exists.

    Raises:
        DataSourceUnavailableError: If the API call itself fails.
    """
    start_argument = start.isoformat()
    end_argument = inclusive_history_end(end).isoformat()
    try:
        history = yahoo_ticker.history(
            start=start_argument,
            end=end_argument,
            auto_adjust=False,
        )
    except Exception as error:
        message = (
            f"Failed to fetch Yahoo Finance history for {ticker} "
            f"({type(error).__name__}): {error}"
        )
        raise DataSourceUnavailableError(message) from error
    if history is None:
        return pd.DataFrame()
    return history


def try_splits(yahoo_ticker: YahooTicker, ticker: str) -> pd.Series:
    """Fetch split history; return an empty Series when the ticker has no data.

    Returns:
        A float Series indexed by split date, or an empty Series if no data exists.

    Raises:
        DataSourceUnavailableError: If the API call itself fails.
    """
    try:
        result = yahoo_ticker.splits
    except Exception as error:
        message = (
            f"Failed to fetch Yahoo Finance splits for {ticker} "
            f"({type(error).__name__}): {error}"
        )
        raise DataSourceUnavailableError(message) from error
    if result is None:
        return pd.Series(dtype=float)
    return result


def quarterly_dividend_yield(
    yahoo_ticker: YahooTicker,
    close: pd.Series,
    quarter_dates: list[date],
) -> pd.Series:
    """Compute the trailing-twelve-month dividend yield at each quarter end.

    Returns:
        A series of yields indexed by quarter end date.
    """
    dividends = yahoo_ticker.dividends
    if dividends.empty:
        return pd.Series([0.0] * len(quarter_dates), index=quarter_dates)

    dividends = dividends.copy()
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

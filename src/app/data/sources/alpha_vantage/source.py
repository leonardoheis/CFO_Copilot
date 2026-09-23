"""Alpha Vantage HTTP client: credentials, request caching, and error mapping."""

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Final, cast

import pandas as pd
import requests

from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceError, DataSourceUnavailableError
from app.data.schema import FINANCIAL_COLUMNS, FinancialQuarterValues
from app.settings import Settings

from .parsing import (
    JsonObject,
    merge_balance_sheet,
    merge_cash_flow,
    merge_earnings,
    merge_income,
    row_for_date,
)

ALPHA_VANTAGE_URL: Final = "https://www.alphavantage.co/query"
INCOME_STATEMENT: Final = "INCOME_STATEMENT"
CASH_FLOW: Final = "CASH_FLOW"
BALANCE_SHEET: Final = "BALANCE_SHEET"
EARNINGS: Final = "EARNINGS"
RATE_LIMIT_KEYS: Final[tuple[str, ...]] = ("Note", "Information")
MIN_REQUEST_INTERVAL_SECONDS: Final = 1.0
RATE_LIMIT_ATTEMPTS: Final = 4
MISSING_API_KEY_MESSAGE: Final = (
    "ALPHA_VANTAGE_API_KEY is not set. Add it to your .env file."
)
logger = logging.getLogger(__name__)


class AlphaVantageSource:
    def __init__(
        self,
        api_key: str,
        cache_directory: Path,
        *,
        refresh: bool = False,
    ) -> None:
        self._api_key = api_key
        self._cache_directory = cache_directory
        self._refresh = refresh
        self._last_request_at: float | None = None

    def fetch_financials_panel(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        self._ensure_api_key()
        normalized_ticker = ticker.upper()
        income = self._request(INCOME_STATEMENT, normalized_ticker)
        cash_flow = self._request(CASH_FLOW, normalized_ticker)
        balance = self._request(BALANCE_SHEET, normalized_ticker)
        earnings = self._request(EARNINGS, normalized_ticker)

        values_by_date: dict[date, FinancialQuarterValues] = {}
        merge_income(values_by_date, income)
        merge_cash_flow(values_by_date, cash_flow)
        merge_balance_sheet(values_by_date, balance)
        merge_earnings(values_by_date, earnings)
        quarter_dates = quarter_end_dates(start, end)

        rows = [
            row_for_date(values_by_date.get(quarter_date), quarter_date).model_dump()
            for quarter_date in quarter_dates
        ]
        return pd.DataFrame(rows).loc[
            :,
            ["date", *FINANCIAL_COLUMNS, "shares_outstanding"],
        ]

    def _request(self, function: str, ticker: str) -> JsonObject:
        cache_path = self._cache_path(function, ticker)
        if cache_path.exists() and not self._refresh:
            return _read_cache(cache_path)

        last_rate_limit: DataSourceError | None = None
        for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
            self._wait_for_rate_limit()
            typed_payload = self._get_json(function, ticker)
            self._last_request_at = time.monotonic()
            rate_limit = _rate_limit_error(typed_payload)
            if rate_limit is not None:
                last_rate_limit = rate_limit
                logger.warning(
                    "Alpha Vantage rate-limited %s for %s (attempt %d/%d)",
                    function,
                    ticker,
                    attempt,
                    RATE_LIMIT_ATTEMPTS,
                )
                continue
            permanent = _permanent_error(typed_payload)
            if permanent is not None:
                raise permanent
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(typed_payload), encoding="utf-8")
            return typed_payload

        if last_rate_limit is None:
            msg = f"Alpha Vantage {function} for {ticker} failed after retries"
            raise DataSourceError(msg)
        raise last_rate_limit

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _get_json(self, function: str, ticker: str) -> JsonObject:
        try:
            response = requests.get(
                ALPHA_VANTAGE_URL,
                params={
                    "function": function,
                    "symbol": ticker,
                    "apikey": self._api_key,
                },
                timeout=Settings.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            msg = f"Failed to fetch Alpha Vantage {function} for {ticker}: {error}"
            raise DataSourceUnavailableError(msg) from error

        if not isinstance(payload, dict):
            msg = f"Unexpected Alpha Vantage response for {function} and {ticker}"
            raise DataSourceUnavailableError(msg)
        return cast("JsonObject", payload)

    def _cache_path(self, function: str, ticker: str) -> Path:
        return self._cache_directory / ticker / f"{function.lower()}.json"

    def _ensure_api_key(self) -> None:
        if not self._api_key:
            raise DataSourceUnavailableError(MISSING_API_KEY_MESSAGE)


def _rate_limit_error(payload: JsonObject) -> DataSourceError | None:
    for key in RATE_LIMIT_KEYS:
        if key in payload:
            return DataSourceError(f"Alpha Vantage {key}: {payload[key]}")
    return None


def _permanent_error(payload: JsonObject) -> DataSourceError | None:
    message = payload.get("Error Message")
    if message is None:
        return None
    return DataSourceError(f"Alpha Vantage Error Message: {message}")


def _read_cache(path: Path) -> JsonObject:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        msg = f"Failed to read Alpha Vantage cache {path}: {error}"
        raise DataSourceUnavailableError(msg) from error
    if not isinstance(payload, dict):
        msg = f"Invalid Alpha Vantage cache format: {path}"
        raise DataSourceUnavailableError(msg)
    return cast("JsonObject", payload)

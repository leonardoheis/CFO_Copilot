"""Alpha Vantage HTTP client: credentials, request caching, and error mapping."""

import json
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
ERROR_KEYS: Final[tuple[str, ...]] = ("Note", "Information", "Error Message")
MISSING_API_KEY_MESSAGE: Final = (
    "ALPHA_VANTAGE_API_KEY is not set. Add it to your .env file."
)


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
        typed_payload = cast("JsonObject", payload)
        for key in ERROR_KEYS:
            if key in typed_payload:
                message = str(typed_payload[key])
                msg_0 = f"Alpha Vantage {key}: {message}"
                raise DataSourceError(msg_0)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(typed_payload), encoding="utf-8")
        return typed_payload

    def _cache_path(self, function: str, ticker: str) -> Path:
        return self._cache_directory / ticker / f"{function.lower()}.json"

    def _ensure_api_key(self) -> None:
        if not self._api_key:
            raise DataSourceUnavailableError(MISSING_API_KEY_MESSAGE)


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

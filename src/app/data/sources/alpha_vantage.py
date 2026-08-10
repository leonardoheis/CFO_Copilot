import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, cast

import pandas as pd
import requests

from app.data.dates import nearest_quarter_end, quarter_end_dates
from app.data.exceptions import DataSourceError, DataSourceUnavailableError
from app.data.schema import FINANCIAL_COLUMNS

ALPHA_VANTAGE_URL: Final = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT: Final = 30
MILLIONS_DIVISOR: Final = 1_000_000
INCOME_STATEMENT: Final = "INCOME_STATEMENT"
CASH_FLOW: Final = "CASH_FLOW"
BALANCE_SHEET: Final = "BALANCE_SHEET"
EARNINGS: Final = "EARNINGS"
ERROR_KEYS: Final[tuple[str, ...]] = ("Note", "Information", "Error Message")
MISSING_API_KEY_MESSAGE: Final = (
    "ALPHA_VANTAGE_API_KEY is not set. Add it to your .env file."
)

JsonObject = dict[str, object]


@dataclass(slots=True)
class QuarterlyValues:
    revenue_usd_m: float | None = None
    gross_profit_usd_m: float | None = None
    opex_usd_m: float | None = None
    operating_income_usd_m: float | None = None
    ebitda_usd_m: float | None = None
    net_income_usd_m: float | None = None
    free_cash_flow_usd_m: float | None = None
    eps: float | None = None
    shares_outstanding: float | None = None


class AlphaVantageSource:
    """Fetch normalized quarterly fundamentals from Alpha Vantage."""

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

        values_by_date: dict[date, QuarterlyValues] = {}
        self._merge_income(values_by_date, income)
        self._merge_cash_flow(values_by_date, cash_flow)
        self._merge_balance_sheet(values_by_date, balance)
        self._merge_earnings(values_by_date, earnings)
        quarter_dates = quarter_end_dates(start, end)

        rows = [
            self._row_for_date(values_by_date.get(quarter_date), quarter_date)
            for quarter_date in quarter_dates
        ]
        return pd.DataFrame(rows).loc[
            :,
            ["date", *FINANCIAL_COLUMNS, "shares_outstanding"],
        ]

    def _request(self, function: str, ticker: str) -> JsonObject:
        cache_path = self._cache_path(function, ticker)
        if cache_path.exists() and not self._refresh:
            return self._read_cache(cache_path)

        try:
            response = requests.get(
                ALPHA_VANTAGE_URL,
                params={
                    "function": function,
                    "symbol": ticker,
                    "apikey": self._api_key,
                },
                timeout=REQUEST_TIMEOUT,
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

    @staticmethod
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

    def _ensure_api_key(self) -> None:
        if not self._api_key:
            raise DataSourceUnavailableError(MISSING_API_KEY_MESSAGE)

    def _merge_income(
        self,
        values_by_date: dict[date, QuarterlyValues],
        payload: JsonObject,
    ) -> None:
        for report in self._reports(payload, "quarterlyReports"):
            quarter_date = self._report_date(report)
            if quarter_date is None:
                continue
            values = values_by_date.setdefault(quarter_date, QuarterlyValues())
            values.revenue_usd_m = self._millions(report, "totalRevenue")
            values.gross_profit_usd_m = self._millions(report, "grossProfit")
            values.opex_usd_m = self._millions(report, "operatingExpenses")
            values.operating_income_usd_m = self._millions(
                report,
                "operatingIncome",
            )
            values.ebitda_usd_m = self._millions(report, "ebitda")
            values.net_income_usd_m = self._millions(report, "netIncome")
            values.eps = self._number(report, "dilutedEPS") or self._number(
                report,
                "basicEPS",
            )

    def _merge_cash_flow(
        self,
        values_by_date: dict[date, QuarterlyValues],
        payload: JsonObject,
    ) -> None:
        for report in self._reports(payload, "quarterlyReports"):
            quarter_date = self._report_date(report)
            if quarter_date is None:
                continue
            operating_cash_flow = self._number(report, "operatingCashflow")
            capital_expenditures = self._number(report, "capitalExpenditures")
            if operating_cash_flow is None or capital_expenditures is None:
                continue
            values = values_by_date.setdefault(quarter_date, QuarterlyValues())
            values.free_cash_flow_usd_m = (
                operating_cash_flow - abs(capital_expenditures)
            ) / MILLIONS_DIVISOR

    def _merge_balance_sheet(
        self,
        values_by_date: dict[date, QuarterlyValues],
        payload: JsonObject,
    ) -> None:
        for report in self._reports(payload, "quarterlyReports"):
            quarter_date = self._report_date(report)
            shares = self._number(report, "commonStockSharesOutstanding")
            if quarter_date is not None and shares is not None:
                values_by_date.setdefault(
                    quarter_date,
                    QuarterlyValues(),
                ).shares_outstanding = shares

    def _merge_earnings(
        self,
        values_by_date: dict[date, QuarterlyValues],
        payload: JsonObject,
    ) -> None:
        for report in self._reports(payload, "quarterlyEarnings"):
            quarter_date = self._report_date(report)
            earnings_per_share = self._number(report, "reportedEPS")
            if quarter_date is None or earnings_per_share is None:
                continue
            values = values_by_date.setdefault(quarter_date, QuarterlyValues())
            if values.eps is None:
                values.eps = earnings_per_share

    @staticmethod
    def _reports(payload: JsonObject, key: str) -> list[JsonObject]:
        raw_reports = payload.get(key, [])
        if not isinstance(raw_reports, list):
            return []
        return [
            cast("JsonObject", report)
            for report in raw_reports
            if isinstance(report, dict)
        ]

    @staticmethod
    def _report_date(report: JsonObject) -> date | None:
        raw_date = report.get("fiscalDateEnding")
        if not isinstance(raw_date, str):
            return None
        try:
            return nearest_quarter_end(date.fromisoformat(raw_date), 46)
        except ValueError:
            return None

    @staticmethod
    def _number(report: JsonObject, key: str) -> float | None:
        value = report.get(key)
        if value is None or str(value) in {"", "None", "null"}:
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None

    @classmethod
    def _millions(cls, report: JsonObject, key: str) -> float | None:
        value = cls._number(report, key)
        return value / MILLIONS_DIVISOR if value is not None else None

    @staticmethod
    def _row_for_date(
        values: QuarterlyValues | None,
        quarter_date: date,
    ) -> dict[str, date | float | None]:
        values = values or QuarterlyValues()
        revenue = values.revenue_usd_m
        gross_profit = values.gross_profit_usd_m
        operating_income = values.operating_income_usd_m
        net_income = values.net_income_usd_m
        safe_revenue = revenue if revenue not in {None, 0.0} else None
        return {
            "date": quarter_date,
            "revenue_usd_m": revenue,
            "gross_profit_usd_m": gross_profit,
            "opex_usd_m": values.opex_usd_m,
            "operating_income_usd_m": operating_income,
            "ebitda_usd_m": values.ebitda_usd_m,
            "net_income_usd_m": net_income,
            "free_cash_flow_usd_m": values.free_cash_flow_usd_m,
            "gross_margin": (
                gross_profit / safe_revenue
                if gross_profit is not None and safe_revenue is not None
                else None
            ),
            "operating_margin": (
                operating_income / safe_revenue
                if operating_income is not None and safe_revenue is not None
                else None
            ),
            "net_margin": (
                net_income / safe_revenue
                if net_income is not None and safe_revenue is not None
                else None
            ),
            "eps": values.eps,
            "shares_outstanding": values.shares_outstanding,
        }

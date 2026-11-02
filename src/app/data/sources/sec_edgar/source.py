"""SEC EDGAR HTTP client: CIK resolution and us-gaap fact retrieval."""

from datetime import date
from functools import partial
from typing import Final, cast

import pandas as pd
import requests

from app.data.companies import CompanyRegistry
from app.data.dates import quarter_end_dates
from app.data.exceptions import (
    DataSourceUnavailableError,
    MalformedPayloadError,
    TickerNotFoundError,
)

from .chains import quarterly_financials
from .concepts import USD_UNIT
from .parsing import (
    JsonObject,
    SecTicker,
    concept_facts,
    financial_panel_from_raw,
    merge_raw_financial_frames,
    sec_tickers,
)
from .xbrl import XbrlFact

SEC_TICKERS_URL: Final = "https://www.sec.gov/files/company_tickers.json"
# Not the per-concept endpoint: for some filers (ABT, F, KO) it answers 200 with
# an empty unit while companyfacts holds the full history for the same tag.
SEC_COMPANY_FACTS_URL: Final = (
    "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
)
NOT_FOUND_STATUS: Final = 404
MISSING_USER_AGENT_MESSAGE: Final = (
    "SEC_USER_AGENT is not set. Add it to your .env file (see .env.example)."
)


def _get_sec_json(url: str, *, user_agent: str, timeout: int) -> object | None:
    """Fetch one SEC document.

    Returns:
        The decoded JSON, or None when SEC has no document at ``url``.

    Raises:
        DataSourceUnavailableError: No user agent, any other HTTP failure, or a
            body that is not JSON.
    """
    if not user_agent:
        raise DataSourceUnavailableError(MISSING_USER_AGENT_MESSAGE)
    try:
        response = requests.get(
            url,
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if response.status_code == NOT_FOUND_STATUS:
            return None
        response.raise_for_status()
        payload: object = response.json()
    except (requests.RequestException, ValueError) as error:
        msg = f"Failed to fetch SEC EDGAR {url}: {error}"
        raise DataSourceUnavailableError(msg) from error
    return payload


def fetch_sec_tickers(*, user_agent: str, timeout: int) -> dict[str, SecTicker]:
    """Download SEC's ticker file, indexed by upper-case ticker.

    Returns:
        Each ticker's zero-padded CIK and registered title.

    Raises:
        DataSourceUnavailableError: The file cannot be fetched.
    """
    payload = _get_sec_json(SEC_TICKERS_URL, user_agent=user_agent, timeout=timeout)
    if payload is None:
        msg = f"SEC ticker file not found at {SEC_TICKERS_URL}"
        raise DataSourceUnavailableError(msg)
    return sec_tickers(payload)


class SecEdgarSource:
    def __init__(
        self, user_agent: str, registry: CompanyRegistry, *, timeout: int
    ) -> None:
        self._user_agent = user_agent
        self._registry = registry
        self._timeout = timeout
        self._tickers: dict[str, SecTicker] | None = None
        self._company_facts_by_cik: dict[str, JsonObject] = {}

    def resolve_ciks(self, ticker: str) -> tuple[str, ...]:
        return self._registry.sec_ciks(ticker, self._lookup_ticker_cik)

    def _lookup_ticker_cik(self, ticker: str) -> str:
        normalized_ticker = ticker.upper()
        found = self._load_tickers().get(normalized_ticker)
        if found is None:
            msg = f"No SEC EDGAR CIK found for ticker {normalized_ticker}"
            raise TickerNotFoundError(
                msg,
            )
        return found.cik

    def fetch_concept(
        self,
        cik: str,
        tag: str,
        unit: str = USD_UNIT,
    ) -> list[XbrlFact]:
        return concept_facts(self._company_facts(cik), tag, unit)

    def _company_facts(self, cik: str) -> JsonObject:
        padded_cik = cik.zfill(10)
        cached = self._company_facts_by_cik.get(padded_cik)
        if cached is not None:
            return cached
        payload = _get_sec_json(
            SEC_COMPANY_FACTS_URL.format(cik=padded_cik),
            user_agent=self._user_agent,
            timeout=self._timeout,
        )
        # 404 is SEC's answer for a CIK that has never filed XBRL.
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            msg = f"SEC companyfacts CIK{padded_cik} is not a JSON object"
            raise MalformedPayloadError(msg)
        company_facts = cast("JsonObject", payload)
        self._company_facts_by_cik[padded_cik] = company_facts
        return company_facts

    def fetch_quarterly_financials(
        self,
        ticker: str,
        start: date,
        end: date,
        splits: pd.Series | None = None,
    ) -> pd.DataFrame:
        quarter_dates = quarter_end_dates(start, end)
        merged: pd.DataFrame | None = None
        for cik in self.resolve_ciks(ticker):
            raw = quarterly_financials(
                cik, partial(self.fetch_concept, cik), quarter_dates, splits
            )
            merged = raw if merged is None else merge_raw_financial_frames(raw, merged)
        if merged is None:
            msg = f"No SEC EDGAR CIKs resolved for ticker {ticker.upper()}"
            raise TickerNotFoundError(msg)
        return merged

    def fetch_financials_panel(
        self,
        ticker: str,
        start: date,
        end: date,
        splits: pd.Series | None = None,
    ) -> pd.DataFrame:
        raw = self.fetch_quarterly_financials(ticker, start, end, splits)
        return financial_panel_from_raw(raw)

    def _load_tickers(self) -> dict[str, SecTicker]:
        if self._tickers is None:
            self._tickers = fetch_sec_tickers(
                user_agent=self._user_agent, timeout=self._timeout
            )
        return self._tickers

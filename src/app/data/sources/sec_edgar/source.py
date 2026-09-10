"""SEC EDGAR HTTP client: CIK resolution and us-gaap concept retrieval."""

import math
from datetime import date
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
from app.data.xbrl import (
    InstantXbrlFact,
    XbrlFact,
    instant_series_from_facts,
    quarterly_facts_from_facts,
)
from app.settings import Settings

from .concepts import (
    DILUTED_SHARES_FALLBACK,
    PER_SHARE_UNIT,
    SHARES_UNIT,
    TAG_CHAINS,
    USD_UNIT,
    ConceptSpec,
)
from .parsing import (
    financial_panel_from_raw,
    merge_raw_financial_frames,
    split_factors_for_filing_dates,
)

SEC_TICKERS_URL: Final = "https://www.sec.gov/files/company_tickers.json"
SEC_CONCEPT_URL: Final = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
)
NOT_FOUND_STATUS: Final = 404
MISSING_USER_AGENT_MESSAGE: Final = (
    "SEC_USER_AGENT is not set. Add it to your .env file (see .env.example)."
)


class SecEdgarSource:
    def __init__(self, user_agent: str, registry: CompanyRegistry) -> None:
        self._user_agent = user_agent
        self._registry = registry
        self._ticker_ciks: dict[str, str] | None = None

    def resolve_cik(self, ticker: str) -> str:
        return self._registry.primary_sec_cik(ticker, self._lookup_ticker_cik)

    def resolve_ciks(self, ticker: str) -> tuple[str, ...]:
        return self._registry.sec_ciks(ticker, self._lookup_ticker_cik)

    def _lookup_ticker_cik(self, ticker: str) -> str:
        normalized_ticker = ticker.upper()
        ticker_ciks = self._load_ticker_ciks()
        cik = ticker_ciks.get(normalized_ticker)
        if cik is None:
            msg = f"No SEC EDGAR CIK found for ticker {normalized_ticker}"
            raise TickerNotFoundError(
                msg,
            )
        return cik

    def fetch_concept(
        self,
        cik: str,
        tag: str,
        unit: str = USD_UNIT,
    ) -> list[XbrlFact]:
        url = SEC_CONCEPT_URL.format(cik=cik.zfill(10), tag=tag)
        try:
            response = self._get_json(url)
        except requests.HTTPError as error:
            if (
                error.response is not None
                and error.response.status_code == NOT_FOUND_STATUS
            ):
                return []
            msg = f"Failed to fetch SEC concept {tag}: {error}"
            raise DataSourceUnavailableError(
                msg,
            ) from error

        payload = cast("dict[str, object]", response)
        units = cast("dict[str, object]", payload.get("units", {}))
        return cast("list[XbrlFact]", units.get(unit, []))

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
            raw = self._fetch_quarterly_financials_for_cik(
                cik,
                quarter_dates,
                splits,
            )
            merged = raw if merged is None else merge_raw_financial_frames(raw, merged)
        if merged is None:
            msg = f"No SEC EDGAR CIKs resolved for ticker {ticker.upper()}"
            raise TickerNotFoundError(msg)
        return merged

    def _fetch_quarterly_financials_for_cik(
        self,
        cik: str,
        quarter_dates: list[date],
        splits: pd.Series | None,
    ) -> pd.DataFrame:
        series_by_name = {
            name: self._fetch_tag_chain(cik, spec, quarter_dates, splits)
            for name, spec in TAG_CHAINS.items()
            if name != "shares_outstanding"
        }
        series_by_name["shares_outstanding"] = self._fetch_shares_chain(
            cik,
            quarter_dates,
            splits,
        )
        return pd.DataFrame(
            {
                "date": quarter_dates,
                **{name: series.tolist() for name, series in series_by_name.items()},
            },
        )

    def fetch_financials_panel(
        self,
        ticker: str,
        start: date,
        end: date,
        splits: pd.Series | None = None,
    ) -> pd.DataFrame:
        raw = self.fetch_quarterly_financials(ticker, start, end, splits)
        return financial_panel_from_raw(raw)

    def _fetch_tag_chain(
        self,
        cik: str,
        spec: ConceptSpec,
        quarter_dates: list[date],
        splits: pd.Series | None,
    ) -> pd.Series:
        combined = pd.Series(math.nan, index=quarter_dates, dtype="float64")
        for tag in spec.tags:
            facts = self.fetch_concept(cik, tag, spec.unit)
            if facts:
                records = quarterly_facts_from_facts(facts, quarter_dates)
                values = records["value"]
                if spec.unit == PER_SHARE_UNIT:
                    values /= split_factors_for_filing_dates(
                        records["filed"],
                        splits,
                    )
                combined = combined.combine_first(values)
        return combined

    def _fetch_shares_chain(
        self,
        cik: str,
        quarter_dates: list[date],
        splits: pd.Series | None,
    ) -> pd.Series:
        for tag in TAG_CHAINS["shares_outstanding"].tags:
            facts = self.fetch_concept(cik, tag, SHARES_UNIT)
            if facts:
                records = instant_series_from_facts(
                    cast("list[InstantXbrlFact]", facts),
                    quarter_dates,
                )
                values = records["value"] * split_factors_for_filing_dates(
                    records["filed"],
                    splits,
                )
                if values.notna().any():
                    return values

        return self._fetch_tag_chain(
            cik,
            DILUTED_SHARES_FALLBACK,
            quarter_dates,
            splits,
        )

    def _load_ticker_ciks(self) -> dict[str, str]:
        if self._ticker_ciks is not None:
            return self._ticker_ciks

        payload = cast("dict[str, object]", self._get_json(SEC_TICKERS_URL))
        ticker_ciks: dict[str, str] = {}
        for entry in payload.values():
            ticker_entry = cast("dict[str, object]", entry)
            try:
                ticker = str(ticker_entry["ticker"]).upper()
                cik = str(ticker_entry["cik_str"]).zfill(10)
            except KeyError as error:
                msg = f"Malformed SEC ticker entry: {ticker_entry!r}"
                raise MalformedPayloadError(
                    msg,
                ) from error
            ticker_ciks[ticker] = cik
        self._ticker_ciks = ticker_ciks
        return ticker_ciks

    def _get_json(self, url: str) -> object:
        if not self._user_agent:
            raise DataSourceUnavailableError(MISSING_USER_AGENT_MESSAGE)
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self._user_agent},
                timeout=Settings.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except DataSourceUnavailableError:
            raise
        except requests.HTTPError:
            raise
        except (requests.RequestException, ValueError) as error:
            msg = f"Failed to fetch SEC EDGAR data: {error}"
            raise DataSourceUnavailableError(
                msg,
            ) from error

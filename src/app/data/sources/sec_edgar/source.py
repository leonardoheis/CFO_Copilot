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
    FactProvenance,
    InstantXbrlFact,
    PeriodMeasure,
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
    implied_shares_from_earnings,
    merge_raw_financial_frames,
    split_factors_for_filing_dates,
    without_implausible_counts,
)

type JsonObject = dict[str, object]

SEC_TICKERS_URL: Final = "https://www.sec.gov/files/company_tickers.json"
SEC_CONCEPT_URL: Final = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
)
NOT_FOUND_STATUS: Final = 404
MISSING_USER_AGENT_MESSAGE: Final = (
    "SEC_USER_AGENT is not set. Add it to your .env file (see .env.example)."
)


def _without_placeholder_zeros(values: pd.Series) -> pd.Series:
    """Treat a superseded tag's 0 as not-reported rather than as data.

    Returns:
        The series with zeros replaced by NaN.
    """
    return values.where(values != 0)


def _empty_chain_records(quarter_dates: list[date]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "value": math.nan,
            "filed": "",
            "period_end": None,
            "provenance": FactProvenance.MISSING,
        },
        index=quarter_dates,
    )


def _take_winning_rows(
    combined: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    prefer_largest: bool,
) -> pd.DataFrame:
    """Replace whole rows, so a value never outlives the origin it came from.

    Returns:
        ``combined`` with the candidate's rows wherever the candidate wins.
    """
    if prefer_largest:
        wins = candidate["value"].notna() & (
            combined["value"].isna() | candidate["value"].gt(combined["value"])
        )
    else:
        wins = combined["value"].isna() & candidate["value"].notna()
    return combined.mask(wins, candidate)


def _none_where_blank(filed: pd.Series) -> list[date | None]:
    """Turn the no-fact placeholder into a null, and a filing date into a date.

    Returns:
        One entry per quarter, null where nothing was filed.
    """
    return [date.fromisoformat(value) if value else None for value in filed]


def _none_where_missing(provenance: pd.Series) -> list[str | None]:
    """Turn the missing marker into a null the fallback can overwrite.

    Returns:
        One entry per quarter, null where no rule produced a value.
    """
    return [
        None if value is FactProvenance.MISSING else str(value) for value in provenance
    ]


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

        payload = cast("JsonObject", response)
        units = cast("JsonObject", payload.get("units", {}))
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
        # Revenue anchors the row: it is the figure whose filing defines which
        # period the row actually describes, so its origin is the row's origin.
        revenue_records = self._fetch_tag_chain_records(
            cik,
            TAG_CHAINS["revenue"],
            quarter_dates,
            splits,
        )
        series_by_name = {
            name: self._fetch_tag_chain(cik, spec, quarter_dates, splits)
            for name, spec in TAG_CHAINS.items()
            if name not in {"shares_outstanding", "revenue"}
        }
        series_by_name["revenue"] = revenue_records["value"]
        shares = self._fetch_shares_chain(cik, quarter_dates, splits)
        if not shares.notna().all():
            # Some filers (e.g. Google's legacy CIK) report no share-count fact
            # of any kind for their earliest quarters, but do report net income
            # and diluted EPS. Recover the implied share count for those gaps.
            implied = implied_shares_from_earnings(
                series_by_name["net_income"],
                series_by_name["eps"],
            )
            # A split-restated EPS can disagree in sign with its own net income
            # (see _fill_missing_financials), and the quotient of the two is then
            # a negative share count.
            shares = shares.combine_first(
                without_implausible_counts(implied, cik),
            )
        series_by_name["shares_outstanding"] = shares
        return pd.DataFrame(
            {
                "date": quarter_dates,
                **{name: series.tolist() for name, series in series_by_name.items()},
                # Null, not a "missing" marker: a null is what lets the vendor
                # fallback overlay its own provenance where SEC found nothing.
                "period_end": revenue_records["period_end"].tolist(),
                "financials_filed": _none_where_blank(revenue_records["filed"]),
                "financials_provenance": _none_where_missing(
                    revenue_records["provenance"],
                ),
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
        return self._fetch_tag_chain_records(cik, spec, quarter_dates, splits)["value"]

    def _fetch_tag_chain_records(
        self,
        cik: str,
        spec: ConceptSpec,
        quarter_dates: list[date],
        splits: pd.Series | None,
    ) -> pd.DataFrame:
        """Resolve a concept across its tag chain, keeping each value's origin.

        Returns:
            A frame of ``value``, ``filed``, ``period_end`` and ``provenance``,
            each row taken from whichever tag supplied the winning value.
        """
        combined = _empty_chain_records(quarter_dates)
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
                records = records.assign(
                    value=_without_placeholder_zeros(values),
                )
                combined = _take_winning_rows(
                    combined,
                    records,
                    prefer_largest=spec.prefer_largest,
                )
            if not spec.prefer_largest and combined["value"].notna().all():
                break
        return combined

    def _fetch_shares_chain(
        self,
        cik: str,
        quarter_dates: list[date],
        splits: pd.Series | None,
    ) -> pd.Series:
        combined = pd.Series(math.nan, index=quarter_dates, dtype="float64")
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
                combined = combined.combine_first(
                    without_implausible_counts(values, cik),
                )

        if combined.notna().all():
            return combined

        # Instant shares-outstanding tags cover fewer early quarters than the
        # weighted-average diluted-share duration facts, so fill any remaining
        # gaps rather than only falling back when the primary is wholly empty.
        fallback = self._fetch_diluted_shares_fallback(cik, quarter_dates, splits)
        return combined.combine_first(fallback)

    def _fetch_diluted_shares_fallback(
        self,
        cik: str,
        quarter_dates: list[date],
        splits: pd.Series | None,
    ) -> pd.Series:
        combined = pd.Series(math.nan, index=quarter_dates, dtype="float64")
        for tag in DILUTED_SHARES_FALLBACK.tags:
            facts = self.fetch_concept(cik, tag, DILUTED_SHARES_FALLBACK.unit)
            if facts:
                records = quarterly_facts_from_facts(
                    facts,
                    quarter_dates,
                    PeriodMeasure.PERIOD_AVERAGE,
                )
                values = records["value"] * split_factors_for_filing_dates(
                    records["filed"],
                    splits,
                )
                combined = combined.combine_first(
                    without_implausible_counts(values, cik),
                )
        return combined

    def _load_ticker_ciks(self) -> dict[str, str]:
        if self._ticker_ciks is not None:
            return self._ticker_ciks

        payload = cast("JsonObject", self._get_json(SEC_TICKERS_URL))
        ticker_ciks: dict[str, str] = {}
        for entry in payload.values():
            ticker_entry = cast("JsonObject", entry)
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

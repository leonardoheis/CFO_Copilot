from dataclasses import dataclass, field
from datetime import date
from typing import Final, cast

import pandas as pd
import requests

from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import COMPANY_METADATA, FINANCIAL_COLUMNS
from app.data.splits import cumulative_split_factors
from app.data.xbrl import (
    InstantXbrlFact,
    XbrlFact,
    instant_series_from_facts,
    quarterly_facts_from_facts,
)

SEC_TICKERS_URL: Final = "https://www.sec.gov/files/company_tickers.json"
SEC_CONCEPT_URL: Final = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
)
REQUEST_TIMEOUT: Final = 30
NOT_FOUND_STATUS: Final = 404
MILLIONS_DIVISOR: Final = 1_000_000
USD_UNIT: Final = "USD"
PER_SHARE_UNIT: Final = "USD/shares"
SHARES_UNIT: Final = "shares"
MISSING_USER_AGENT_MESSAGE: Final = (
    "SEC_USER_AGENT is not set. Add it to your .env file (see .env.example)."
)


@dataclass(frozen=True, slots=True)
class ConceptSpec:
    """An ordered set of us-gaap tags reported under a single XBRL unit."""

    tags: tuple[str, ...]
    unit: str = field(default=USD_UNIT)


TAG_CHAINS: Final[dict[str, ConceptSpec]] = {
    "revenue": ConceptSpec(
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenues",
        ),
    ),
    "cogs": ConceptSpec(("CostOfGoodsAndServicesSold", "CostOfRevenue")),
    "costs_and_expenses": ConceptSpec(("CostsAndExpenses",)),
    "operating_income": ConceptSpec(("OperatingIncomeLoss",)),
    "net_income": ConceptSpec(("NetIncomeLoss",)),
    "dep_amort": ConceptSpec(
        (
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "Depreciation",
        ),
    ),
    "operating_cash_flow": ConceptSpec(
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
    ),
    "capex": ConceptSpec(
        (
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquirePropertyPlantAndEquipment",
        ),
    ),
    "eps": ConceptSpec(
        ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
        unit=PER_SHARE_UNIT,
    ),
    "shares_outstanding": ConceptSpec(
        ("CommonStockSharesOutstanding",),
        unit=SHARES_UNIT,
    ),
}


class SecEdgarSource:
    def __init__(self, user_agent: str) -> None:
        self._user_agent = user_agent
        self._ticker_ciks: dict[str, str] | None = None

    def resolve_cik(self, ticker: str) -> str:
        normalized_ticker = ticker.upper()
        metadata = COMPANY_METADATA.get(normalized_ticker)
        if metadata is not None and metadata.cik:
            return metadata.cik

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
        cik = self.resolve_cik(ticker)
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
        revenue = raw["revenue"]
        cogs = raw["cogs"]
        gross_profit = revenue - cogs
        operating_income = raw["operating_income"]
        net_income = raw["net_income"]
        safe_revenue = revenue.where(revenue != 0)
        reported_opex = raw["costs_and_expenses"] - cogs
        derived_opex = revenue - operating_income - cogs
        opex = reported_opex.where(reported_opex.notna(), derived_opex)

        panel = pd.DataFrame(
            {
                "date": raw["date"],
                "revenue_usd_m": revenue / MILLIONS_DIVISOR,
                "gross_profit_usd_m": gross_profit / MILLIONS_DIVISOR,
                "opex_usd_m": opex / MILLIONS_DIVISOR,
                "operating_income_usd_m": (operating_income / MILLIONS_DIVISOR),
                "ebitda_usd_m": (operating_income + raw["dep_amort"])
                / MILLIONS_DIVISOR,
                "net_income_usd_m": net_income / MILLIONS_DIVISOR,
                "free_cash_flow_usd_m": (raw["operating_cash_flow"] - raw["capex"])
                / MILLIONS_DIVISOR,
                "gross_margin": gross_profit / safe_revenue,
                "operating_margin": operating_income / safe_revenue,
                "net_margin": net_income / safe_revenue,
                "eps": raw["eps"],
                "shares_outstanding": raw["shares_outstanding"],
            },
        )
        return panel.loc[:, ["date", *FINANCIAL_COLUMNS, "shares_outstanding"]]

    def _fetch_tag_chain(
        self,
        cik: str,
        spec: ConceptSpec,
        quarter_dates: list[date],
        splits: pd.Series | None,
    ) -> pd.Series:
        combined = pd.Series(float("nan"), index=quarter_dates, dtype="float64")
        for tag in spec.tags:
            facts = self.fetch_concept(cik, tag, spec.unit)
            if facts:
                records = quarterly_facts_from_facts(facts, quarter_dates)
                values = records["value"]
                if spec.unit == PER_SHARE_UNIT:
                    values /= self._split_factors_for_filing_dates(
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
                values = records["value"] * self._split_factors_for_filing_dates(
                    records["filed"],
                    splits,
                )
                if values.notna().any():
                    return values

        return self._fetch_tag_chain(
            cik,
            ConceptSpec(
                ("WeightedAverageNumberOfDilutedSharesOutstanding",),
                unit=SHARES_UNIT,
            ),
            quarter_dates,
            splits,
        )

    @staticmethod
    def _split_factors_for_filing_dates(
        filed_dates: pd.Series,
        splits: pd.Series | None,
    ) -> pd.Series:
        if splits is None:
            return pd.Series(1.0, index=filed_dates.index)
        parsed_dates = pd.to_datetime(filed_dates.replace({"": pd.NA}))
        valid = parsed_dates.notna()
        factors = pd.Series(1.0, index=filed_dates.index)
        if valid.any():
            factors.loc[valid] = cumulative_split_factors(
                splits,
                pd.DatetimeIndex(parsed_dates.loc[valid]),
            ).to_numpy()
        return factors

    def _load_ticker_ciks(self) -> dict[str, str]:
        if self._ticker_ciks is not None:
            return self._ticker_ciks

        payload = cast("dict[str, object]", self._get_json(SEC_TICKERS_URL))
        ticker_ciks: dict[str, str] = {}
        for entry in payload.values():
            ticker_entry = cast("dict[str, object]", entry)
            ticker = str(ticker_entry["ticker"]).upper()
            cik = str(ticker_entry["cik_str"]).zfill(10)
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
                timeout=REQUEST_TIMEOUT,
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

    @property
    def financial_columns(self) -> tuple[str, ...]:
        return FINANCIAL_COLUMNS

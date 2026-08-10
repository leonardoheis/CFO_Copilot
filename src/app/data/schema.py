from dataclasses import dataclass
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict

METADATA_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "company",
    "ticker",
    "sector",
    "is_public",
)

MACRO_COLUMNS: Final[tuple[str, ...]] = (
    "gdp_yoy",
    "fed_funds",
    "unemployment_rate",
    "cpi_yoy",
    "dxy",
    "vix",
    "wti_oil",
)

FINANCIAL_COLUMNS: Final[tuple[str, ...]] = (
    "revenue_usd_m",
    "gross_profit_usd_m",
    "opex_usd_m",
    "operating_income_usd_m",
    "ebitda_usd_m",
    "net_income_usd_m",
    "free_cash_flow_usd_m",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "eps",
)

MARKET_COLUMNS: Final[tuple[str, ...]] = (
    "stock_price_usd",
    "dividend_yield",
)

# Needs inputs from more than one source, so the pipeline derives it after the
# per-source panels are merged.
DERIVED_COLUMNS: Final[tuple[str, ...]] = ("market_cap_usd_m", "pe_ratio")

PANEL_COLUMNS: Final[tuple[str, ...]] = (
    *METADATA_COLUMNS,
    *FINANCIAL_COLUMNS,
    *MARKET_COLUMNS,
    *DERIVED_COLUMNS,
    *MACRO_COLUMNS,
)


@dataclass(frozen=True, slots=True)
class CompanyMetadata:
    company: str
    sector: str
    is_public: bool
    cik: str = ""


COMPANY_METADATA: Final[dict[str, CompanyMetadata]] = {
    "AMZN": CompanyMetadata(
        company="Amazon",
        sector="Consumer Cyclical",
        is_public=True,
        cik="0001018724",
    ),
}


class PanelRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    company: str
    ticker: str
    sector: str
    is_public: bool
    revenue_usd_m: float | None = None
    gross_profit_usd_m: float | None = None
    opex_usd_m: float | None = None
    operating_income_usd_m: float | None = None
    ebitda_usd_m: float | None = None
    net_income_usd_m: float | None = None
    free_cash_flow_usd_m: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    market_cap_usd_m: float | None = None
    stock_price_usd: float | None = None
    eps: float | None = None
    pe_ratio: float | None = None
    dividend_yield: float | None = None
    gdp_yoy: float | None = None
    fed_funds: float | None = None
    unemployment_rate: float | None = None
    cpi_yoy: float | None = None
    dxy: float | None = None
    vix: float | None = None
    wti_oil: float | None = None


def resolve_company_metadata(ticker: str) -> CompanyMetadata:
    normalized_ticker = ticker.upper()
    if normalized_ticker in COMPANY_METADATA:
        return COMPANY_METADATA[normalized_ticker]

    return CompanyMetadata(
        company=normalized_ticker,
        sector="Unknown",
        is_public=True,
    )

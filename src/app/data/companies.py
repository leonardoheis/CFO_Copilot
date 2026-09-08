from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.data.exceptions import TickerNotFoundError

CIK_LENGTH = 10


@dataclass(frozen=True, slots=True)
class CompanyPanelMetadata:
    company: str
    sector: str
    is_public: bool


@dataclass(frozen=True, slots=True)
class KnownCik:
    cik: str


@dataclass(frozen=True, slots=True)
class DualCikFiling:
    legacy_cik: str
    current_cik: str


@dataclass(frozen=True, slots=True)
class SecTickerLookup:
    """Resolve CIK from SEC company_tickers.json at runtime."""


@dataclass(frozen=True, slots=True)
class MarketFromTicker:
    """Use the requested ticker for Yahoo Finance history."""


@dataclass(frozen=True, slots=True)
class MarketWithHistoryTicker:
    history_ticker: str


@dataclass(frozen=True, slots=True)
class ScrapedCompany:
    tickers: tuple[str, ...]
    panel: CompanyPanelMetadata
    sec: KnownCik | DualCikFiling | SecTickerLookup
    market: MarketFromTicker | MarketWithHistoryTicker


class _PanelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    sector: str
    is_public: bool


class _KnownCikConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["known_cik"]
    cik: str


class _DualCikConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["dual_cik"]
    legacy_cik: str
    current_cik: str


class _SecTickerLookupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sec_ticker_lookup"]


class _FromTickerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["from_ticker"]


class _HistoryTickerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["history_ticker"]
    history_ticker: str


class _CompanyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: tuple[str, ...]
    panel: _PanelConfig
    sec: _KnownCikConfig | _DualCikConfig | _SecTickerLookupConfig = Field(
        discriminator="type",
    )
    market: _FromTickerConfig | _HistoryTickerConfig = Field(
        discriminator="type",
    )

    @field_validator("tickers")
    @classmethod
    def normalize_tickers(cls, tickers: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(ticker.upper() for ticker in tickers)
        if not normalized or any(not ticker for ticker in normalized):
            msg = "tickers must contain at least one non-empty ticker"
            raise ValueError(msg)
        return normalized


class _RegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    companies: tuple[_CompanyConfig, ...]


REGISTRY_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "config" / "companies.yaml"
)


def _validate_cik(cik: str) -> str:
    if len(cik) != CIK_LENGTH or not cik.isdigit():
        msg = "CIK must contain exactly 10 digits"
        raise ValueError(msg)
    return cik


def _to_domain_company(config: _CompanyConfig) -> ScrapedCompany:
    panel = CompanyPanelMetadata(
        company=config.panel.company,
        sector=config.panel.sector,
        is_public=config.panel.is_public,
    )
    match config.sec:
        case _KnownCikConfig(cik=cik):
            sec: KnownCik | DualCikFiling | SecTickerLookup = KnownCik(
                cik=_validate_cik(cik),
            )
        case _DualCikConfig(legacy_cik=legacy_cik, current_cik=current_cik):
            sec = DualCikFiling(
                legacy_cik=_validate_cik(legacy_cik),
                current_cik=_validate_cik(current_cik),
            )
        case _SecTickerLookupConfig():
            sec = SecTickerLookup()

    match config.market:
        case _FromTickerConfig():
            market: MarketFromTicker | MarketWithHistoryTicker = MarketFromTicker()
        case _HistoryTickerConfig(history_ticker=history_ticker):
            market = MarketWithHistoryTicker(
                history_ticker=history_ticker.upper(),
            )

    return ScrapedCompany(
        tickers=config.tickers,
        panel=panel,
        sec=sec,
        market=market,
    )


def load_company_registry(path: Path = REGISTRY_PATH) -> tuple[ScrapedCompany, ...]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = _RegistryConfig.model_validate(raw)
        companies = tuple(_to_domain_company(item) for item in config.companies)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        msg = f"Invalid company registry {path}: {error}"
        raise ValueError(msg) from error

    tickers = [ticker for company in companies for ticker in company.tickers]
    duplicates = {ticker for ticker in tickers if tickers.count(ticker) > 1}
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        msg_0 = f"Duplicate company ticker aliases: {duplicate_list}"
        raise ValueError(msg_0)
    return companies


SCRAPED_COMPANIES: Final[tuple[ScrapedCompany, ...]] = load_company_registry()


def _build_ticker_index(
    companies: tuple[ScrapedCompany, ...],
) -> dict[str, ScrapedCompany]:
    index: dict[str, ScrapedCompany] = {}
    for company in companies:
        for ticker in company.tickers:
            index[ticker] = company
    return index


TICKER_INDEX: Final[dict[str, ScrapedCompany]] = _build_ticker_index(SCRAPED_COMPANIES)


def resolve_scraped_company(ticker: str) -> ScrapedCompany:
    normalized_ticker = ticker.upper()
    if normalized_ticker in TICKER_INDEX:
        return TICKER_INDEX[normalized_ticker]

    return ScrapedCompany(
        tickers=(normalized_ticker,),
        panel=CompanyPanelMetadata(
            company=normalized_ticker,
            sector="Unknown",
            is_public=True,
        ),
        sec=SecTickerLookup(),
        market=MarketFromTicker(),
    )


def resolve_company_metadata(ticker: str) -> CompanyPanelMetadata:
    return resolve_scraped_company(ticker).panel


def resolve_market_history_tickers(ticker: str) -> tuple[str, ...]:
    company = resolve_scraped_company(ticker)
    normalized_ticker = ticker.upper()
    tickers: list[str] = [normalized_ticker]
    match company.market:
        case MarketWithHistoryTicker(history_ticker=history_ticker):
            tickers.append(history_ticker)
        case MarketFromTicker():
            pass
    return tuple(dict.fromkeys(tickers))


def resolve_sec_ciks(
    ticker: str,
    lookup_cik: Callable[[str], str],
) -> tuple[str, ...]:
    company = resolve_scraped_company(ticker)
    normalized_ticker = ticker.upper()
    match company.sec:
        case DualCikFiling(legacy_cik=legacy_cik, current_cik=current_cik):
            return (legacy_cik, current_cik)
        case KnownCik(cik=cik):
            return (cik,)
        case SecTickerLookup():
            return (lookup_cik(normalized_ticker),)


def resolve_primary_sec_cik(
    ticker: str,
    lookup_cik: Callable[[str], str],
) -> str:
    ciks = resolve_sec_ciks(ticker, lookup_cik)
    if not ciks:
        msg = f"No SEC EDGAR CIK found for ticker {ticker.upper()}"
        raise TickerNotFoundError(msg)
    return ciks[-1]

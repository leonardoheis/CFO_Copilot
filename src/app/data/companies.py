from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, assert_never

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


def _validate_cik(cik: str) -> str:
    if len(cik) != CIK_LENGTH or not cik.isdigit():
        msg = f"CIK must contain exactly {CIK_LENGTH} digits"
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
        case _ as unreachable:
            assert_never(unreachable)

    match config.market:
        case _FromTickerConfig():
            market: MarketFromTicker | MarketWithHistoryTicker = MarketFromTicker()
        case _HistoryTickerConfig(history_ticker=history_ticker):
            market = MarketWithHistoryTicker(
                history_ticker=history_ticker.upper(),
            )
        case _ as unreachable_market:
            assert_never(unreachable_market)

    return ScrapedCompany(
        tickers=config.tickers,
        panel=panel,
        sec=sec,
        market=market,
    )


def load_company_registry(path: Path) -> tuple[ScrapedCompany, ...]:
    """Load and validate every company profile from a YAML registry file.

    Returns:
        A tuple of validated company profiles.

    Raises:
        ValueError: If the file is unreadable, malformed, or has duplicate tickers.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = _RegistryConfig.model_validate(raw)
        companies = tuple(_to_domain_company(item) for item in config.companies)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        msg = f"Invalid company registry {path}: {error}"
        raise ValueError(msg) from error

    ticker_counts = Counter(
        ticker for company in companies for ticker in company.tickers
    )
    duplicates = sorted(ticker for ticker, count in ticker_counts.items() if count > 1)
    if duplicates:
        duplicate_msg = f"Duplicate company ticker aliases: {', '.join(duplicates)}"
        raise ValueError(duplicate_msg)
    return companies


class CompanyRegistry:
    """Resolve ingestion rules for a ticker from a loaded company registry."""

    def __init__(self, companies: tuple[ScrapedCompany, ...]) -> None:
        self._companies = companies
        self._index: dict[str, ScrapedCompany] = {
            ticker: company for company in companies for ticker in company.tickers
        }

    @classmethod
    def from_path(cls, path: Path) -> "CompanyRegistry":
        """Build a registry from a YAML configuration file.

        Returns:
            A registry holding every validated company profile in the file.
        """
        return cls(load_company_registry(path))

    @property
    def companies(self) -> tuple[ScrapedCompany, ...]:
        return self._companies

    def scraped_company(self, ticker: str) -> ScrapedCompany:
        """Return the profile for a ticker, falling back to runtime lookup.

        Returns:
            The configured profile, or a default profile for unknown tickers.
        """
        normalized_ticker = ticker.upper()
        known_company = self._index.get(normalized_ticker)
        if known_company is not None:
            return known_company

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

    def company_metadata(self, ticker: str) -> CompanyPanelMetadata:
        """Return the panel metadata for a ticker.

        Returns:
            The company name, sector, and public status.
        """
        return self.scraped_company(ticker).panel

    def market_history_tickers(self, ticker: str) -> tuple[str, ...]:
        """Return the Yahoo Finance symbols to try, current symbol first.

        Returns:
            A de-duplicated tuple of market tickers.
        """
        company = self.scraped_company(ticker)
        tickers: list[str] = [ticker.upper()]
        match company.market:
            case MarketWithHistoryTicker(history_ticker=history_ticker):
                tickers.append(history_ticker)
            case MarketFromTicker():
                pass
            case _ as unreachable:
                assert_never(unreachable)
        return tuple(dict.fromkeys(tickers))

    def sec_ciks(
        self,
        ticker: str,
        lookup_cik: Callable[[str], str],
    ) -> tuple[str, ...]:
        """Return every SEC CIK for a ticker, oldest filer first.

        Returns:
            A tuple of zero-padded CIK strings.
        """
        company = self.scraped_company(ticker)
        match company.sec:
            case DualCikFiling(legacy_cik=legacy_cik, current_cik=current_cik):
                return (legacy_cik, current_cik)
            case KnownCik(cik=cik):
                return (cik,)
            case SecTickerLookup():
                return (lookup_cik(ticker.upper()),)
            case _ as unreachable:
                assert_never(unreachable)

    def primary_sec_cik(
        self,
        ticker: str,
        lookup_cik: Callable[[str], str],
    ) -> str:
        """Return the current SEC CIK for a ticker.

        Returns:
            The most recent CIK, which is the last entry for dual filers.
        """
        return self.sec_ciks(ticker, lookup_cik)[-1]

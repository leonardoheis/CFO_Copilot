from pathlib import Path

import pytest

from app.data.companies import (
    SCRAPED_COMPANIES,
    DualCikFiling,
    KnownCik,
    MarketFromTicker,
    MarketWithHistoryTicker,
    SecTickerLookup,
    load_company_registry,
    resolve_company_metadata,
    resolve_market_history_tickers,
    resolve_scraped_company,
    resolve_sec_ciks,
)


def test_scraped_companies_lists_each_profile_once() -> None:
    company_names = {company.panel.company for company in SCRAPED_COMPANIES}

    assert company_names == {
        "Amazon",
        "Alphabet",
    }
    assert len(company_names) == len(SCRAPED_COMPANIES)


def test_resolve_company_metadata_for_googl() -> None:
    metadata = resolve_company_metadata("googl")

    assert metadata.company == "Alphabet"
    assert metadata.sector == "Communication Services"
    assert metadata.is_public is True


def test_resolve_scraped_company_for_alphabet_tickers_share_profile() -> None:
    googl = resolve_scraped_company("GOOGL")
    goog = resolve_scraped_company("GOOG")

    assert googl is goog
    assert isinstance(googl.sec, DualCikFiling)
    assert googl.sec.legacy_cik == "0001288776"
    assert googl.sec.current_cik == "0001652044"
    assert isinstance(googl.market, MarketWithHistoryTicker)
    assert googl.market.history_ticker == "GOOG"


def test_resolve_scraped_company_for_amazon_uses_known_cik() -> None:
    amazon = resolve_scraped_company("AMZN")

    assert isinstance(amazon.sec, KnownCik)
    assert amazon.sec.cik == "0001018724"
    assert isinstance(amazon.market, MarketFromTicker)


def test_resolve_scraped_company_for_unknown_ticker_uses_runtime_lookup() -> None:
    unknown = resolve_scraped_company("MSFT")

    assert isinstance(unknown.sec, SecTickerLookup)
    assert isinstance(unknown.market, MarketFromTicker)
    assert unknown.panel.company == "MSFT"
    assert unknown.panel.sector == "Unknown"


def test_resolve_sec_ciks_for_alphabet_returns_legacy_then_current() -> None:
    assert resolve_sec_ciks("GOOGL", lambda _ticker: "0000000000") == (
        "0001288776",
        "0001652044",
    )


def test_resolve_market_history_tickers_for_googl_includes_goog_fallback() -> None:
    assert resolve_market_history_tickers("GOOGL") == ("GOOGL", "GOOG")


def test_resolve_market_history_tickers_for_goog_does_not_duplicate() -> None:
    assert resolve_market_history_tickers("GOOG") == ("GOOG",)


def test_load_company_registry_supports_runtime_sec_lookup(tmp_path: Path) -> None:
    registry = tmp_path / "companies.yaml"
    registry.write_text(
        """
companies:
  - tickers: [MSFT]
    panel:
      company: Microsoft
      sector: Technology
      is_public: true
    sec:
      type: sec_ticker_lookup
    market:
      type: from_ticker
""",
        encoding="utf-8",
    )

    companies = load_company_registry(registry)

    assert len(companies) == 1
    assert isinstance(companies[0].sec, SecTickerLookup)


def test_load_company_registry_rejects_duplicate_tickers(tmp_path: Path) -> None:
    registry = tmp_path / "companies.yaml"
    registry.write_text(
        """
companies:
  - tickers: [DUP]
    panel: {company: First, sector: Technology, is_public: true}
    sec: {type: known_cik, cik: "0000000001"}
    market: {type: from_ticker}
  - tickers: [DUP]
    panel: {company: Second, sector: Technology, is_public: true}
    sec: {type: known_cik, cik: "0000000002"}
    market: {type: from_ticker}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate company ticker aliases: DUP"):
        load_company_registry(registry)


def test_load_company_registry_rejects_malformed_cik(tmp_path: Path) -> None:
    registry = tmp_path / "companies.yaml"
    registry.write_text(
        """
companies:
  - tickers: [BAD]
    panel: {company: Bad, sector: Technology, is_public: true}
    sec: {type: known_cik, cik: "123"}
    market: {type: from_ticker}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="CIK must contain exactly 10 digits"):
        load_company_registry(registry)

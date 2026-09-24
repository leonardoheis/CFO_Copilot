from pathlib import Path

from app.data.companies import CompanyRegistry
from app.data.sources import (
    AlphaVantageSource,
    FredSource,
    SecEdgarSource,
    YfinanceSource,
)
from app.data.sources_bundle import IngestionSources
from app.injections.production import Container

TEST_USER_AGENT = "CFO Copilot tests@example.com"


def _bundle(
    registry: CompanyRegistry,
    alpha_vantage: AlphaVantageSource | None = None,
) -> tuple[IngestionSources, FredSource, SecEdgarSource]:
    fred = FredSource(api_key="test-key")
    sec_edgar = SecEdgarSource(user_agent=TEST_USER_AGENT, registry=registry)
    sources = IngestionSources.from_sources(
        fred=fred,
        yfinance=YfinanceSource(registry=registry),
        sec_edgar=sec_edgar,
        registry=registry,
        alpha_vantage=alpha_vantage,
    )
    return sources, fred, sec_edgar


def test_from_sources_binds_each_sources_fetch_method(
    company_registry: CompanyRegistry,
) -> None:
    sources, fred, sec_edgar = _bundle(company_registry)

    assert sources.fetch_macro_panel == fred.fetch_macro_panel
    assert sources.fetch_sec_financials == sec_edgar.fetch_financials_panel


def test_without_alpha_vantage_there_is_no_fallback(
    company_registry: CompanyRegistry,
) -> None:
    sources, _, _ = _bundle(company_registry)

    assert sources.fetch_fallback_financials is None


def test_alpha_vantage_becomes_the_fallback(
    company_registry: CompanyRegistry,
    tmp_path: Path,
) -> None:
    alpha_vantage = AlphaVantageSource("test-key", tmp_path)

    sources, _, _ = _bundle(company_registry, alpha_vantage)

    assert sources.fetch_fallback_financials == alpha_vantage.fetch_financials_panel


def test_the_container_builds_the_bundle() -> None:
    sources = Container().ingestion_sources()

    assert callable(sources.fetch_macro_panel)
    assert callable(sources.fetch_sec_financials)

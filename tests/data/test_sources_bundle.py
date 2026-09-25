from datetime import date
from unittest.mock import create_autospec

import pandas as pd

from app.data.companies import CompanyRegistry
from app.data.sources import (
    AlphaVantageSource,
    FredSource,
    SecEdgarSource,
    YfinanceSource,
)
from app.data.sources_bundle import IngestionSources
from app.injections.production import Container

START = date(2020, 3, 31)
END = date(2020, 6, 30)
NO_SPLITS = pd.Series(dtype=float)


def _bundle(
    registry: CompanyRegistry,
    *,
    fred: FredSource,
    sec_edgar: SecEdgarSource,
    alpha_vantage: AlphaVantageSource | None = None,
) -> IngestionSources:
    return IngestionSources.from_sources(
        fred=fred,
        yfinance=YfinanceSource(registry=registry),
        sec_edgar=sec_edgar,
        registry=registry,
        alpha_vantage=alpha_vantage,
    )


def test_from_sources_binds_each_sources_fetch_method(
    company_registry: CompanyRegistry,
) -> None:
    fred = create_autospec(FredSource, instance=True)
    sec_edgar = create_autospec(SecEdgarSource, instance=True)
    sources = _bundle(company_registry, fred=fred, sec_edgar=sec_edgar)

    sources.fetch_macro_panel(START, END)
    sources.fetch_sec_financials("AAA", START, END, NO_SPLITS)

    fred.fetch_macro_panel.assert_called_once_with(START, END)
    sec_edgar.fetch_financials_panel.assert_called_once_with(
        "AAA", START, END, NO_SPLITS
    )


def test_without_alpha_vantage_there_is_no_fallback(
    company_registry: CompanyRegistry,
) -> None:
    sources = _bundle(
        company_registry,
        fred=create_autospec(FredSource, instance=True),
        sec_edgar=create_autospec(SecEdgarSource, instance=True),
    )

    assert sources.fetch_fallback_financials is None


def test_alpha_vantage_becomes_the_fallback(
    company_registry: CompanyRegistry,
) -> None:
    alpha_vantage = create_autospec(AlphaVantageSource, instance=True)
    sources = _bundle(
        company_registry,
        fred=create_autospec(FredSource, instance=True),
        sec_edgar=create_autospec(SecEdgarSource, instance=True),
        alpha_vantage=alpha_vantage,
    )

    assert sources.fetch_fallback_financials is not None
    sources.fetch_fallback_financials("AAA", START, END)

    alpha_vantage.fetch_financials_panel.assert_called_once_with("AAA", START, END)


def test_the_container_builds_the_bundle() -> None:
    sources = Container().ingestion_sources()

    assert callable(sources.fetch_macro_panel)
    assert callable(sources.fetch_sec_financials)

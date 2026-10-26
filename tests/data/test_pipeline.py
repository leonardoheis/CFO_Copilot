import logging
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fredapi import Fred

from app.data.companies import CompanyRegistry
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError
from app.data.pipeline import (
    build_panel_skeleton,
    merge_panel,
    resolve_date_range,
    write_panel,
)
from app.data.schema import (
    COST_OF_REVENUE_COLUMNS,
    FINANCIAL_COLUMNS,
    FRED_MACRO_COLUMNS,
    MARKET_COLUMNS,
    PANEL_COLUMNS,
)
from app.data.sources import FredSource, SecEdgarSource, YfinanceSource
from app.data.sources_bundle import IngestionSources
from app.settings import Settings

TEST_USER_AGENT = "CFO Copilot tests test@example.com"
TEST_QUARTER_DATES = quarter_end_dates(date(2020, 1, 1), date(2020, 6, 30))
EXPECTED_REVENUE = 1_000.0
FISCAL_OFFSET_DAYS = 31
EXPECTED_STOCK_PRICE = 100.0
EXPECTED_FED_FUNDS = 1.0
EXPECTED_SP500 = 0.05
EXPECTED_EPS = 5.0
EXPECTED_SPLIT_FACTOR = 20.0
EXPECTED_ADJUSTED_EPS = EXPECTED_EPS / EXPECTED_SPLIT_FACTOR
EXPECTED_PE_RATIO = EXPECTED_STOCK_PRICE / EXPECTED_ADJUSTED_EPS
EXPECTED_SHARES = 1_000_000_000.0
EXPECTED_FALLBACK_EBITDA = 275.0


def fake_macro_panel(_start: date, _end: date) -> pd.DataFrame:
    values = {column: [math.nan] * 2 for column in FRED_MACRO_COLUMNS}
    values["fed_funds"] = [EXPECTED_FED_FUNDS, 2.0]
    return pd.DataFrame({"date": TEST_QUARTER_DATES, **values})


class FakeMarketSource:
    @staticmethod
    def fetch_market_panel(
        _ticker: str,
        _start: date,
        _end: date,
    ) -> pd.DataFrame:
        values = {column: [math.nan] * 2 for column in MARKET_COLUMNS}
        values["stock_price_usd"] = [EXPECTED_STOCK_PRICE, 110.0]
        return pd.DataFrame({"date": TEST_QUARTER_DATES, **values})

    @staticmethod
    def fetch_index_return_panel(_start: date, _end: date) -> pd.DataFrame:
        return pd.DataFrame(
            {"date": TEST_QUARTER_DATES, "sp500_return_lag1": [EXPECTED_SP500, 0.02]},
        )

    @staticmethod
    def fetch_splits(
        _ticker: str,
    ) -> pd.Series:
        return pd.Series(dtype=float)


def fake_sec_financials(
    _ticker: str,
    _start: date,
    _end: date,
    _splits: pd.Series,
) -> pd.DataFrame:
    values = {column: [math.nan] * 2 for column in FINANCIAL_COLUMNS}
    values["revenue_usd_m"] = [EXPECTED_REVENUE, 1_100.0]
    values["net_income_usd_m"] = [100.0, 110.0]
    values["eps"] = [EXPECTED_ADJUSTED_EPS, -1.0]
    return pd.DataFrame(
        {
            "date": TEST_QUARTER_DATES,
            **values,
            "shares_outstanding": [EXPECTED_SHARES] * 2,
            "period_end": TEST_QUARTER_DATES,
            "financials_filed": TEST_QUARTER_DATES,
            "financials_provenance": ["native"] * 2,
        },
    )


def fake_fiscal_sec_financials(
    _ticker: str,
    _start: date,
    _end: date,
    _splits: pd.Series,
) -> pd.DataFrame:
    """A filer whose quarters end a month after the calendar quarter they land in.

    Returns:
        A raw financials frame whose period ends are offset from their slots.
    """
    values = {column: [math.nan] * 2 for column in FINANCIAL_COLUMNS}
    values["revenue_usd_m"] = [EXPECTED_REVENUE, 1_100.0]
    period_ends = [
        quarter + timedelta(days=FISCAL_OFFSET_DAYS) for quarter in TEST_QUARTER_DATES
    ]
    return pd.DataFrame(
        {
            "date": TEST_QUARTER_DATES,
            **values,
            "shares_outstanding": [EXPECTED_SHARES] * 2,
            "period_end": period_ends,
            "financials_filed": period_ends,
            "financials_provenance": ["native"] * 2,
        },
    )


def fake_fallback_financials(
    _ticker: str,
    _start: date,
    _end: date,
) -> pd.DataFrame:
    values = {column: [math.nan] * 2 for column in FINANCIAL_COLUMNS}
    values["revenue_usd_m"] = [900.0, 950.0]
    values["ebitda_usd_m"] = [EXPECTED_FALLBACK_EBITDA, 300.0]
    values["eps"] = [10.0, 2.0]
    return pd.DataFrame(
        {
            "date": TEST_QUARTER_DATES,
            **values,
            "shares_outstanding": [900_000_000.0] * 2,
            "period_end": TEST_QUARTER_DATES,
            "financials_filed": [None] * 2,
            "financials_provenance": ["alpha_vantage"] * 2,
        },
    )


def failing_macro_panel(_start: date, _end: date) -> pd.DataFrame:
    msg = "macro source unavailable"
    raise DataSourceUnavailableError(msg)


def test_resolve_date_range_defaults_to_twenty_years() -> None:
    start, end = resolve_date_range(None, date(2026, 6, 30))

    assert end == date(2026, 6, 30)
    assert start == date(2006, 6, 30)


def test_quarter_end_dates_returns_quarterly_periods() -> None:
    quarter_dates = quarter_end_dates(date(2020, 1, 1), date(2020, 12, 31))

    assert quarter_dates == [
        date(2020, 3, 31),
        date(2020, 6, 30),
        date(2020, 9, 30),
        date(2020, 12, 31),
    ]


def test_build_panel_skeleton_has_expected_columns_and_metadata(
    company_registry: CompanyRegistry,
) -> None:
    start = date(2020, 1, 1)
    end = date(2020, 6, 30)
    panel = build_panel_skeleton("AMZN", start, end, company_registry)
    expected_rows = len(quarter_end_dates(start, end))

    assert list(panel.columns) == list(PANEL_COLUMNS)
    assert len(panel) == expected_rows
    assert panel.loc[0, "company"] == "Amazon"
    assert panel.loc[0, "ticker"] == "AMZN"
    assert panel.loc[0, "sector"] == "Consumer Cyclical"
    assert bool(panel.loc[0, "is_public"]) is True
    assert pd.isna(panel.loc[0, "revenue_usd_m"])


def test_merge_panel_fills_columns_from_every_source(
    company_registry: CompanyRegistry,
) -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=company_registry,
        ),
    )

    assert list(panel.columns) == list(PANEL_COLUMNS)
    assert panel.loc[0, "company"] == "Amazon"
    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(EXPECTED_REVENUE)
    assert panel.loc[0, "stock_price_usd"] == pytest.approx(EXPECTED_STOCK_PRICE)
    assert panel.loc[0, "fed_funds"] == pytest.approx(EXPECTED_FED_FUNDS)
    assert panel.loc[0, "sp500_return_lag1"] == pytest.approx(EXPECTED_SP500)
    assert panel.loc[0, "eps"] == pytest.approx(EXPECTED_ADJUSTED_EPS)


def test_merge_panel_derives_pe_ratio_from_price_and_earnings(
    company_registry: CompanyRegistry,
) -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=company_registry,
        ),
    )

    assert panel.loc[0, "pe_ratio"] == pytest.approx(EXPECTED_PE_RATIO)
    assert pd.isna(panel.loc[1, "pe_ratio"])


def test_merge_panel_fills_only_missing_sec_values_from_fallback(
    company_registry: CompanyRegistry,
) -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=company_registry,
            fetch_fallback_financials=fake_fallback_financials,
        ),
    )

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(EXPECTED_REVENUE)
    assert panel.loc[0, "ebitda_usd_m"] == pytest.approx(EXPECTED_FALLBACK_EBITDA)
    assert panel.loc[0, "eps"] == pytest.approx(EXPECTED_ADJUSTED_EPS)
    assert panel.loc[1, "eps"] == pytest.approx(2.0)


def fake_fallback_with_gross_profit(
    ticker: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    return fake_fallback_financials(ticker, start, end).assign(
        gross_profit_usd_m=[880.0, 930.0],
        gross_margin=[0.98, 0.98],
        opex_usd_m=[800.0, 850.0],
        operating_income_usd_m=[80.0, 80.0],
    )


def test_merge_panel_leaves_cost_of_revenue_columns_empty_when_declared(
    company_registry: CompanyRegistry,
) -> None:
    """UNH files no cost of revenue; Alpha Vantage must not fill one in."""
    panel = merge_panel(
        ticker="UNH",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=company_registry,
            fetch_fallback_financials=fake_fallback_with_gross_profit,
        ),
    )

    assert panel[list(COST_OF_REVENUE_COLUMNS)].isna().all().all()
    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(EXPECTED_REVENUE)
    assert panel["operating_income_usd_m"].tolist() == [80.0, 80.0]


def test_merge_panel_leaves_only_opex_empty_when_opex_is_unreliable(
    company_registry: CompanyRegistry,
) -> None:
    """GE's opex cannot be rebuilt from SEC; its gross profit can."""
    panel = merge_panel(
        ticker="GE",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=company_registry,
            fetch_fallback_financials=fake_fallback_with_gross_profit,
        ),
    )

    assert panel["opex_usd_m"].isna().all()
    assert panel["gross_profit_usd_m"].tolist() == [880.0, 930.0]


def test_merge_panel_withholds_a_declared_quarter_even_from_the_fallback(
    tmp_path: Path,
) -> None:
    """OXY 2025-Q4 mixes bases; Alpha Vantage must not fill it back in."""
    registry_path = tmp_path / "companies.yaml"
    registry_path.write_text(
        """
companies:
  - tickers: [WHL]
    panel:
      company: Withheld
      sector: Energy
      is_public: true
      withheld_quarters: {2020-03-31: full year minus nine months on another basis}
    sec: {type: known_cik, cik: "0000000001"}
    market: {type: from_ticker}
""",
        encoding="utf-8",
    )

    panel = merge_panel(
        ticker="WHL",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=CompanyRegistry.from_path(registry_path),
            fetch_fallback_financials=fake_fallback_financials,
        ),
    )

    assert panel.loc[0, list(FINANCIAL_COLUMNS)].isna().all()
    assert panel.loc[1, "revenue_usd_m"] == pytest.approx(1_100.0)
    assert panel.loc[0, "stock_price_usd"] == pytest.approx(EXPECTED_STOCK_PRICE)


def test_merge_panel_keeps_fallback_gross_profit_for_other_companies(
    company_registry: CompanyRegistry,
) -> None:
    """The accepted risk: elsewhere Alpha Vantage still fills the gap."""
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=company_registry,
            fetch_fallback_financials=fake_fallback_with_gross_profit,
        ),
    )

    assert panel["gross_profit_usd_m"].tolist() == [880.0, 930.0]


def test_merge_panel_warns_when_gaps_remain_without_a_fallback(
    company_registry: CompanyRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        panel = merge_panel(
            ticker="AMZN",
            start=date(2020, 1, 1),
            end=date(2020, 6, 30),
            sources=IngestionSources(
                fetch_macro_panel=fake_macro_panel,
                yfinance=FakeMarketSource(),
                fetch_sec_financials=fake_sec_financials,
                registry=company_registry,
            ),
        )

    assert pd.isna(panel.loc[0, "ebitda_usd_m"])
    assert "No financials fallback configured for AMZN" in caplog.text


def test_merge_panel_adjusts_eps_to_current_share_basis(
    company_registry: CompanyRegistry,
) -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_sec_financials,
            registry=company_registry,
        ),
    )

    assert panel.loc[0, "eps"] == pytest.approx(EXPECTED_ADJUSTED_EPS)


def test_merge_panel_propagates_source_errors(
    company_registry: CompanyRegistry,
) -> None:
    start, end = date(2020, 1, 1), date(2020, 6, 30)
    sources = IngestionSources(
        fetch_macro_panel=failing_macro_panel,
        yfinance=FakeMarketSource(),
        fetch_sec_financials=fake_sec_financials,
        registry=company_registry,
    )

    with pytest.raises(DataSourceUnavailableError, match="macro source unavailable"):
        merge_panel(ticker="AMZN", start=start, end=end, sources=sources)


@pytest.mark.vcr
def test_merge_panel_returns_panel_after_all_sources_are_implemented(
    company_registry: CompanyRegistry,
) -> None:
    fred = FredSource(client=Fred(api_key=Settings.FRED_API_KEY or "test-key"))
    sec_edgar = SecEdgarSource(
        user_agent=Settings.SEC_USER_AGENT or TEST_USER_AGENT,
        registry=company_registry,
        timeout=Settings.REQUEST_TIMEOUT,
    )
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fred.fetch_macro_panel,
            yfinance=YfinanceSource(registry=company_registry),
            fetch_sec_financials=sec_edgar.fetch_financials_panel,
            registry=company_registry,
        ),
    )

    assert list(panel.columns) == list(PANEL_COLUMNS)
    assert len(panel) == len(quarter_end_dates(date(2020, 1, 1), date(2020, 6, 30)))
    assert panel["revenue_usd_m"].notna().any()
    assert panel["stock_price_usd"].notna().any()
    assert panel["fed_funds"].notna().any()
    assert panel["eps"].notna().any()
    assert panel["pe_ratio"].notna().any()


def test_merge_panel_records_how_far_a_period_end_sits_from_its_quarter(
    company_registry: CompanyRegistry,
) -> None:
    """A fiscal row must be identifiable from the panel without re-querying SEC."""
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fetch_macro_panel=fake_macro_panel,
            yfinance=FakeMarketSource(),
            fetch_sec_financials=fake_fiscal_sec_financials,
            registry=company_registry,
        ),
    )

    assert panel["period_end_offset_days"].tolist() == [FISCAL_OFFSET_DAYS] * 2
    assert panel["financials_provenance"].tolist() == ["native"] * 2


def test_write_panel_creates_the_missing_directory(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "processed" / "AAPL_panel.parquet"

    write_panel(pd.DataFrame({"revenue_usd_m": [1.0]}), output_path)

    assert output_path.is_file()

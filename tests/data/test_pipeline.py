from datetime import date

import pandas as pd
import pytest

from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError
from app.data.pipeline import (
    build_panel_skeleton,
    merge_panel,
    most_recent_completed_quarter,
    resolve_date_range,
)
from app.data.schema import (
    FINANCIAL_COLUMNS,
    MACRO_COLUMNS,
    MARKET_COLUMNS,
    PANEL_COLUMNS,
)
from app.data.sources import FredSource, SecEdgarSource, YfinanceSource
from app.data.sources_bundle import IngestionSources
from app.settings import Settings

TEST_USER_AGENT = "CFO Copilot tests test@example.com"
TEST_QUARTER_DATES = quarter_end_dates(date(2020, 1, 1), date(2020, 6, 30))
EXPECTED_REVENUE = 1_000.0
EXPECTED_STOCK_PRICE = 100.0
EXPECTED_FED_FUNDS = 1.0
EXPECTED_EPS = 5.0
EXPECTED_SPLIT_FACTOR = 20.0
EXPECTED_ADJUSTED_EPS = EXPECTED_EPS / EXPECTED_SPLIT_FACTOR
EXPECTED_PE_RATIO = EXPECTED_STOCK_PRICE / EXPECTED_ADJUSTED_EPS
EXPECTED_SHARES = 1_000_000_000.0


class FakeMacroSource:
    @staticmethod
    def fetch_macro_panel(_start: date, _end: date) -> pd.DataFrame:
        values = {column: [float("nan")] * 2 for column in MACRO_COLUMNS}
        values["fed_funds"] = [EXPECTED_FED_FUNDS, 2.0]
        return pd.DataFrame({"date": TEST_QUARTER_DATES, **values})


class FakeMarketSource:
    @staticmethod
    def fetch_market_panel(
        _ticker: str,
        _start: date,
        _end: date,
    ) -> pd.DataFrame:
        values = {column: [float("nan")] * 2 for column in MARKET_COLUMNS}
        values["stock_price_usd"] = [EXPECTED_STOCK_PRICE, 110.0]
        return pd.DataFrame({"date": TEST_QUARTER_DATES, **values})

    @staticmethod
    def fetch_splits(
        _ticker: str,
    ) -> pd.Series:
        return pd.Series(dtype=float)


class FakeFinancialsSource:
    @staticmethod
    def fetch_financials_panel(
        _ticker: str,
        _start: date,
        _end: date,
        _splits: pd.Series,
    ) -> pd.DataFrame:
        values = {column: [float("nan")] * 2 for column in FINANCIAL_COLUMNS}
        values["revenue_usd_m"] = [EXPECTED_REVENUE, 1_100.0]
        values["eps"] = [EXPECTED_ADJUSTED_EPS, -1.0]
        return pd.DataFrame(
            {
                "date": TEST_QUARTER_DATES,
                **values,
                "shares_outstanding": [EXPECTED_SHARES] * 2,
            },
        )


class FailingMacroSource:
    @staticmethod
    def fetch_macro_panel(_start: date, _end: date) -> pd.DataFrame:
        msg = "macro source unavailable"
        raise DataSourceUnavailableError(msg)


def test_most_recent_completed_quarter_for_august() -> None:
    assert most_recent_completed_quarter(date(2026, 8, 9)) == date(2026, 6, 30)


def test_resolve_date_range_defaults_to_twenty_years() -> None:
    start, end = resolve_date_range(None, date(2026, 6, 30))

    assert end == date(2026, 6, 30)
    assert start == date(2008, 4, 1)


def test_quarter_end_dates_returns_quarterly_periods() -> None:
    quarter_dates = quarter_end_dates(date(2020, 1, 1), date(2020, 12, 31))

    assert quarter_dates == [
        date(2020, 3, 31),
        date(2020, 6, 30),
        date(2020, 9, 30),
        date(2020, 12, 31),
    ]


def test_build_panel_skeleton_has_expected_columns_and_metadata() -> None:
    start = date(2020, 1, 1)
    end = date(2020, 6, 30)
    panel = build_panel_skeleton("AMZN", start, end)
    expected_rows = len(quarter_end_dates(start, end))

    assert list(panel.columns) == list(PANEL_COLUMNS)
    assert len(panel) == expected_rows
    assert panel.loc[0, "company"] == "Amazon"
    assert panel.loc[0, "ticker"] == "AMZN"
    assert panel.loc[0, "sector"] == "Consumer Cyclical"
    assert bool(panel.loc[0, "is_public"]) is True
    assert pd.isna(panel.loc[0, "revenue_usd_m"])


def test_merge_panel_fills_columns_from_every_source() -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fred=FakeMacroSource(),
            yfinance=FakeMarketSource(),
            sec_edgar=FakeFinancialsSource(),
        ),
    )

    assert list(panel.columns) == list(PANEL_COLUMNS)
    assert panel.loc[0, "company"] == "Amazon"
    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(EXPECTED_REVENUE)
    assert panel.loc[0, "stock_price_usd"] == pytest.approx(EXPECTED_STOCK_PRICE)
    assert panel.loc[0, "fed_funds"] == pytest.approx(EXPECTED_FED_FUNDS)
    assert panel.loc[0, "eps"] == pytest.approx(EXPECTED_ADJUSTED_EPS)


def test_merge_panel_derives_pe_ratio_from_price_and_earnings() -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fred=FakeMacroSource(),
            yfinance=FakeMarketSource(),
            sec_edgar=FakeFinancialsSource(),
        ),
    )

    assert panel.loc[0, "pe_ratio"] == pytest.approx(EXPECTED_PE_RATIO)
    assert pd.isna(panel.loc[1, "pe_ratio"])


def test_merge_panel_adjusts_eps_to_current_share_basis() -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fred=FakeMacroSource(),
            yfinance=FakeMarketSource(),
            sec_edgar=FakeFinancialsSource(),
        ),
    )

    assert panel.loc[0, "eps"] == pytest.approx(EXPECTED_ADJUSTED_EPS)


def test_merge_panel_propagates_source_errors() -> None:
    with pytest.raises(DataSourceUnavailableError, match="macro source unavailable"):
        merge_panel(
            ticker="AMZN",
            start=date(2020, 1, 1),
            end=date(2020, 6, 30),
            sources=IngestionSources(
                fred=FailingMacroSource(),
                yfinance=FakeMarketSource(),
                sec_edgar=FakeFinancialsSource(),
            ),
        )


@pytest.mark.vcr
def test_merge_panel_returns_panel_after_all_sources_are_implemented() -> None:
    panel = merge_panel(
        ticker="AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
        sources=IngestionSources(
            fred=FredSource(api_key=Settings.FRED_API_KEY or "test-key"),
            yfinance=YfinanceSource(),
            sec_edgar=SecEdgarSource(
                user_agent=Settings.SEC_USER_AGENT or TEST_USER_AGENT,
            ),
        ),
    )

    assert list(panel.columns) == list(PANEL_COLUMNS)
    assert len(panel) == len(quarter_end_dates(date(2020, 1, 1), date(2020, 6, 30)))
    assert panel["revenue_usd_m"].notna().any()
    assert panel["stock_price_usd"].notna().any()
    assert panel["fed_funds"].notna().any()
    assert panel["eps"].notna().any()
    assert panel["pe_ratio"].notna().any()

import numpy as np
import pandas as pd
import pytest

from app.data.companies import (
    CompanyPanelMetadata,
    CompanyRegistry,
    MarketFromTicker,
    ScrapedCompany,
    SecTickerLookup,
)
from app.data.consolidation import consolidate_panels
from app.data.flags import pre_listing_flag
from app.data.missing import missing_value_ledger
from app.data.schema import COST_OF_REVENUE_COLUMNS, FINANCIAL_COLUMNS
from tests.conftest import PanelFactory


@pytest.fixture
def panel_long(make_panel: PanelFactory) -> pd.DataFrame:
    return consolidate_panels({"AAA": make_panel(ticker="AAA", quarters=12)}).panel_long


def _reasons(ledger: pd.DataFrame, column: str) -> list[str]:
    return ledger.loc[ledger["column"] == column, "reason"].tolist()


def test_a_complete_panel_has_an_empty_ledger(panel_long: pd.DataFrame) -> None:
    assert missing_value_ledger(panel_long, CompanyRegistry(())).empty


def test_pe_with_non_positive_eps_is_explained_by_rule(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[4, ["eps", "pe_ratio"]] = [-1.0, np.nan]

    assert _reasons(
        missing_value_ledger(panel_long, CompanyRegistry(())), "pe_ratio"
    ) == ["pe_undefined_by_rule"]


def test_rows_before_the_first_price_are_pre_listing(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[:2, ["stock_price_usd", "eps", "market_cap_usd_m", "pe_ratio"]] = (
        np.nan
    )

    ledger = missing_value_ledger(panel_long, CompanyRegistry(()))

    assert set(ledger.loc[ledger["column"] != "pe_ratio", "reason"]) == {"pre_listing"}


def test_a_row_without_revenue_is_no_filing_data(panel_long: pd.DataFrame) -> None:
    panel_long.loc[5, [*FINANCIAL_COLUMNS, "market_cap_usd_m"]] = np.nan

    assert set(missing_value_ledger(panel_long, CompanyRegistry(()))["reason"]) == {
        "no_filing_data"
    }


def test_a_withheld_quarter_is_explained_as_withheld(panel_long: pd.DataFrame) -> None:
    panel_long.loc[5, list(FINANCIAL_COLUMNS)] = np.nan
    registry = CompanyRegistry((
        ScrapedCompany(
            tickers=("AAA",),
            panel=CompanyPanelMetadata(
                company="AAA",
                sector="Technology",
                is_public=True,
                withheld_quarters={panel_long["date"].dt.date.iloc[5]: "mixed bases"},
            ),
            sec=SecTickerLookup(),
            market=MarketFromTicker(),
        ),
    ))

    ledger = missing_value_ledger(panel_long, registry)

    financial = ledger[ledger["column"].isin(FINANCIAL_COLUMNS)]
    assert set(financial["reason"]) == {"withheld_quarter"}
    assert set(financial["column"]) == set(FINANCIAL_COLUMNS)


def test_gross_profit_gaps_of_a_company_without_cost_of_revenue_are_explained(
    panel_long: pd.DataFrame,
) -> None:
    panel_long[list(COST_OF_REVENUE_COLUMNS)] = np.nan

    registry = CompanyRegistry((
        ScrapedCompany(
            tickers=("AAA",),
            panel=CompanyPanelMetadata(
                company="AAA",
                sector="Technology",
                is_public=True,
                has_cost_of_revenue=False,
            ),
            sec=SecTickerLookup(),
            market=MarketFromTicker(),
        ),
    ))

    ledger = missing_value_ledger(panel_long, registry)

    assert set(ledger["reason"]) == {"no_cost_of_revenue"}
    assert set(ledger["column"]) == set(COST_OF_REVENUE_COLUMNS)


def test_gross_profit_gaps_of_any_other_company_stay_unexplained(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[3, "gross_profit_usd_m"] = np.nan

    registry = CompanyRegistry((
        ScrapedCompany(
            tickers=("BBB",),
            panel=CompanyPanelMetadata(
                company="BBB",
                sector="Technology",
                is_public=True,
                has_cost_of_revenue=False,
            ),
            sec=SecTickerLookup(),
            market=MarketFromTicker(),
        ),
    ))

    ledger = missing_value_ledger(panel_long, registry)

    assert ledger["reason"].tolist() == ["unexplained"]


def test_opex_gaps_of_a_company_without_reliable_opex_are_explained(
    panel_long: pd.DataFrame,
) -> None:
    panel_long["opex_usd_m"] = np.nan

    registry = CompanyRegistry((
        ScrapedCompany(
            tickers=("AAA",),
            panel=CompanyPanelMetadata(
                company="AAA",
                sector="Technology",
                is_public=True,
                has_reliable_opex=False,
            ),
            sec=SecTickerLookup(),
            market=MarketFromTicker(),
        ),
    ))

    ledger = missing_value_ledger(panel_long, registry)

    assert set(ledger["reason"]) == {"unreliable_opex"}
    assert set(ledger["column"]) == {"opex_usd_m"}


def test_an_eps_gap_with_price_and_revenue_is_unexplained(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[7, "eps"] = np.nan

    ledger = missing_value_ledger(panel_long, CompanyRegistry(()))

    assert ledger[["column", "reason"]].to_numpy().tolist() == [["eps", "unexplained"]]
    assert ledger.loc[ledger.index[0], "ticker"] == "AAA"
    assert ledger.loc[ledger.index[0], "date"] == panel_long.loc[7, "date"]


def test_pre_listing_rows_are_the_rows_the_pre_listing_flag_marks(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[:2, "stock_price_usd"] = np.nan

    ledger = missing_value_ledger(panel_long, CompanyRegistry(()))
    pre_listing_dates = ledger.loc[ledger["reason"] == "pre_listing", "date"]

    assert set(pre_listing_dates) == set(
        panel_long.loc[pre_listing_flag(panel_long), "date"]
    )


def test_a_company_never_priced_has_no_pre_listing_rows(
    panel_long: pd.DataFrame,
) -> None:
    panel_long["stock_price_usd"] = np.nan

    assert "pre_listing" not in set(
        missing_value_ledger(panel_long, CompanyRegistry(()))["reason"]
    )
    assert not pre_listing_flag(panel_long).any()

import numpy as np
import pandas as pd
import pytest

from app.data.consolidation import consolidate_panels
from app.data.missing import missing_value_ledger
from app.data.schema import FINANCIAL_COLUMNS
from tests.conftest import PanelFactory


@pytest.fixture
def panel_long(make_panel: PanelFactory) -> pd.DataFrame:
    return consolidate_panels({"AAA": make_panel(ticker="AAA", quarters=12)}).panel_long


def _reasons(ledger: pd.DataFrame, column: str) -> list[str]:
    return ledger.loc[ledger["column"] == column, "reason"].tolist()


def test_a_complete_panel_has_an_empty_ledger(panel_long: pd.DataFrame) -> None:
    assert missing_value_ledger(panel_long).empty


def test_pe_with_non_positive_eps_is_explained_by_rule(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[4, ["eps", "pe_ratio"]] = [-1.0, np.nan]

    assert _reasons(missing_value_ledger(panel_long), "pe_ratio") == [
        "pe_undefined_by_rule"
    ]


def test_rows_before_the_first_price_are_pre_listing(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[:2, ["stock_price_usd", "eps", "market_cap_usd_m", "pe_ratio"]] = (
        np.nan
    )

    ledger = missing_value_ledger(panel_long)

    assert set(ledger.loc[ledger["column"] != "pe_ratio", "reason"]) == {"pre_listing"}


def test_a_row_without_revenue_is_no_filing_data(panel_long: pd.DataFrame) -> None:
    panel_long.loc[5, [*FINANCIAL_COLUMNS, "market_cap_usd_m"]] = np.nan

    assert set(missing_value_ledger(panel_long)["reason"]) == {"no_filing_data"}


def test_an_eps_gap_with_price_and_revenue_is_unexplained(
    panel_long: pd.DataFrame,
) -> None:
    panel_long.loc[7, "eps"] = np.nan

    ledger = missing_value_ledger(panel_long)

    assert ledger[["column", "reason"]].to_numpy().tolist() == [["eps", "unexplained"]]
    assert ledger.loc[ledger.index[0], "ticker"] == "AAA"
    assert ledger.loc[ledger.index[0], "date"] == panel_long.loc[7, "date"]

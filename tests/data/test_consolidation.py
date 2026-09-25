import pandas as pd
import pytest

from app.data.consolidation import consolidate_panels
from app.data.exceptions import ConsolidationError, MacroMismatchError
from app.data.schema import MACRO_COLUMNS
from tests.conftest import PanelFactory

QUARTERS = 8


@pytest.fixture
def panels(make_panel: PanelFactory) -> dict[str, pd.DataFrame]:
    return {
        "BBB": make_panel(ticker="BBB", quarters=QUARTERS),
        "AAA": make_panel(ticker="AAA", quarters=QUARTERS),
    }


def test_panel_long_holds_every_row_sorted_by_ticker_then_date(
    panels: dict[str, pd.DataFrame],
) -> None:
    panel_long = consolidate_panels(panels).panel_long

    assert len(panel_long) == 2 * QUARTERS
    assert panel_long["ticker"].tolist() == ["AAA"] * QUARTERS + ["BBB"] * QUARTERS
    assert panel_long.equals(
        panel_long.sort_values(["ticker", "date"], ignore_index=True)
    )


def test_macro_lives_once_in_macro_q(panels: dict[str, pd.DataFrame]) -> None:
    result = consolidate_panels(panels)

    assert list(result.macro_q.columns) == ["date", *MACRO_COLUMNS]
    assert len(result.macro_q) == QUARTERS
    assert not set(MACRO_COLUMNS) & set(result.panel_long.columns)


def test_is_public_is_dropped(panels: dict[str, pd.DataFrame]) -> None:
    assert "is_public" not in consolidate_panels(panels).panel_long.columns


def test_a_varying_is_public_is_refused(panels: dict[str, pd.DataFrame]) -> None:
    panels["AAA"].loc[0, "is_public"] = False

    with pytest.raises(ConsolidationError, match="is_public"):
        consolidate_panels(panels)


def test_differing_macro_names_the_company(panels: dict[str, pd.DataFrame]) -> None:
    panels["BBB"].loc[3, "vix"] = 999.0

    with pytest.raises(MacroMismatchError, match="BBB"):
        consolidate_panels(panels)


def test_no_panels_is_refused() -> None:
    with pytest.raises(ConsolidationError):
        consolidate_panels({})

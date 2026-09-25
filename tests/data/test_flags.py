import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.data.consolidation import consolidate_panels
from app.data.exceptions import ConsolidationError
from app.data.flags import (
    add_flags,
    covid_flag,
    is_projected,
    outlier_flag,
    structural_break_flag,
)
from tests.conftest import PanelFactory

FAR_FUTURE = date(2100, 1, 1)
FLAG_COLUMNS = ["covid", "structural_break", "outlier_flag", "is_projected"]
COVID_QUARTERS_PER_COMPANY = 3
BREAK_WINDOW = 4


def _dates(quarters: int, start: str = "2019-03-31") -> pd.Series:
    return pd.Series(pd.date_range(start, periods=quarters, freq="QE"))


def _margin_panel(quarters: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "revenue_usd_m": 100 * np.exp(0.02 * np.arange(quarters)),
        "gross_margin": 0.4 + 0.01 * rng.normal(size=quarters),
        "operating_margin": 0.2 + 0.01 * rng.normal(size=quarters),
        "net_margin": 0.1 + 0.01 * rng.normal(size=quarters),
    })


def test_covid_marks_exactly_the_three_2020_quarters() -> None:
    dates = _dates(12)

    flagged = dates[covid_flag(dates)]

    assert flagged.dt.strftime("%Y-%m-%d").tolist() == [
        "2020-06-30",
        "2020-09-30",
        "2020-12-31",
    ]


def test_projected_means_after_the_last_reported_quarter() -> None:
    dates = _dates(4, start="2026-03-31")

    projected = is_projected(dates, last_reported_quarter=date(2026, 6, 30))

    assert projected.tolist() == [False, False, True, True]


def test_a_break_covers_its_quarter_and_the_next_three() -> None:
    flagged = structural_break_flag(_dates(12), [date(2020, 3, 31)])

    assert flagged.to_numpy().nonzero()[0].tolist() == [4, 5, 6, 7]


def test_two_breaks_flag_both_windows() -> None:
    flagged = structural_break_flag(_dates(12), [date(2019, 6, 30), date(2021, 3, 31)])

    assert flagged.to_numpy().nonzero()[0].tolist() == [1, 2, 3, 4, 8, 9, 10, 11]


def test_an_extreme_margin_is_flagged() -> None:
    panel = _margin_panel()
    panel.loc[35, "net_margin"] = 0.9

    assert outlier_flag(panel).loc[35]


def test_only_a_small_share_is_flagged() -> None:
    assert outlier_flag(_margin_panel()).sum() <= math.ceil(0.03 * 36) + 1


def test_a_short_history_gets_no_flags() -> None:
    assert outlier_flag(_margin_panel(quarters=10)).sum() == 0


def test_rows_missing_an_input_are_never_flagged() -> None:
    panel = _margin_panel()
    panel.loc[20, "net_margin"] = np.nan

    assert not outlier_flag(panel).loc[20]


def test_the_same_seed_gives_the_same_flags() -> None:
    panel = _margin_panel()

    pd.testing.assert_series_equal(outlier_flag(panel), outlier_flag(panel))


@pytest.fixture
def panel_long(make_panel: PanelFactory) -> pd.DataFrame:
    panels = {"AAA": make_panel(ticker="AAA"), "BBB": make_panel(ticker="BBB")}
    return consolidate_panels(panels).panel_long


def test_add_flags_adds_four_boolean_columns_and_keeps_the_index(
    panel_long: pd.DataFrame,
) -> None:
    flagged = add_flags(panel_long, {}, last_reported_quarter=FAR_FUTURE)

    assert flagged.index.equals(panel_long.index)
    assert flagged[FLAG_COLUMNS].dtypes.eq("bool").all()
    assert flagged["covid"].sum() == 2 * COVID_QUARTERS_PER_COMPANY


def test_a_break_applies_to_its_own_company_only(panel_long: pd.DataFrame) -> None:
    flagged = add_flags(
        panel_long,
        {"AAA": (date(2015, 12, 31),)},
        last_reported_quarter=FAR_FUTURE,
    )

    assert flagged.groupby("ticker")["structural_break"].sum().to_dict() == {
        "AAA": BREAK_WINDOW,
        "BBB": 0,
    }


def test_a_break_for_an_unknown_company_is_refused(panel_long: pd.DataFrame) -> None:
    with pytest.raises(ConsolidationError, match="ZZZ"):
        add_flags(
            panel_long,
            {"ZZZ": (date(2015, 12, 31),)},
            last_reported_quarter=FAR_FUTURE,
        )

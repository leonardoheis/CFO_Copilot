import math
from datetime import date
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import pytest

from app.data.consolidation import consolidate_panels
from app.data.exceptions import MalformedPanelError, PanelNotFoundError
from app.data.flags import add_flags
from app.data.panel_store import PanelStore
from app.data.schema import MACRO_COLUMNS
from app.settings import Settings
from tests.conftest import PanelFactory

QUARTERS = 24


def _write(store: PanelStore, panel: pd.DataFrame) -> None:
    panel.assign(date=panel["date"].dt.date).to_parquet(
        store.path_for(panel["ticker"].iloc[0]), index=False
    )


def test_load_returns_datetime_dates(tmp_path: Path, make_panel: PanelFactory) -> None:
    store = PanelStore(tmp_path)
    _write(store, make_panel(ticker="AAA"))

    panel = store.load("aaa")

    assert pd.api.types.is_datetime64_any_dtype(panel["date"])
    assert len(panel) == QUARTERS


def test_missing_file_names_the_ticker(tmp_path: Path) -> None:
    with pytest.raises(PanelNotFoundError, match="ZZZ"):
        PanelStore(tmp_path).load("zzz")


def test_missing_column_is_named(tmp_path: Path, make_panel: PanelFactory) -> None:
    store = PanelStore(tmp_path)
    _write(store, make_panel(ticker="AAA").drop(columns=["vix"]))

    with pytest.raises(MalformedPanelError, match="vix"):
        store.load("AAA")


def test_gap_in_quarters_is_rejected(tmp_path: Path, make_panel: PanelFactory) -> None:
    store = PanelStore(tmp_path)
    _write(store, make_panel(ticker="AAA").drop(index=5))

    with pytest.raises(MalformedPanelError, match="consecutive"):
        store.load("AAA")


def test_duplicate_dates_are_rejected(tmp_path: Path, make_panel: PanelFactory) -> None:
    panel = make_panel(ticker="AAA")
    panel.loc[3, "date"] = panel.loc[2, "date"]
    store = PanelStore(tmp_path)
    _write(store, panel)

    with pytest.raises(MalformedPanelError, match="consecutive"):
        store.load("AAA")


def test_load_all_keys_every_panel_on_disk(
    tmp_path: Path, make_panel: PanelFactory
) -> None:
    store = PanelStore(tmp_path)
    for ticker in ("BBB", "AAA"):
        _write(store, make_panel(ticker=ticker))

    assert store.tickers() == ("AAA", "BBB")
    assert set(store.load_all()) == {"AAA", "BBB"}


def test_missing_directory_holds_no_tickers(tmp_path: Path) -> None:
    assert not PanelStore(tmp_path / "absent").tickers()


def test_file_naming_matches_the_ingestion_writer() -> None:
    store = PanelStore(Settings.panel_output_path("AAPL").parent)

    assert store.path_for("aapl") == Settings.panel_output_path("AAPL")


def test_nb00_output_naming_matches_the_consolidation_writer() -> None:
    store = PanelStore(Settings.PANEL_LONG_PATH.parent)

    assert store.panel_long_path == Settings.PANEL_LONG_PATH
    assert store.macro_q_path == Settings.MACRO_Q_PATH


class Nb00Outputs(NamedTuple):
    store: PanelStore
    panel_long: pd.DataFrame
    macro_q: pd.DataFrame

    def load(self) -> dict[str, pd.DataFrame]:
        return self.store.load_consolidated()


@pytest.fixture
def nb00_outputs(tmp_path: Path, make_panel: PanelFactory) -> Nb00Outputs:
    consolidated = consolidate_panels({
        "AAA": make_panel(ticker="AAA"),
        "BBB": make_panel(ticker="BBB"),
    })
    panel_long = add_flags(
        consolidated.panel_long, {}, last_reported_quarter=date(2100, 1, 1)
    )
    store = PanelStore(tmp_path)
    panel_long.to_parquet(store.panel_long_path, index=False)
    consolidated.macro_q.to_parquet(store.macro_q_path, index=False)
    return Nb00Outputs(store=store, panel_long=panel_long, macro_q=consolidated.macro_q)


def test_load_consolidated_returns_one_frame_per_ticker(
    nb00_outputs: Nb00Outputs,
) -> None:
    panels = nb00_outputs.load()

    assert set(panels) == {"AAA", "BBB"}
    frame = panels["AAA"]
    flags = {"covid", "structural_break", "outlier_flag", "is_projected"}
    assert {*MACRO_COLUMNS, *flags} <= set(frame.columns)
    assert pd.api.types.is_datetime64_any_dtype(frame["date"])
    assert frame.index.tolist() == list(range(QUARTERS))


def test_projected_rows_are_left_out(nb00_outputs: Nb00Outputs) -> None:
    panel_long = nb00_outputs.panel_long
    panel_long.loc[panel_long.index[-1], "is_projected"] = True
    panel_long.to_parquet(nb00_outputs.store.panel_long_path, index=False)

    assert len(nb00_outputs.load()["BBB"]) == QUARTERS - 1


def test_missing_nb00_output_is_named(tmp_path: Path) -> None:
    with pytest.raises(PanelNotFoundError, match="panel_long"):
        PanelStore(tmp_path).load_consolidated()


def test_a_panel_date_absent_from_macro_q_is_named(nb00_outputs: Nb00Outputs) -> None:
    nb00_outputs.macro_q.iloc[:-1].to_parquet(
        nb00_outputs.store.macro_q_path, index=False
    )

    with pytest.raises(MalformedPanelError, match=r"no row for .*2020-12-31"):
        nb00_outputs.load()


def test_a_missing_macro_value_names_its_column_and_date(
    nb00_outputs: Nb00Outputs,
) -> None:
    macro_q = nb00_outputs.macro_q.copy()
    macro_q.loc[3, "vix"] = math.nan
    macro_q.to_parquet(nb00_outputs.store.macro_q_path, index=False)

    with pytest.raises(MalformedPanelError, match=r"missing values.*vix.*2015-12-31"):
        nb00_outputs.load()

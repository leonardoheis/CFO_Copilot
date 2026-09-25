from pathlib import Path

import pandas as pd
import pytest

from app.data.exceptions import MalformedPanelError, PanelNotFoundError
from app.data.panel_store import PanelStore
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

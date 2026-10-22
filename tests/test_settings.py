from pathlib import Path

import pytest

from app.settings import Settings


def test_reading_data_paths_creates_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(type(Settings), "ROOT_PATH", property(lambda _: tmp_path))

    paths = (
        Settings.DATA_DIRECTORY,
        Settings.PANEL_LONG_PATH,
        Settings.MACRO_Q_PATH,
        Settings.panel_output_path("aapl"),
    )

    assert paths[-1] == tmp_path / "data" / "processed" / "AAPL_panel.parquet"
    assert not any(tmp_path.iterdir())

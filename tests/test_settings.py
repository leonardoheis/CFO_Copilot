from pathlib import Path

import pytest

from app.settings import Settings


def test_reading_data_paths_creates_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(type(Settings), "ROOT_PATH", property(lambda _: tmp_path))

    paths = (Settings.DATA_DIRECTORY, Settings.PROCESSED_DIRECTORY)

    assert paths[-1] == tmp_path / "data" / "processed"
    assert not any(tmp_path.iterdir())

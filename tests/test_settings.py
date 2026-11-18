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


def test_local_models_live_under_the_repository_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_MODELS_DIRECTORY", raising=False)
    monkeypatch.setitem(type(Settings).model_config, "env_file", None)

    settings = type(Settings)()

    assert settings.LOCAL_MODELS_DIRECTORY == Settings.ROOT_PATH / "models"


def test_local_models_directory_follows_an_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_MODELS_DIRECTORY", str(tmp_path))

    assert tmp_path == type(Settings)().LOCAL_MODELS_DIRECTORY

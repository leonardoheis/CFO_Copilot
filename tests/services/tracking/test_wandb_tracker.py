import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Literal

import pandas as pd
import pytest

from app.injections.production import Container
from app.services.tracking import (
    MissingApiKeyError,
    RunConfig,
    TrackingUnavailableError,
    WandbSettings,
    WandbTracker,
)

CONFIG = RunConfig(panel_size=2, n_rows=48, target_variable="revenue_usd_m")
Mode = Literal["online", "offline", "disabled"]


@dataclass
class _FakeArtifact:
    """Positional ``name`` like ``wandb.Artifact``, which Pydantic cannot mimic."""

    name: str
    type: str
    files: list[str] = field(default_factory=list)

    def add_file(self, path: str) -> None:
        self.files.append(path)


class _FakeRun:
    def __init__(self) -> None:
        self.logged: list[dict[str, object]] = []
        self.artifacts: list[_FakeArtifact] = []
        self.finished = False

    def log(self, data: dict[str, object]) -> None:
        self.logged.append(data)

    def log_artifact(self, artifact: _FakeArtifact) -> None:
        self.artifacts.append(artifact)

    def finish(self) -> None:
        self.finished = True


class _FakeWandb(ModuleType):
    """Stands in for the ``wandb`` module; nothing needs installing."""

    def __init__(self) -> None:
        super().__init__("wandb")
        self.run = _FakeRun()
        self.seen: dict[str, object] = {}
        self.Artifact = _FakeArtifact
        self.Table = lambda dataframe: ("table", len(dataframe))

    def init(self, **kwargs: object) -> _FakeRun:
        self.seen["init"] = kwargs
        return self.run

    def login(self, *, key: str) -> None:
        self.seen["login"] = key


@pytest.fixture
def wandb(monkeypatch: pytest.MonkeyPatch) -> _FakeWandb:
    fake = _FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", fake)
    return fake


def _tracker(
    run_directory: Path, *, mode: Mode = "offline", api_key: str = ""
) -> WandbTracker:
    settings = WandbSettings(
        project="cfo-copilot",
        entity=None,
        mode=mode,
        api_key=api_key,
        run_directory=run_directory,
    )
    return WandbTracker(settings=settings)


def test_run_receives_name_config_and_mode(wandb: _FakeWandb, tmp_path: Path) -> None:
    with _tracker(tmp_path).start_run("nb01-eda-revenue", CONFIG, job_type="eda"):
        pass

    assert wandb.seen["init"] == {
        "dir": str(tmp_path),
        "project": "cfo-copilot",
        "entity": None,
        "name": "nb01-eda-revenue",
        "job_type": "eda",
        "config": CONFIG.model_dump(mode="json"),
        "mode": "offline",
    }


def test_run_finishes_when_the_body_raises(wandb: _FakeWandb, tmp_path: Path) -> None:
    with (
        pytest.raises(RuntimeError),
        _tracker(tmp_path).start_run("r", CONFIG, job_type="eda"),
    ):
        raise RuntimeError

    assert wandb.run.finished


def test_table_and_metrics_are_logged(wandb: _FakeWandb, tmp_path: Path) -> None:
    with _tracker(tmp_path).start_run("r", CONFIG, job_type="eda") as tracked:
        tracked.log_table("diagnostics", pd.DataFrame({"a": [1, 2]}))
        tracked.log_metrics({"n_ok": 3.0})

    assert wandb.run.logged == [{"diagnostics": ("table", 2)}, {"n_ok": 3.0}]


def test_dataset_is_logged_as_an_artifact(wandb: _FakeWandb, tmp_path: Path) -> None:
    path = tmp_path / "features_h1.parquet"

    with _tracker(tmp_path).start_run("r", CONFIG, job_type="features") as tracked:
        tracked.log_dataset("features_h1", path)

    logged = [(a.name, a.type, a.files) for a in wandb.run.artifacts]
    assert logged == [("features_h1", "dataset", [str(path)])]


def test_online_without_key_fails_before_any_run(
    wandb: _FakeWandb, tmp_path: Path
) -> None:
    with (
        pytest.raises(MissingApiKeyError, match="WANDB_API_KEY"),
        _tracker(tmp_path, mode="online").start_run("r", CONFIG, job_type="eda"),
    ):
        pass

    assert "init" not in wandb.seen


def test_online_logs_in_with_the_configured_key(
    wandb: _FakeWandb, tmp_path: Path
) -> None:
    with _tracker(tmp_path, mode="online", api_key="secret").start_run(
        "r", CONFIG, job_type="eda"
    ):
        pass

    assert wandb.seen["login"] == "secret"


def test_offline_never_logs_in(wandb: _FakeWandb, tmp_path: Path) -> None:
    with _tracker(tmp_path).start_run("r", CONFIG, job_type="eda"):
        pass

    assert "login" not in wandb.seen


def test_container_builds_the_tracker_without_wandb_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "wandb", None)

    tracker = Container().experiment_tracker()

    assert isinstance(tracker, WandbTracker)
    with (
        pytest.raises(TrackingUnavailableError, match="research"),
        tracker.start_run("r", CONFIG, job_type="eda"),
    ):
        pass

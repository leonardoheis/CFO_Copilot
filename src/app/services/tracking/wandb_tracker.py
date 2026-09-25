import importlib
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Protocol

import pandas as pd
from matplotlib.figure import Figure
from pydantic import BaseModel, ConfigDict

from app.services.tracking.config import RunConfig, WandbSettings
from app.services.tracking.exceptions import (
    MissingApiKeyError,
    TrackingUnavailableError,
)


class _RawRun(Protocol):
    def log(self, data: dict[str, object]) -> None: ...
    def log_artifact(self, artifact: object) -> None: ...
    def finish(self) -> None: ...


def import_wandb() -> ModuleType:
    """Import wandb on first use so the image runs without the research group.

    Returns:
        The imported ``wandb`` module.

    Raises:
        TrackingUnavailableError: wandb is not installed.
    """
    try:
        return importlib.import_module("wandb")
    except ImportError as error:
        message = "wandb is not installed; run `uv sync --group research`"
        raise TrackingUnavailableError(message) from error


class WandbRun:
    def __init__(self, run: _RawRun, wandb: ModuleType) -> None:
        self._run = run
        self._wandb = wandb

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self._run.log(dict(metrics))

    def log_table(self, name: str, table: pd.DataFrame) -> None:
        self._run.log({name: self._wandb.Table(dataframe=table)})

    def log_figure(self, name: str, figure: Figure) -> None:
        self._run.log({name: self._wandb.Image(figure)})

    def log_dataset(self, name: str, path: Path) -> None:
        artifact = self._wandb.Artifact(name, type="dataset")
        artifact.add_file(str(path))
        self._run.log_artifact(artifact)


class WandbTracker(BaseModel):
    """Start W&B runs; offline mode keeps a tracking outage from blocking work."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    settings: WandbSettings

    @contextmanager
    def start_run(
        self, name: str, config: RunConfig, *, job_type: str
    ) -> Generator[WandbRun]:
        """Open a run and finish it however the body exits.

        Yields:
            A handle for logging metrics, tables, figures and datasets.
        """
        wandb = import_wandb()
        self._login_when_online(wandb)
        self.settings.run_directory.mkdir(parents=True, exist_ok=True)
        run = wandb.init(
            dir=str(self.settings.run_directory),
            project=self.settings.project,
            entity=self.settings.entity,
            name=name,
            job_type=job_type,
            config=config.model_dump(mode="json"),
            mode=self.settings.mode,
        )
        try:
            yield WandbRun(run, wandb)
        finally:
            run.finish()

    def _login_when_online(self, wandb: ModuleType) -> None:
        if self.settings.mode != "online":
            return
        if not self.settings.api_key:
            message = "WANDB_MODE is online but WANDB_API_KEY is empty; set it in .env"
            raise MissingApiKeyError(message)
        wandb.login(key=self.settings.api_key)

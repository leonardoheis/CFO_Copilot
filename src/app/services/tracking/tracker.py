from collections.abc import Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

import pandas as pd
from matplotlib.figure import Figure

from app.services.tracking.config import RunConfig


class TrackedRun(Protocol):
    def log_metrics(self, metrics: Mapping[str, float]) -> None: ...
    def log_table(self, name: str, table: pd.DataFrame) -> None: ...
    def log_figure(self, name: str, figure: Figure) -> None: ...
    def log_dataset(self, name: str, path: Path) -> None: ...


class ExperimentTracker(Protocol):
    def start_run(
        self, name: str, config: RunConfig, *, job_type: str
    ) -> AbstractContextManager[TrackedRun]: ...

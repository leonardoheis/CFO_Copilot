import importlib
from pathlib import Path
from typing import Final, Protocol, Self, cast

import pandas as pd

from app.data.report_store import ReportStore
from app.data.schema import PROVENANCE_COLUMNS
from app.services.diagnostics.exceptions import ProfilingUnavailableError
from app.services.diagnostics.models import ProfileSettings

_NOT_PROFILED: Final = (
    "date",
    *PROVENANCE_COLUMNS,
    "period_end_offset_days",
    "pre_listing",
)


def profile_frame(pooled: pd.DataFrame) -> pd.DataFrame:
    """Keep the listed quarters and the variables worth profiling.

    Returns:
        ``pooled`` without pre-listing rows, dates, or provenance metadata.
    """
    if "pre_listing" in pooled.columns:
        pooled = pooled.loc[~pooled["pre_listing"].astype(bool)]
    return pooled.drop(columns=[c for c in _NOT_PROFILED if c in pooled.columns])


class _Report(Protocol):
    """The slice of ydata-profiling's ``ProfileReport`` this module relies on."""

    def to_file(self, output_file: Path, *, silent: bool = ...) -> None: ...
    def compare(self, other: Self) -> Self: ...


class _ReportFactory(Protocol):
    """``ProfileReport``'s constructor arguments this module passes."""

    def __call__(
        self,
        df: pd.DataFrame,
        *,
        title: str,
        progress_bar: bool,
        interactions: dict[str, bool],
    ) -> _Report: ...


def _report_factory() -> _ReportFactory:
    # Imported on first use: ydata-profiling is in the research group only, so
    # the production image and CI's test job run without it.
    try:
        module = importlib.import_module("ydata_profiling")
    except ImportError as error:
        message = "ydata-profiling is not installed; run `uv sync --group research`"
        raise ProfilingUnavailableError(message) from error
    return cast("_ReportFactory", module.ProfileReport)


class AutoProfiler:
    """Write automated ydata-profiling reports of a frame, or of two compared.

    Usage::

        profiler = container.auto_profiler()
        path = profiler.profile(pooled, title="Pooled panel", name="panel.html")
    """

    def __init__(self, store: ReportStore, settings: ProfileSettings) -> None:
        self._store = store
        self._settings = settings

    def _report(self, frame: pd.DataFrame, title: str) -> _Report:
        return _report_factory()(
            frame,
            title=title,
            progress_bar=False,
            interactions={"continuous": self._settings.interactions},
        )

    def profile(self, frame: pd.DataFrame, *, title: str, name: str) -> Path:
        """Profile one frame into an HTML report.

        Returns:
            The written report.
        """
        path = self._store.path_for(name)
        self._report(frame, title).to_file(path, silent=True)
        return path

    def compare(
        self,
        before: pd.DataFrame,
        after: pd.DataFrame,
        *,
        before_title: str,
        after_title: str,
        name: str,
    ) -> Path:
        """Profile two frames side by side into one HTML report.

        Returns:
            The written comparison report.
        """
        path = self._store.path_for(name)
        comparison = self._report(before, before_title).compare(
            self._report(after, after_title)
        )
        comparison.to_file(path, silent=True)
        return path

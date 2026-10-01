import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
from pydantic import ValidationError

from app.data import ReportStore
from app.injections import Container
from app.services.diagnostics import (
    AutoProfiler,
    ProfileSettings,
    ProfilingUnavailableError,
)

MAX_REPORT_BYTES = 5 * 1024 * 1024


class _FakeReport:
    def __init__(self, df: pd.DataFrame, title: str, config: dict[str, object]) -> None:
        self.df = df
        self.title = title
        self.config = config
        self.silent: bool | None = None

    def to_file(self, output_file: Path, *, silent: bool = True) -> None:
        self.silent = silent
        Path(output_file).write_text(f"<html>{self.title}</html>", encoding="utf-8")

    def compare(self, other: "_FakeReport") -> "_FakeReport":
        return _FakeReport(self.df, f"{self.title} vs {other.title}", self.config)


class _FakeYdata(ModuleType):
    """Stands in for ``ydata_profiling``; nothing needs installing."""

    def __init__(self) -> None:
        super().__init__("ydata_profiling")
        self.reports: list[_FakeReport] = []
        self.ProfileReport = self._record_report

    def _record_report(
        self, df: pd.DataFrame, *, title: str, **config: object
    ) -> _FakeReport:
        report = _FakeReport(df, title, config)
        self.reports.append(report)
        return report


@pytest.fixture
def ydata(monkeypatch: pytest.MonkeyPatch) -> _FakeYdata:
    fake = _FakeYdata()
    monkeypatch.setitem(sys.modules, "ydata_profiling", fake)
    return fake


@pytest.fixture
def profiler(tmp_path: Path) -> AutoProfiler:
    return AutoProfiler(
        store=ReportStore(directory=tmp_path / "reports"), settings=ProfileSettings()
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"revenue_usd_m": [1.0, 2.0, 3.0], "sector": ["A", "B", "A"]})


def test_profile_writes_one_report_through_the_store(
    ydata: _FakeYdata, profiler: AutoProfiler, tmp_path: Path
) -> None:
    path = profiler.profile(_frame(), title="Panel", name="panel.html")

    assert path == tmp_path / "reports" / "panel.html"
    assert path.read_text(encoding="utf-8") == "<html>Panel</html>"
    assert ydata.reports[0].title == "Panel"
    assert ydata.reports[0].silent is True


def test_pairwise_interactions_are_off_by_default(
    ydata: _FakeYdata, profiler: AutoProfiler
) -> None:
    profiler.profile(_frame(), title="Panel", name="panel.html")

    assert ydata.reports[0].config["interactions"] == {"continuous": False}
    assert ydata.reports[0].config["progress_bar"] is False


def test_compare_writes_one_report_of_both_frames(
    ydata: _FakeYdata, profiler: AutoProfiler
) -> None:
    path = profiler.compare(
        _frame(),
        _frame(),
        before_title="Before 2020",
        after_title="2020 onward",
        name="drift.html",
    )

    assert path.read_text(encoding="utf-8") == "<html>Before 2020 vs 2020 onward</html>"
    assert [report.title for report in ydata.reports] == ["Before 2020", "2020 onward"]


def test_settings_refuse_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        ProfileSettings.model_validate({"minimal": True})


def test_missing_library_is_a_named_error(
    monkeypatch: pytest.MonkeyPatch, profiler: AutoProfiler
) -> None:
    monkeypatch.setitem(sys.modules, "ydata_profiling", None)

    with pytest.raises(ProfilingUnavailableError, match="research"):
        profiler.profile(_frame(), title="Panel", name="panel.html")


def test_container_builds_the_profiler_without_ydata_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "ydata_profiling", None)

    assert isinstance(Container().auto_profiler(), AutoProfiler)


# ydata-profiling 4.18.4 (the latest) calls datetime.utcnow(), deprecated in 3.12.
@pytest.mark.filterwarnings(
    "ignore:datetime.datetime.utcnow:DeprecationWarning:ydata_profiling.model.describe"
)
def test_real_report_of_a_small_panel_stays_small(profiler: AutoProfiler) -> None:
    pytest.importorskip("ydata_profiling")
    panel = pd.DataFrame({
        "revenue_usd_m": [float(value) for value in range(40)],
        "sector": ["A", "B"] * 20,
    })

    path = profiler.profile(panel, title="Smoke", name="smoke.html")

    assert 0 < path.stat().st_size < MAX_REPORT_BYTES

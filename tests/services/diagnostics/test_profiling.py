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
    profile_frame,
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


class _ReportRecorder:
    """Records every report the fake ``ydata_profiling`` is asked to build."""

    def __init__(self) -> None:
        self.reports: list[_FakeReport] = []

    def profile_report(
        self, df: pd.DataFrame, *, title: str, **config: object
    ) -> _FakeReport:
        report = _FakeReport(df, title, config)
        self.reports.append(report)
        return report


@pytest.fixture
def ydata(monkeypatch: pytest.MonkeyPatch) -> _ReportRecorder:
    recorder = _ReportRecorder()
    fake_module = ModuleType("ydata_profiling")
    monkeypatch.setattr(
        fake_module, "ProfileReport", recorder.profile_report, raising=False
    )
    monkeypatch.setitem(sys.modules, "ydata_profiling", fake_module)
    return recorder


@pytest.fixture
def profiler(tmp_path: Path) -> AutoProfiler:
    return AutoProfiler(
        store=ReportStore(directory=tmp_path / "reports"), settings=ProfileSettings()
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"revenue_usd_m": [1.0, 2.0, 3.0], "sector": ["A", "B", "A"]})


def test_profile_writes_one_report_through_the_store(
    ydata: _ReportRecorder, profiler: AutoProfiler, tmp_path: Path
) -> None:
    path = profiler.profile(_frame(), title="Panel", name="panel.html")

    assert path == tmp_path / "reports" / "panel.html"
    assert path.read_text(encoding="utf-8") == "<html>Panel</html>"
    assert ydata.reports[0].title == "Panel"
    assert ydata.reports[0].silent is True


def test_pairwise_interactions_are_off_by_default(
    ydata: _ReportRecorder, profiler: AutoProfiler
) -> None:
    profiler.profile(_frame(), title="Panel", name="panel.html")

    assert ydata.reports[0].config["interactions"] == {"continuous": False}
    assert ydata.reports[0].config["progress_bar"] is False


def test_compare_writes_one_report_of_both_frames(
    ydata: _ReportRecorder, profiler: AutoProfiler
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


def _pooled_panel() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["TSLA", "TSLA", "AAPL"],
        "date": pd.to_datetime(["2010-03-31", "2010-06-30", "2010-03-31"]),
        "revenue_usd_m": [20.8, 28.4, 13_499.0],
        "period_end": pd.to_datetime(["2010-03-31", "2010-06-30", "2010-03-27"]),
        "financials_filed": [None, "2010-08-13", "2010-04-21"],
        "financials_provenance": ["alpha_vantage", "native", "native"],
        "period_end_offset_days": [0, 0, -4],
        "pre_listing": [True, False, False],
    })


def test_profile_frame_drops_pre_listing_rows() -> None:
    frame = profile_frame(_pooled_panel())

    assert frame["revenue_usd_m"].tolist() == [28.4, 13_499.0]


def test_profile_frame_drops_dates_provenance_and_the_spent_flag() -> None:
    assert list(profile_frame(_pooled_panel()).columns) == ["ticker", "revenue_usd_m"]


def test_profile_frame_keeps_every_row_without_a_pre_listing_flag() -> None:
    pooled = _pooled_panel().drop(columns=["pre_listing"])

    assert len(profile_frame(pooled)) == len(pooled)

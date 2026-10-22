from pathlib import Path

import pandas as pd

from app.data import ReportStore


def test_path_is_named_inside_the_directory(tmp_path: Path) -> None:
    store = ReportStore(directory=tmp_path / "reports")

    assert store.path_for("auto_eda.html") == tmp_path / "reports" / "auto_eda.html"


def test_asking_for_a_path_creates_nothing(tmp_path: Path) -> None:
    store = ReportStore(directory=tmp_path / "reports")

    store.path_for("auto_eda.html")

    assert not (tmp_path / "reports").exists()


def test_construction_creates_nothing(tmp_path: Path) -> None:
    ReportStore(directory=tmp_path / "reports")

    assert not (tmp_path / "reports").exists()


def test_a_table_is_written_as_csv_and_its_path_returned(tmp_path: Path) -> None:
    store = ReportStore(directory=tmp_path / "reports")
    table = pd.DataFrame({"ticker": ["AAA"], "value": [1.5]})

    path = store.write_csv(table, "register.csv")

    assert path == tmp_path / "reports" / "register.csv"
    pd.testing.assert_frame_equal(pd.read_csv(path), table)


class _HtmlReport:
    def __init__(self) -> None:
        self.silent: bool | None = None

    def to_file(self, output_file: Path, *, silent: bool = False) -> None:
        self.silent = silent
        output_file.write_text("<html></html>", encoding="utf-8")


def test_a_report_is_rendered_silently_into_a_new_directory(tmp_path: Path) -> None:
    store = ReportStore(directory=tmp_path / "reports")
    report = _HtmlReport()

    path = store.write_report(report, "auto_eda.html")

    assert path == tmp_path / "reports" / "auto_eda.html"
    assert path.is_file()
    assert report.silent is True

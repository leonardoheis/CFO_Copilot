from pathlib import Path
from typing import Protocol

import pandas as pd


class FileReport(Protocol):
    """A report that renders itself to a file, like ydata-profiling's."""

    def to_file(self, output_file: Path, *, silent: bool = ...) -> None: ...


class ReportStore:
    """Place generated HTML and CSV reports under one directory.

    Usage::

        store = container.report_store()
        path = store.write_csv(table, "nb01_outlier_register.csv")
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, name: str) -> Path:
        return self._directory / name

    def write_csv(self, table: pd.DataFrame, name: str) -> Path:
        """Write a table as CSV, creating the directory.

        Returns:
            The written file.
        """
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)
        return path

    def write_report(self, report: FileReport, name: str) -> Path:
        """Render a report to a file, creating the directory.

        Returns:
            The written file.
        """
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        report.to_file(path, silent=True)
        return path

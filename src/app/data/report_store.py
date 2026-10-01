from pathlib import Path

import pandas as pd


class ReportStore:
    """Place generated HTML and CSV reports under one directory.

    Usage::

        store = container.report_store()
        path = store.path_for("nb01_auto_eda_panel.html")
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, name: str) -> Path:
        """Name a report file, creating the directory on first use.

        Returns:
            The report's path inside the store's directory.
        """
        self._directory.mkdir(parents=True, exist_ok=True)
        return self._directory / name

    def write_csv(self, table: pd.DataFrame, name: str) -> Path:
        """Write a table as CSV under the store's directory.

        Returns:
            The written file.
        """
        path = self.path_for(name)
        table.to_csv(path, index=False)
        return path

from pathlib import Path

import pandas as pd

from app.data.exceptions import ResultsNotFoundError


class ResultsStore:
    """Append evaluation records to one parquet dataset, partitioned by model.

    Every append writes new files, so earlier runs are never overwritten.

    Usage::

        store = container.results_store()
        store.append(evaluation.records(model="seasonal_naive", provenance=...))
        results = store.read()
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def append(self, records: pd.DataFrame) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        records.to_parquet(self._directory, partition_cols=["model"], index=False)

    def read(self) -> pd.DataFrame:
        """Read every record appended so far.

        Returns:
            All records; ``model`` as a plain string column.

        Raises:
            ResultsNotFoundError: Nothing has been appended yet.
        """
        if not self._directory.exists():
            message = f"No results at {self._directory}"
            raise ResultsNotFoundError(message)
        results = pd.read_parquet(self._directory)
        return results.assign(model=results["model"].astype(str))

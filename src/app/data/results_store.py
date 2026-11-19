import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

import pandas as pd

from app.data.exceptions import ResultsNotFoundError

_RUN_ID: Final = re.compile(r"run-[0-9a-f]{32}")


class ResultsStore:
    """Store complete evaluation runs alongside the legacy model partitions.

    New runs are partitioned by run ID and model.

    Usage::

        store = container.results_store()
        store.append(evaluation.records(model="seasonal_naive", provenance=...))
        results = store.read(run_id=provenance.run_id)
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _run_directory(self, run_id: str) -> Path:
        if _RUN_ID.fullmatch(run_id) is None:
            message = f"Invalid evaluation run ID: {run_id!r}"
            raise ValueError(message)
        return self._directory / f"run_id={run_id}"

    def append(self, records: pd.DataFrame) -> None:
        """Publish one complete run of records.

        Raises:
            ValueError: The records lack a single evaluation run ID.
            FileExistsError: That run has already been stored.
            OSError: The staged run could not be published.
        """
        run_ids = records.get("run_id", pd.Series(dtype=str)).unique()
        if len(run_ids) != 1 or not isinstance(run_id := run_ids[0], str):
            message = "All records in an append must share one evaluation run ID"
            raise ValueError(message)
        destination = self._run_directory(run_id)
        if destination.exists():
            raise FileExistsError(destination)

        self._directory.mkdir(parents=True, exist_ok=True)
        # A hidden staging directory keeps partial files out of dataset reads.
        with TemporaryDirectory(prefix=".pending-", dir=self._directory) as temporary:
            staged = Path(temporary) / "run"
            records.drop(columns="run_id").to_parquet(
                staged, partition_cols=["model"], index=False
            )
            try:
                staged.rename(destination)
            except OSError as error:
                if not destination.exists():
                    raise
                raise FileExistsError(destination) from error

    def read(self, *, run_id: str | None = None) -> pd.DataFrame:
        """Read one evaluation run, or all results when no run ID is given.

        Returns:
            The selected records, with missing IDs for legacy records.

        Raises:
            ResultsNotFoundError: No records exist for the requested selection.
        """
        directory = self._directory if run_id is None else self._run_directory(run_id)
        if not directory.is_dir():
            message = f"No results at {directory}"
            raise ResultsNotFoundError(message)
        results = pd.read_parquet(directory)
        if "model" not in results:
            message = f"No results at {directory}"
            raise ResultsNotFoundError(message)
        stored_ids = (
            pd.Series(run_id, index=results.index, dtype=object)
            if run_id is not None or "run_id" not in results
            else results["run_id"].astype(object)
        )
        return results.assign(
            model=results["model"].astype(str),
            run_id=stored_ids.where(stored_ids.notna(), None),
        )

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.data import ResultsStore
from app.data.exceptions import ResultsNotFoundError


@pytest.fixture
def records() -> pd.DataFrame:
    return pd.DataFrame({
        "model": ["seasonal_naive", "naive"],
        "ticker": ["AAA", "BBB"],
        "origin_date": [date(2024, 3, 31), date(2024, 3, 31)],
        "y_hat_scaled": [4.5, None],
        "git_commit": ["a" * 40] * 2,
    })


def test_appended_records_read_back_equal(
    tmp_path: Path, records: pd.DataFrame
) -> None:
    store = ResultsStore(directory=tmp_path / "results")

    store.append(records)

    pd.testing.assert_frame_equal(
        store.read()[records.columns].sort_values("ticker", ignore_index=True),
        records,
    )


def test_appending_twice_keeps_both_runs(tmp_path: Path, records: pd.DataFrame) -> None:
    store = ResultsStore(directory=tmp_path / "results")

    store.append(records)
    store.append(records.assign(git_commit="b" * 40))

    results = store.read()
    assert len(results) == 2 * len(records)
    assert set(results["git_commit"]) == {"a" * 40, "b" * 40}


def test_reading_before_any_append_is_refused(tmp_path: Path) -> None:
    store = ResultsStore(directory=tmp_path / "results")

    with pytest.raises(ResultsNotFoundError, match="No results"):
        store.read()

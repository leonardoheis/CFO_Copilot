from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.data import ResultsStore
from app.data.exceptions import ResultsNotFoundError

FIRST_RUN = "run-" + "a" * 32
SECOND_RUN = "run-" + "b" * 32


@pytest.fixture
def records() -> pd.DataFrame:
    return pd.DataFrame({
        "model": ["seasonal_naive", "naive"],
        "ticker": ["AAA", "BBB"],
        "origin_date": [date(2024, 3, 31), date(2024, 3, 31)],
        "y_hat_scaled": [4.5, None],
        "git_commit": ["a" * 40] * 2,
        "run_id": [FIRST_RUN] * 2,
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


def test_two_runs_at_one_commit_are_separate(
    tmp_path: Path, records: pd.DataFrame
) -> None:
    store = ResultsStore(directory=tmp_path / "results")

    store.append(records)
    other_run = records.assign(run_id=SECOND_RUN, y_hat_scaled=6.0)
    store.append(other_run)

    for run_id, expected in ((FIRST_RUN, records), (SECOND_RUN, other_run)):
        pd.testing.assert_frame_equal(
            store.read(run_id=run_id)[expected.columns].sort_values(
                "ticker", ignore_index=True
            ),
            expected,
        )
    assert set(store.read()["run_id"]) == {FIRST_RUN, SECOND_RUN}


def test_legacy_records_remain_readable_alongside_a_new_run(
    tmp_path: Path, records: pd.DataFrame
) -> None:
    directory = tmp_path / "results"
    store = ResultsStore(directory=directory)
    legacy = records.drop(columns="run_id").assign(git_commit="b" * 40)
    legacy.to_parquet(directory, partition_cols=["model"], index=False)
    assert store.read()["run_id"].isna().all()

    with pytest.raises(ResultsNotFoundError, match=SECOND_RUN):
        store.read(run_id=SECOND_RUN)

    store.append(records)

    combined = store.read()
    pd.testing.assert_frame_equal(
        combined.loc[combined["run_id"].isna(), legacy.columns].sort_values(
            "ticker", ignore_index=True
        ),
        legacy,
    )
    assert len(store.read(run_id=FIRST_RUN)) == len(records)


def test_the_same_run_cannot_be_appended_twice(
    tmp_path: Path, records: pd.DataFrame
) -> None:
    store = ResultsStore(directory=tmp_path / "results")
    store.append(records)

    with pytest.raises(FileExistsError, match=FIRST_RUN):
        store.append(records)

    assert len(store.read()) == len(records)


def test_an_append_must_contain_exactly_one_run(
    tmp_path: Path, records: pd.DataFrame
) -> None:
    store = ResultsStore(directory=tmp_path / "results")
    two_runs = records.assign(run_id=[FIRST_RUN, SECOND_RUN])

    with pytest.raises(ValueError, match="share one evaluation run ID"):
        store.append(two_runs)


def test_invalid_run_ids_are_rejected(tmp_path: Path) -> None:
    store = ResultsStore(directory=tmp_path / "results")
    with pytest.raises(ValueError, match="Invalid evaluation run ID"):
        store.read(run_id="not-a-run-id")


def test_a_failed_write_is_hidden_and_can_be_retried(
    tmp_path: Path, records: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ResultsStore(directory=tmp_path / "results")
    write_parquet = pd.DataFrame.to_parquet

    def write_then_fail(
        frame: pd.DataFrame,
        path: Path,
        *,
        partition_cols: list[str],
        index: bool,
    ) -> None:
        write_parquet(frame, path, partition_cols=partition_cols, index=index)
        with pytest.raises(ResultsNotFoundError, match="No results"):
            store.read()
        message = "interrupted write"
        raise OSError(message)

    with monkeypatch.context() as patch:
        patch.setattr(pd.DataFrame, "to_parquet", write_then_fail)
        with pytest.raises(OSError, match="interrupted write"):
            store.append(records)

    with pytest.raises(ResultsNotFoundError, match="No results"):
        store.read(run_id=FIRST_RUN)

    store.append(records)
    assert len(store.read(run_id=FIRST_RUN)) == len(records)


def test_reading_before_any_append_is_refused(tmp_path: Path) -> None:
    store = ResultsStore(directory=tmp_path / "results")

    with pytest.raises(ResultsNotFoundError, match="No results"):
        store.read()

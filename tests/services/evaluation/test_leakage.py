import numpy as np
import pandas as pd
import pytest

from app.services.evaluation import (
    EvaluationLeakageError,
    check_no_look_ahead,
    protocol_a_splits,
)

HORIZON = 4
QUARTERS = pd.date_range("2020-03-31", periods=12, freq="QE")


@pytest.fixture
def dataset() -> pd.DataFrame:
    labelled = np.arange(len(QUARTERS)) < len(QUARTERS) - HORIZON
    return pd.DataFrame({
        "ticker": "AAA",
        "origin_date": QUARTERS,
        "target_date": QUARTERS + pd.offsets.QuarterEnd(HORIZON),
        "growth_yoy_lag1": 0.1,
        "target_level": np.where(labelled, 100.0, np.nan),
        "y": np.where(labelled, 0.05, np.nan),
    })


@pytest.fixture
def origin(dataset: pd.DataFrame) -> pd.Timestamp:
    return protocol_a_splits(dataset, n_origins=1)[0].origin


def test_a_protocol_a_split_without_test_labels_passes(dataset: pd.DataFrame) -> None:
    split = protocol_a_splits(dataset, n_origins=1)[0]

    check_no_look_ahead(
        dataset[split.train],
        dataset[split.test].drop(columns=["y", "target_level"]),
        split.origin,
    )


def test_a_training_cut_off_on_the_origin_date_is_refused(
    dataset: pd.DataFrame, origin: pd.Timestamp
) -> None:
    leaking_train = dataset[dataset["origin_date"] < origin]
    test = dataset[dataset["origin_date"] == origin].drop(columns=["y", "target_level"])

    with pytest.raises(
        EvaluationLeakageError,
        match=f"{HORIZON - 1} training rows have a target date after the origin",
    ):
        check_no_look_ahead(leaking_train, test, origin)


def test_test_rows_that_carry_their_labels_are_refused(
    dataset: pd.DataFrame, origin: pd.Timestamp
) -> None:
    train = dataset[dataset["target_date"] <= origin]
    test = dataset[dataset["origin_date"] == origin]

    with pytest.raises(EvaluationLeakageError, match="carry labels: y, target_level"):
        check_no_look_ahead(train, test, origin)


def test_test_rows_from_before_a_training_target_are_refused(
    dataset: pd.DataFrame, origin: pd.Timestamp
) -> None:
    train = dataset[dataset["target_date"] <= origin]
    earlier = dataset[dataset["origin_date"] == QUARTERS[0]]

    with pytest.raises(EvaluationLeakageError, match="1 test rows forecast from"):
        check_no_look_ahead(train, earlier.drop(columns=["y", "target_level"]), origin)

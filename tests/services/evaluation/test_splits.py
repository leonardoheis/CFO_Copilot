import numpy as np
import pandas as pd
import pytest

from app.services.evaluation import TooFewOriginsError, protocol_a_splits

HORIZON = 4
QUARTERS = pd.date_range("2020-03-31", periods=12, freq="QE")
# Origins q0..q7 have a target inside the 12 quarters; q8..q11 do not.
LABELLED_ORIGINS = 8


@pytest.fixture
def dataset() -> pd.DataFrame:
    frame = pd.concat(
        [
            pd.DataFrame({
                "ticker": ticker,
                "origin_date": QUARTERS,
                "target_date": QUARTERS + pd.offsets.QuarterEnd(HORIZON),
                "y": np.where(np.arange(len(QUARTERS)) < LABELLED_ORIGINS, 1.0, np.nan),
            })
            for ticker in ("AAA", "BBB")
        ],
        ignore_index=True,
    )
    # BBB's last labelled quarter is a missing filing: its origin still counts.
    frame.loc[
        (frame["ticker"] == "BBB") & (frame["origin_date"] == QUARTERS[7]), "y"
    ] = np.nan
    return frame


def test_origins_are_the_last_labelled_ones_oldest_first(
    dataset: pd.DataFrame,
) -> None:
    splits = protocol_a_splits(dataset, n_origins=3)

    assert [split.origin for split in splits] == list(QUARTERS[5:8])


def test_training_rows_have_their_target_on_or_before_the_origin(
    dataset: pd.DataFrame,
) -> None:
    last = protocol_a_splits(dataset, n_origins=1)[0]

    trained = dataset[last.train]
    assert set(trained["origin_date"]) == set(QUARTERS[:4])
    assert (trained["target_date"] <= last.origin).all()


def test_the_rows_whose_label_falls_after_the_origin_never_train(
    dataset: pd.DataFrame,
) -> None:
    last = protocol_a_splits(dataset, n_origins=1)[0]

    earlier_labelled = (dataset["origin_date"] < last.origin) & dataset["y"].notna()
    withheld = dataset[earlier_labelled & ~last.train]
    assert withheld.groupby("ticker").size().to_dict() == {
        "AAA": HORIZON - 1,
        "BBB": HORIZON - 1,
    }


def test_test_rows_are_the_origins_rows_with_a_known_target(
    dataset: pd.DataFrame,
) -> None:
    last = protocol_a_splits(dataset, n_origins=1)[0]

    assert dataset.loc[last.test, "ticker"].tolist() == ["AAA"]


def test_no_test_row_trains_at_its_own_origin(dataset: pd.DataFrame) -> None:
    for split in protocol_a_splits(dataset, n_origins=LABELLED_ORIGINS):
        assert not (split.train & split.test).any()


def test_asking_for_more_origins_than_are_labelled_is_refused(
    dataset: pd.DataFrame,
) -> None:
    with pytest.raises(TooFewOriginsError, match="asked for 9 labelled origins"):
        protocol_a_splits(dataset, n_origins=LABELLED_ORIGINS + 1)

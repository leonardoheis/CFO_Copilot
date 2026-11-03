from typing import NamedTuple

import pandas as pd

from app.services.evaluation.exceptions import TooFewOriginsError


class Split(NamedTuple):
    """The rows that train and the rows that test at one origin.

    Both masks are aligned to the dataset's index.
    """

    origin: pd.Timestamp
    train: pd.Series
    test: pd.Series


def protocol_a_splits(dataset: pd.DataFrame, n_origins: int) -> tuple[Split, ...]:
    """Split a feature dataset at its last ``n_origins`` labelled origins (spec R2).

    A row trains at origin t only if its target date is on or before t, so
    the rows with origins t - h + 1 ... t - 1, whose labels fall after t, never
    train.

    Returns:
        One split per origin, oldest first.

    Raises:
        TooFewOriginsError: Fewer origins have a known target than requested.
    """
    labelled = dataset["y"].notna()
    labelled_origins = sorted(dataset.loc[labelled, "origin_date"].unique())
    if len(labelled_origins) < n_origins:
        raise TooFewOriginsError(
            requested=n_origins, available=len(labelled_origins)
        )
    return tuple(
        Split(
            origin=pd.Timestamp(origin),
            train=labelled & (dataset["target_date"] <= origin),
            test=labelled & (dataset["origin_date"] == origin),
        )
        for origin in labelled_origins[-n_origins:]
    )

from typing import NamedTuple

import numpy as np
import pandas as pd
from sklearn.model_selection import LeaveOneGroupOut

from app.services.evaluation.exceptions import TooFewOriginsError
from app.services.features import QUARTERS_READ_BY_FEATURE


class Split(NamedTuple):
    """The rows that train and the rows that test at one origin.

    Both masks are aligned to the dataset's index.
    """

    origin: pd.Timestamp
    train: pd.Series
    test: pd.Series


def protocol_a_splits(dataset: pd.DataFrame, n_origins: int) -> tuple[Split, ...]:
    """Split a feature dataset for Protocol A at its last labelled origins.

    Protocol A scores companies the model was trained on. A row trains at
    origin t only if its target date is on or before t, so the rows with
    origins t - h + 1 ... t - 1, whose labels fall after t, never train
    (``docs/specs/nb02-evaluation-harness.md``, requirement R2).

    Returns:
        One split per origin, oldest first.

    Raises:
        TooFewOriginsError: Fewer origins have a known target than requested.
    """
    labelled = dataset["y"].notna()
    labelled_origins = sorted(dataset.loc[labelled, "origin_date"].unique())
    if len(labelled_origins) < n_origins:
        raise TooFewOriginsError(requested=n_origins, available=len(labelled_origins))
    return tuple(
        Split(
            origin=pd.Timestamp(origin),
            train=labelled & (dataset["target_date"] <= origin),
            test=labelled & (dataset["origin_date"] == origin),
        )
        for origin in labelled_origins[-n_origins:]
    )


class HeldOutCompany(NamedTuple):
    """One company left out of training, with Protocol A's splits for it."""

    ticker: str
    splits: tuple[Split, ...]


def protocol_b_splits(
    dataset: pd.DataFrame, n_origins: int
) -> tuple[HeldOutCompany, ...]:
    """Protocol A's splits once per company, with that company held out.

    Leave-one-company-out (spec R3): a held-out company never trains and is
    the only one tested.

    Returns:
        One entry per company, in ticker order; its splits oldest origin first.
    """
    splits = protocol_a_splits(dataset, n_origins)
    tickers = dataset["ticker"]
    held_out_companies = []
    for _, held_out_rows in LeaveOneGroupOut().split(dataset, groups=tickers):
        held_out = pd.Series(data=False, index=dataset.index)
        held_out.iloc[held_out_rows] = True
        held_out_companies.append(
            HeldOutCompany(
                ticker=str(tickers.iloc[held_out_rows[0]]),
                splits=tuple(
                    split._replace(
                        train=split.train & ~held_out, test=split.test & held_out
                    )
                    for split in splits
                ),
            )
        )
    return tuple(held_out_companies)


def truncate_history(features: pd.DataFrame, history: int) -> pd.DataFrame:
    """Blank the features a company with only ``history`` quarters cannot have.

    Returns:
        A copy of ``features`` with every growth feature that reads more than
        ``history`` quarters set to NaN, not imputed (spec R3).
    """
    beyond_history = [
        column
        for column, quarters in QUARTERS_READ_BY_FEATURE.items()
        if quarters > history and column in features.columns
    ]
    truncated = features.copy()
    truncated[beyond_history] = np.nan
    return truncated

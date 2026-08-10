from datetime import date

import pandas as pd
import pytest

from app.data.splits import cumulative_split_factors


def test_cumulative_split_factors_returns_one_without_splits() -> None:
    index = pd.DatetimeIndex([date(2020, 3, 31), date(2020, 6, 30)])

    factors = cumulative_split_factors(pd.Series(dtype=float), index)

    assert factors.tolist() == [1.0, 1.0]


def test_cumulative_split_factors_applies_future_split() -> None:
    splits = pd.Series([20.0], index=pd.DatetimeIndex([date(2022, 6, 6)]))
    index = pd.DatetimeIndex([date(2020, 3, 31), date(2022, 6, 30)])

    factors = cumulative_split_factors(splits, index)

    assert factors.tolist() == [20.0, 1.0]


def test_cumulative_split_factors_excludes_split_on_date() -> None:
    split_date = date(2022, 6, 30)
    splits = pd.Series([20.0], index=pd.DatetimeIndex([split_date]))
    index = pd.DatetimeIndex([pd.Timestamp(split_date)])

    factors = cumulative_split_factors(splits, index)

    assert factors.iloc[0] == pytest.approx(1.0)


def test_cumulative_split_factors_compounds_future_splits() -> None:
    splits = pd.Series(
        [2.0, 3.0, 5.0],
        index=pd.DatetimeIndex(
            [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)],
        ),
    )
    index = pd.DatetimeIndex([date(2019, 12, 31), date(2020, 12, 31)])

    factors = cumulative_split_factors(splits, index)

    assert factors.tolist() == [30.0, 15.0]

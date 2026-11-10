from collections.abc import Callable, Sequence
from typing import NamedTuple

import numpy as np
import pandas as pd
from pydantic import BaseModel
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    root_mean_squared_error,
)

from app.domain import TargetVariable
from app.services.evaluation.exceptions import UndefinedMetricError
from app.services.evaluation.models import IntervalMetrics, PointMetrics
from app.services.features.transforms import TargetFamily, target_family


class PointMetricTables(NamedTuple):
    """Point metrics pooled, per sector and per company, always produced together."""

    pooled: pd.DataFrame
    by_sector: pd.DataFrame
    by_company: pd.DataFrame


class IntervalMetricTables(NamedTuple):
    """Interval metrics per level, pooled and per sector."""

    pooled: pd.DataFrame
    by_sector: pd.DataFrame


def in_sample_scale(
    seasonal_naive_errors: pd.DataFrame, origin: pd.Timestamp
) -> pd.Series:
    """Each company's seasonal-naive MAE over its rows that train at ``origin``.

    ``seasonal_naive_errors`` holds ``ticker, target_date, error`` on the shared
    error scale; the result is MASE's denominator.

    Returns:
        The scale per ticker.
    """
    trained = seasonal_naive_errors[seasonal_naive_errors["target_date"] <= origin]
    return trained["error"].abs().groupby(trained["ticker"]).mean()


def mape(y_level: pd.Series, y_hat_level: pd.Series, variable: TargetVariable) -> float:
    """scikit-learn's MAPE on levels, refused for a target that can be zero.

    Returns:
        The MAPE as a fraction.

    Raises:
        UndefinedMetricError: The target can be zero or negative, where a
            percentage error explodes (operating income reaches 143 in the
            panel).
    """
    if target_family(variable) is not TargetFamily.POSITIVE:
        raise UndefinedMetricError(metric="MAPE", variable=variable.value)
    return float(mean_absolute_percentage_error(y_level, y_hat_level))


def _group_metrics(rows: pd.DataFrame, variable: TargetVariable) -> PointMetrics:
    missing = int(rows["y_hat_scaled"].isna().sum())
    has_mape = target_family(variable) is TargetFamily.POSITIVE
    if missing:
        return PointMetrics(
            rows=len(rows),
            missing=missing,
            mae=np.nan,
            rmse=np.nan,
            mase=np.nan,
            oos_r2=np.nan,
            mape=np.nan if has_mape else None,
        )
    y, y_hat, scale = rows["y_scaled"], rows["y_hat_scaled"], rows["mase_scale"]
    return PointMetrics(
        rows=len(rows),
        missing=0,
        mae=float(mean_absolute_error(y, y_hat)),
        rmse=float(root_mean_squared_error(y, y_hat)),
        # Mean of |error| / the company's scale: MAE of the rescaled values.
        mase=float(mean_absolute_error(y / scale, y_hat / scale)),
        # Campbell and Thompson (2008): r2_score would compare with the mean of y.
        oos_r2=float(
            1
            - mean_squared_error(y, y_hat)
            / mean_squared_error(y, rows["baseline_scaled"])
        ),
        mape=mape(rows["y_level"], rows["y_hat_level"], variable) if has_mape else None,
    )


def _by_group(
    frame: pd.DataFrame,
    by: Sequence[str],
    score: Callable[[pd.DataFrame], BaseModel],
) -> pd.DataFrame:
    if not by:
        return pd.DataFrame([score(frame).model_dump(exclude_none=True)])
    return pd.DataFrame([
        dict(zip(by, keys, strict=True)) | score(group).model_dump(exclude_none=True)
        for keys, group in frame.groupby(list(by), observed=True)
    ])


def point_metrics(
    scored: pd.DataFrame, *, variable: TargetVariable, by: Sequence[str] = ()
) -> pd.DataFrame:
    """Score predictions on the shared error scale, grouped by ``by``.

    ``scored`` holds one row per test row: ``y_scaled``, ``y_hat_scaled``,
    ``baseline_scaled`` (the baseline to beat's prediction), ``mase_scale``,
    and for revenue ``y_level`` and ``y_hat_level``. A group with a missing
    prediction is reported with its count and no metrics.

    Returns:
        One row per group: the ``by`` columns, ``rows``, ``missing``, ``mae``,
        ``rmse``, ``mase``, ``oos_r2``, and ``mape`` for revenue.
    """
    return _by_group(scored, by, lambda rows: _group_metrics(rows, variable))


def winkler_score(intervals: pd.DataFrame) -> pd.Series:
    """Interval width plus 2 / (1 - level) per unit by which ``y`` falls outside.

    Winkler (1972); Gneiting and Raftery (2007, §6.2) call it the interval
    score. ``intervals`` holds ``level``, ``lower_scaled``, ``upper_scaled``
    and ``y_scaled``.

    Returns:
        The score per row; lower is better.
    """
    y, lower, upper = (
        intervals["y_scaled"],
        intervals["lower_scaled"],
        intervals["upper_scaled"],
    )
    outside = (lower - y).clip(lower=0) + (y - upper).clip(lower=0)
    return (upper - lower) + 2 / (1 - intervals["level"]) * outside


def _interval_group_metrics(rows: pd.DataFrame) -> IntervalMetrics:
    missing = int(rows[["lower_scaled", "upper_scaled"]].isna().any(axis=1).sum())
    if missing:
        return IntervalMetrics(
            rows=len(rows),
            missing=missing,
            coverage=np.nan,
            mean_width=np.nan,
            mean_winkler_score=np.nan,
        )
    y = rows["y_scaled"]
    return IntervalMetrics(
        rows=len(rows),
        missing=0,
        coverage=float(y.between(rows["lower_scaled"], rows["upper_scaled"]).mean()),
        mean_width=float((rows["upper_scaled"] - rows["lower_scaled"]).mean()),
        mean_winkler_score=float(winkler_score(rows).mean()),
    )


def interval_metrics(
    intervals: pd.DataFrame, *, by: Sequence[str] = ()
) -> pd.DataFrame:
    """Score intervals per level on the shared error scale, grouped by ``by``.

    ``intervals`` holds one row per test row and level: ``level``,
    ``lower_scaled``, ``upper_scaled`` and ``y_scaled``. A group with a
    missing interval is reported with its count and no metrics.

    Returns:
        One row per level and group: ``level``, the ``by`` columns, ``rows``,
        ``missing``, ``coverage``, ``mean_width`` and ``mean_winkler_score``.
    """
    return _by_group(intervals, ["level", *by], _interval_group_metrics)


def point_metric_tables(
    scored: pd.DataFrame, *, variable: TargetVariable
) -> PointMetricTables:
    """Score pooled, per sector and per company in one call.

    Returns:
        The three tables; a pooled number never travels without its sectors.
    """
    return PointMetricTables(
        pooled=point_metrics(scored, variable=variable),
        by_sector=point_metrics(scored, variable=variable, by=["sector"]),
        by_company=point_metrics(scored, variable=variable, by=["sector", "ticker"]),
    )


def interval_metric_tables(intervals: pd.DataFrame) -> IntervalMetricTables:
    """Score intervals pooled and per sector in one call (spec R8).

    Returns:
        The two tables; pooled coverage can hide sectors that under-cover.
    """
    return IntervalMetricTables(
        pooled=interval_metrics(intervals),
        by_sector=interval_metrics(intervals, by=["sector"]),
    )

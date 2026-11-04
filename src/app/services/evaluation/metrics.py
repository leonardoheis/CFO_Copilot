from collections.abc import Sequence
from typing import NamedTuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    root_mean_squared_error,
)

from app.domain import TargetVariable
from app.services.evaluation.exceptions import UndefinedMetricError
from app.services.evaluation.models import PointMetrics
from app.services.features.transforms import TargetFamily, target_family


class PointMetricTables(NamedTuple):
    """Point metrics pooled, per sector and per company, always produced together."""

    pooled: pd.DataFrame
    by_sector: pd.DataFrame
    by_company: pd.DataFrame


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
            1 - mean_squared_error(y, y_hat) / mean_squared_error(y, rows["baseline_scaled"])
        ),
        mape=mape(rows["y_level"], rows["y_hat_level"], variable) if has_mape else None,
    )


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
    if not by:
        return pd.DataFrame([_group_metrics(scored, variable).model_dump(exclude_none=True)])
    return pd.DataFrame([
        dict(zip(by, keys, strict=True))
        | _group_metrics(group, variable).model_dump(exclude_none=True)
        for keys, group in scored.groupby(list(by), observed=True)
    ])


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

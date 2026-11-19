from collections.abc import Mapping
from copy import copy
from enum import StrEnum
from typing import Self, assert_never

import numpy as np
import pandas as pd

from app.domain import TargetVariable
from app.services.evaluation.models import ForecastTask
from app.services.features.transforms import (
    SEASONAL_LAG,
    TargetFamily,
    TargetTransformer,
    log_level,
    target_family,
)


class Baseline(StrEnum):
    SEASONAL_NAIVE = "seasonal_naive"
    SEASONAL_NAIVE_GROWTH = "seasonal_naive_growth"
    NAIVE = "naive"
    DRIFT = "drift"


def _drift_per_quarter(series: pd.Series, history: int | None) -> pd.Series:
    values = series.to_numpy(dtype=float)
    positions = np.arange(values.size)
    # The first reported quarter at or after each position; past the end if none.
    first_reported_from = np.minimum.accumulate(
        np.where(np.isnan(values), values.size, positions)[::-1]
    )[::-1]
    window_start = (
        np.zeros_like(positions)
        if history is None
        else np.maximum(positions - history + 1, 0)
    )
    first = first_reported_from[window_start]
    quarters_elapsed = (positions - first).astype(float)
    quarters_elapsed[quarters_elapsed <= 0] = np.nan
    first_value = np.append(values, np.nan)[first]
    return pd.Series((values - first_value) / quarters_elapsed, index=series.index)


def baseline_levels(
    panel: pd.DataFrame,
    *,
    variable: TargetVariable,
    horizon: int,
    baseline: Baseline,
    history: int | None = None,
) -> pd.Series:
    """Forecast one company's level at each origin + horizon from its past quarters.

    Revenue is extrapolated in logs and a signed target in levels, the scale its
    errors are compared on (see ``on_error_scale``). Drift runs from the first
    reported quarter, within the last ``history`` quarters when given (a
    Protocol B company with that much history).

    Returns:
        The forecast level indexed like ``panel``; NaN where the history is
        too short.
    """
    positive = target_family(variable) is TargetFamily.POSITIVE
    series = log_level(panel[variable]) if positive else panel[variable]
    year_earlier = series.shift(SEASONAL_LAG - horizon)
    match baseline:
        case Baseline.SEASONAL_NAIVE:
            forecast = year_earlier
        case Baseline.SEASONAL_NAIVE_GROWTH:
            forecast = year_earlier + series.diff(SEASONAL_LAG)
        case Baseline.NAIVE:
            forecast = series
        case Baseline.DRIFT:
            forecast = series + horizon * _drift_per_quarter(series, history)
        case _ as unreachable:
            assert_never(unreachable)
    return pd.Series(np.exp(forecast), index=panel.index) if positive else forecast


class BaselineForecaster:
    """A baseline behind the ``Forecaster`` interface, so it is scored like a model.

    Usage::

        task = ForecastTask(variable=variable, arm=TargetArm.LOG_DIFF4, horizon=1)
        naive = BaselineForecaster(Baseline.SEASONAL_NAIVE, panels=panels, task=task)
        y_hat = naive.fit(train).predict(test)["y_hat"]
    """

    def __init__(
        self,
        baseline: Baseline,
        *,
        panels: Mapping[str, pd.DataFrame],
        task: ForecastTask,
    ) -> None:
        self._baseline = baseline
        self._panels = panels
        self._task = task
        self._targets_by_history: dict[int | None, pd.Series] = {}

    def for_fold(self) -> "BaselineForecaster":
        """Copy a fixed-rule baseline for one fold while retaining its targets.

        Returns:
            A new forecaster sharing only the panel inputs and their cached targets.
        """
        return copy(self)

    def _targets(self, history: int | None) -> pd.Series:
        if history not in self._targets_by_history:
            task = self._task
            transformer = TargetTransformer(arm=task.arm, horizon=task.horizon)
            self._targets_by_history[history] = pd.concat([
                pd.Series(
                    transformer.target_for(
                        panel[task.variable],
                        baseline_levels(
                            panel,
                            variable=task.variable,
                            horizon=task.horizon,
                            baseline=self._baseline,
                            history=history,
                        ),
                        revenue=panel[TargetVariable.REVENUE],
                    ).to_numpy(),
                    index=pd.MultiIndex.from_arrays([panel["ticker"], panel["date"]]),
                )
                for panel in self._panels.values()
            ])
        return self._targets_by_history[history]

    def fit(self, _train: pd.DataFrame, /) -> Self:
        """Learn nothing: a baseline is a fixed rule over each company's history.

        Returns:
            This forecaster.
        """
        return self

    def predict(
        self, test: pd.DataFrame, /, *, history: int | None = None
    ) -> pd.DataFrame:
        """Look up the baseline's target for every test row, from ``history`` quarters.

        Returns:
            ``y_hat`` indexed like ``test``.
        """
        keys = pd.MultiIndex.from_arrays([test["ticker"], test["origin_date"]])
        return pd.DataFrame(
            {"y_hat": self._targets(history).reindex(keys).to_numpy()},
            index=test.index,
        )

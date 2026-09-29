from enum import StrEnum
from typing import Final

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator

from app.services.features.exceptions import InvalidHorizonError, NonPositiveValueError

SEASONAL_LAG: Final = 4
MAX_HORIZON: Final = SEASONAL_LAG


class TargetArm(StrEnum):
    LOG_DIFF1 = "log_diff1"
    LOG_DIFF4 = "log_diff4"
    SEASNAIVE_RESIDUAL = "seasnaive_residual"


def log_level(values: pd.Series) -> pd.Series:
    """Take the natural log, refusing zero and negative values.

    Returns:
        The log series, NaN where the input is NaN.

    Raises:
        NonPositiveValueError: Any value is zero or negative.
    """
    non_positive = int((values <= 0).sum())
    if non_positive:
        raise NonPositiveValueError(count=non_positive)
    return pd.Series(np.log(values), index=values.index)


def yoy_log_growth(values: pd.Series) -> pd.Series:
    return log_level(values).diff(SEASONAL_LAG)


class TargetTransformer(BaseModel):
    """Build and invert one arm's target at one horizon.

    Usage::

        transformer = TargetTransformer(arm=TargetArm.LOG_DIFF4, horizon=2)
        y = transformer.make(revenue)
        level = transformer.reconstruct(revenue, prediction)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: TargetArm
    horizon: int

    @field_validator("horizon")
    @classmethod
    def _supported_horizon(cls, horizon: int) -> int:
        if not 1 <= horizon <= MAX_HORIZON:
            raise InvalidHorizonError(horizon=horizon, max_horizon=MAX_HORIZON)
        return horizon

    def make(self, values: pd.Series) -> pd.Series:
        """Build the target for the origin held in each row.

        Returns:
            The transformed target indexed like ``values``; NaN where unknown.
        """
        log_values = log_level(values)
        future = log_values.shift(-self.horizon)
        year_earlier = log_values.shift(SEASONAL_LAG - self.horizon)
        if self.arm is TargetArm.LOG_DIFF1:
            return future - log_values
        if self.arm is TargetArm.LOG_DIFF4:
            return future - year_earlier
        return future - year_earlier - log_values.diff(SEASONAL_LAG)

    def reconstruct(
        self, values: pd.Series, prediction: pd.Series, *, shrinkage: float = 1.0
    ) -> pd.Series:
        """Turn a target-space prediction into a level at origin + horizon.

        Returns:
            The predicted level indexed by origin row. ``shrinkage`` scales the
            prediction on the residual arm only.
        """
        log_values = log_level(values)
        year_earlier = log_values.shift(SEASONAL_LAG - self.horizon)
        if self.arm is TargetArm.LOG_DIFF1:
            predicted_log = log_values + prediction
        elif self.arm is TargetArm.LOG_DIFF4:
            predicted_log = year_earlier + prediction
        else:
            predicted_log = (
                year_earlier + log_values.diff(SEASONAL_LAG) + shrinkage * prediction
            )
        return pd.Series(np.exp(predicted_log), index=values.index)

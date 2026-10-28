from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Self, assert_never

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.data.dates import QUARTERS_PER_YEAR
from app.domain import TargetVariable
from app.services.features.exceptions import (
    InvalidHorizonError,
    MissingRevenueError,
    NonPositiveValueError,
)

SEASONAL_LAG: Final = QUARTERS_PER_YEAR
MAX_HORIZON: Final = SEASONAL_LAG


class TargetArm(StrEnum):
    LOG_DIFF1 = "log_diff1"
    LOG_DIFF4 = "log_diff4"
    SEASNAIVE_RESIDUAL = "seasnaive_residual"
    REVENUE_SCALED_YOY = "revenue_scaled_yoy"


class TargetFamily(StrEnum):
    POSITIVE = "positive"
    SIGNED = "signed"


def target_family(variable: str) -> TargetFamily:
    """Classify a column by whether it can be zero or negative.

    Returns:
        Positive for revenue, which never is and so is measured in logs;
        signed for every other column.
    """
    if variable == TargetVariable.REVENUE:
        return TargetFamily.POSITIVE
    return TargetFamily.SIGNED


class TargetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    arms: tuple[TargetArm, ...]
    default_arm: TargetArm

    @model_validator(mode="after")
    def _default_is_an_allowed_arm(self) -> Self:
        if self.default_arm not in self.arms:
            msg = f"default arm {self.default_arm} is not among {self.arms}"
            raise ValueError(msg)
        return self


TARGET_POLICIES: Final[Mapping[TargetFamily, TargetPolicy]] = {
    TargetFamily.POSITIVE: TargetPolicy(
        arms=(
            TargetArm.LOG_DIFF1,
            TargetArm.LOG_DIFF4,
            TargetArm.SEASNAIVE_RESIDUAL,
        ),
        # Master plan D4.
        default_arm=TargetArm.SEASNAIVE_RESIDUAL,
    ),
    TargetFamily.SIGNED: TargetPolicy(
        arms=(TargetArm.REVENUE_SCALED_YOY,),
        default_arm=TargetArm.REVENUE_SCALED_YOY,
    ),
}


def arms_for(variable: TargetVariable) -> tuple[TargetArm, ...]:
    """Name the target arms a variable can be forecast with.

    Returns:
        The arms of the variable's family.
    """
    return TARGET_POLICIES[target_family(variable)].arms


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


def default_arm(variable: TargetVariable) -> TargetArm:
    """Name the arm NB01 exports for a variable.

    Returns:
        The default arm of the variable's family.
    """
    return TARGET_POLICIES[target_family(variable)].default_arm


def yoy_log_growth(values: pd.Series) -> pd.Series:
    return log_level(values).diff(SEASONAL_LAG)


def trailing_revenue(revenue: pd.Series) -> pd.Series:
    return revenue.rolling(SEASONAL_LAG).sum()


def revenue_scaled_yoy_change(values: pd.Series, revenue: pd.Series) -> pd.Series:
    """Change against the same quarter a year earlier, per unit of trailing revenue.

    Returns:
        Defined for negative values; NaN until four quarters of revenue exist.
    """
    return (values - values.shift(SEASONAL_LAG)) / trailing_revenue(revenue)


def target_growth(
    variable: TargetVariable, values: pd.Series, revenue: pd.Series
) -> pd.Series:
    """Year-over-year growth of a target, in the family its arms use.

    Returns:
        Log growth for revenue, the revenue-scaled change otherwise.
    """
    match target_family(variable):
        case TargetFamily.POSITIVE:
            return yoy_log_growth(values)
        case TargetFamily.SIGNED:
            return revenue_scaled_yoy_change(values, revenue)
        case _ as unreachable:
            assert_never(unreachable)


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

    def _trailing_revenue(self, revenue: pd.Series | None) -> pd.Series:
        if revenue is None:
            raise MissingRevenueError(arm=self.arm.value)
        return trailing_revenue(revenue)

    def make(self, values: pd.Series, *, revenue: pd.Series | None = None) -> pd.Series:
        """Build the target for the origin held in each row.

        ``revenue`` is required by the revenue-scaled arm and unused by the others.

        Returns:
            The transformed target indexed like ``values``; NaN where unknown.
        """
        if self.arm is TargetArm.REVENUE_SCALED_YOY:
            change = values.shift(-self.horizon) - values.shift(
                SEASONAL_LAG - self.horizon
            )
            return change / self._trailing_revenue(revenue)
        log_values = log_level(values)
        future = log_values.shift(-self.horizon)
        year_earlier = log_values.shift(SEASONAL_LAG - self.horizon)
        match self.arm:
            case TargetArm.LOG_DIFF1:
                return future - log_values
            case TargetArm.LOG_DIFF4:
                return future - year_earlier
            case TargetArm.SEASNAIVE_RESIDUAL:
                return future - year_earlier - log_values.diff(SEASONAL_LAG)
            case _ as unreachable:
                assert_never(unreachable)

    def reconstruct(
        self,
        values: pd.Series,
        prediction: pd.Series,
        *,
        shrinkage: float = 1.0,
        revenue: pd.Series | None = None,
    ) -> pd.Series:
        """Turn a target-space prediction into a level at origin + horizon.

        Returns:
            The predicted level indexed by origin row. ``shrinkage`` scales the
            prediction on the residual arm only; ``revenue`` is required by the
            revenue-scaled arm.
        """
        if self.arm is TargetArm.REVENUE_SCALED_YOY:
            year_earlier_level = values.shift(SEASONAL_LAG - self.horizon)
            return year_earlier_level + prediction * self._trailing_revenue(revenue)
        log_values = log_level(values)
        year_earlier = log_values.shift(SEASONAL_LAG - self.horizon)
        match self.arm:
            case TargetArm.LOG_DIFF1:
                predicted_log = log_values + prediction
            case TargetArm.LOG_DIFF4:
                predicted_log = year_earlier + prediction
            case TargetArm.SEASNAIVE_RESIDUAL:
                predicted_log = (
                    year_earlier
                    + log_values.diff(SEASONAL_LAG)
                    + shrinkage * prediction
                )
            case _ as unreachable:
                assert_never(unreachable)
        return pd.Series(np.exp(predicted_log), index=values.index)

import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.diagnostics.transform_comparison import (
    LevelTransform,
    TransformPolicy,
    baseline_transform,
    candidates_for,
)
from app.services.features.transforms import (
    TargetArm,
    TargetPolicy,
    TargetVariable,
    arms_for,
    default_arm,
    revenue_scaled_yoy_change,
    target_growth,
    yoy_log_growth,
)

POSITIVE_CANDIDATES = (
    LevelTransform.NONE,
    LevelTransform.LOG,
    LevelTransform.SQRT,
    LevelTransform.BOX_COX,
    LevelTransform.BOX_COX_SECTOR,
)
SIGNED_CANDIDATES = (
    LevelTransform.NONE,
    LevelTransform.REVENUE_SCALED,
    LevelTransform.ASINH,
    LevelTransform.YEO_JOHNSON,
    LevelTransform.YEO_JOHNSON_SECTOR,
)
LOG_ARMS = (TargetArm.LOG_DIFF1, TargetArm.LOG_DIFF4, TargetArm.SEASNAIVE_RESIDUAL)
SIGNED_VARIABLES = [
    variable for variable in TargetVariable if variable is not TargetVariable.REVENUE
]
VALUES = pd.Series([10.0, 12.0, 11.0, 13.0, 14.0, 15.0, 13.0, 16.0])
REVENUE = pd.Series([100.0, 110.0, 105.0, 120.0, 125.0, 130.0, 128.0, 140.0])


def test_revenue_is_forecast_in_logs() -> None:
    variable = TargetVariable.REVENUE

    assert arms_for(variable) == LOG_ARMS
    assert default_arm(variable) is TargetArm.SEASNAIVE_RESIDUAL
    assert candidates_for(variable) == POSITIVE_CANDIDATES
    assert baseline_transform(variable) is LevelTransform.LOG
    pd.testing.assert_series_equal(
        target_growth(variable, VALUES, REVENUE), yoy_log_growth(VALUES)
    )


@pytest.mark.parametrize("variable", SIGNED_VARIABLES)
def test_a_signed_target_is_scaled_by_revenue(variable: TargetVariable) -> None:
    assert arms_for(variable) == (TargetArm.REVENUE_SCALED_YOY,)
    assert default_arm(variable) is TargetArm.REVENUE_SCALED_YOY
    assert candidates_for(variable) == SIGNED_CANDIDATES
    assert baseline_transform(variable) is LevelTransform.REVENUE_SCALED
    pd.testing.assert_series_equal(
        target_growth(variable, VALUES, REVENUE),
        revenue_scaled_yoy_change(VALUES, REVENUE),
    )


def test_a_policy_refuses_a_default_outside_its_arms() -> None:
    with pytest.raises(ValidationError, match="default arm"):
        TargetPolicy(
            arms=(TargetArm.REVENUE_SCALED_YOY,), default_arm=TargetArm.LOG_DIFF4
        )


def test_a_policy_refuses_a_baseline_outside_its_candidates() -> None:
    with pytest.raises(ValidationError, match="baseline"):
        TransformPolicy(candidates=(LevelTransform.NONE,), baseline=LevelTransform.LOG)


def test_a_column_that_is_not_a_target_is_compared_as_signed() -> None:
    assert candidates_for("net_income_usd_m") == SIGNED_CANDIDATES
    assert baseline_transform("net_income_usd_m") is LevelTransform.REVENUE_SCALED

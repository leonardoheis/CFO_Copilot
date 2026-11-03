from typing import assert_never

import pandas as pd

from app.domain import TargetVariable
from app.services.features.transforms import (
    TargetArm,
    TargetFamily,
    TargetTransformer,
    log_level,
    target_family,
    trailing_revenue,
)


def on_error_scale(
    variable: TargetVariable, level: pd.Series, revenue: pd.Series
) -> pd.Series:
    """Put a level at origin + horizon on the one scale all models' errors share.

    ``level`` and ``revenue`` are indexed by origin row. The scale is fixed in
    ``docs/specs/nb02-evaluation-harness.md``, requirement R5.

    Returns:
        Revenue as a log level, so an error of 0.05 is about 5 %. A target that
        can be negative (operating income, EBITDA, free cash flow) divided by
        the company's trailing four-quarter revenue at the origin, so an error
        of 0.02 is 2 % of a year's revenue.
    """
    match target_family(variable):
        case TargetFamily.POSITIVE:
            return log_level(level)
        case TargetFamily.SIGNED:
            return level / trailing_revenue(revenue)
        case _ as unreachable:
            assert_never(unreachable)


def reconstruct_on_error_scale(
    panel: pd.DataFrame,
    *,
    variable: TargetVariable,
    arm: TargetArm,
    horizon: int,
    prediction: pd.Series,
) -> pd.DataFrame:
    """Turn one company's target-space predictions into levels and error-scale values.

    ``panel`` holds one company's consecutive quarters in date order;
    ``prediction`` is indexed by origin date and may leave origins out.

    Returns:
        One row per panel quarter: ``ticker, origin_date, y_level, y_hat_level,
        y_scaled, y_hat_scaled``; NaN where the target or the prediction is
        missing.
    """
    values = panel[variable]
    revenue = panel[TargetVariable.REVENUE]
    aligned_prediction = pd.Series(
        prediction.reindex(panel["date"]).to_numpy(), index=panel.index
    )
    y_level = values.shift(-horizon)
    # Shrinkage is a model's choice, applied to its own prediction; the
    # harness only inverts the arm.
    y_hat_level = TargetTransformer(arm=arm, horizon=horizon).reconstruct(
        values, aligned_prediction, revenue=revenue
    )
    return pd.DataFrame({
        "ticker": panel["ticker"],
        "origin_date": panel["date"],
        "y_level": y_level,
        "y_hat_level": y_hat_level,
        "y_scaled": on_error_scale(variable, y_level, revenue),
        "y_hat_scaled": on_error_scale(variable, y_hat_level, revenue),
    })

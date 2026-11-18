from typing import assert_never

import numpy as np
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


def _peer_median(values: np.ndarray, sectors: np.ndarray, company: int) -> float:
    others = np.arange(values.size) != company
    same_sector = others & (sectors == sectors[company])
    return float(np.nanmedian(values[same_sector if same_sector.any() else others]))


def sector_peer_scales(scales: pd.DataFrame) -> pd.Series:
    """Median error scale of each company's sector peers at each origin.

    ``scales`` holds ``ticker, origin_date, sector, mase_scale``. A company is
    never its own peer; one alone in its sector takes the median of every
    other company.

    Returns:
        The peers' scale, indexed by ticker and origin date.
    """
    by_origin: list[pd.Series] = []
    for _, at_origin in scales.groupby("origin_date"):
        values = at_origin["mase_scale"].to_numpy(dtype=float)
        sectors = at_origin["sector"].to_numpy()
        by_origin.append(
            pd.Series(
                [_peer_median(values, sectors, i) for i in range(values.size)],
                index=pd.MultiIndex.from_frame(at_origin[["ticker", "origin_date"]]),
            )
        )
    peer_scales: pd.Series = pd.concat(by_origin)
    return peer_scales


def credibility_weighted_scale(
    own_scale: pd.Series,
    own_errors: pd.Series,
    peer_scale: pd.Series,
    *,
    prior_errors: int,
) -> pd.Series:
    """Blend a company's own error scale with its peers' by how many errors it rests on.

    Credibility weighting (Bühlmann and Gisler, 2005): the peers' scale counts
    as ``prior_errors`` errors. A company with none of its own takes the
    peers' scale, one with ``prior_errors`` sits halfway, and one with many
    keeps nearly its own.

    Returns:
        The blended scale, aligned to ``own_scale``.
    """
    return (own_errors * own_scale.fillna(0.0) + prior_errors * peer_scale) / (
        own_errors + prior_errors
    )


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

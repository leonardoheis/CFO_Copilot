import math
from collections.abc import Sequence

import numpy as np
import pandas as pd


def _conformal_quantile(scores: np.ndarray, level: float) -> float:
    rank = math.ceil((scores.size + 1) * level)
    if rank <= 0:
        return 0.0
    # Too few calibration errors to promise the level: the honest interval is unbounded.
    if rank > scores.size:
        return math.inf
    return float(np.sort(scores)[rank - 1])


def rolling_half_widths(
    errors: pd.DataFrame,
    origins: Sequence[pd.Timestamp],
    *,
    level: float,
    window: int,
    step: float,
) -> pd.Series:
    """Half-width of the ``level`` interval at each origin, from earlier errors.

    ``errors`` holds ``origin_date, target_date, error`` on the shared error
    scale, for every origin the model was refit at. At origin t only errors
    whose target date is on or before t calibrate, from the latest ``window``
    origins among them (``docs/specs/nb02-evaluation-harness.md``, R8). ACI
    (Gibbs and Candès, 2021) moves the miscoverage by ``step`` times the gap
    between the target and the observed miss rate of every earlier interval
    whose outcome is known by t.

    Returns:
        The half-width per origin, indexed by origin date.
    """
    target_miscoverage = 1 - level
    scored = errors.dropna(subset=["error"]).assign(score=lambda f: f["error"].abs())
    half_widths: dict[pd.Timestamp, float] = {}
    for origin in origins:
        known = scored[scored["target_date"] <= origin]
        recent = sorted(known["origin_date"].unique())[-window:]
        calibration = known.loc[known["origin_date"].isin(recent), "score"]
        outcome_known = set(known["origin_date"])
        observed_misses = [
            float((known.loc[known["origin_date"] == issued, "score"] > width).mean())
            for issued, width in half_widths.items()
            if issued in outcome_known
        ]
        miscoverage = target_miscoverage + step * sum(
            target_miscoverage - miss for miss in observed_misses
        )
        half_widths[origin] = _conformal_quantile(
            calibration.to_numpy(), 1 - miscoverage
        )
    return pd.Series(half_widths)

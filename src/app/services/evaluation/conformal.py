import math
from collections.abc import Sequence
from typing import NamedTuple, Self

import numpy as np
import pandas as pd


class _IssuedInterval(NamedTuple):
    """An interval issued at an origin, whose misses ACI checks once known."""

    origin: np.datetime64
    half_width: float


def _conformal_quantile(scores: np.ndarray, level: float) -> float:
    rank = math.ceil((scores.size + 1) * level)
    if rank <= 0:
        return 0.0
    # Too few calibration errors to promise the level: the honest interval is unbounded.
    if rank > scores.size:
        return math.inf
    return float(np.sort(scores)[rank - 1])


class _ScoredErrors(NamedTuple):
    """Absolute errors with their origin and target dates, as NumPy arrays.

    Arrays, not a frame: the jackknife calibrates once per company, and frame
    filters inside its loops made that minutes instead of seconds.
    """

    origin_dates: np.ndarray
    target_dates: np.ndarray
    scores: np.ndarray

    @classmethod
    def from_frame(cls, errors: pd.DataFrame) -> Self:
        scored = errors.dropna(subset=["error"])
        return cls(
            origin_dates=scored["origin_date"].to_numpy(),
            target_dates=scored["target_date"].to_numpy(),
            scores=scored["error"].abs().to_numpy(),
        )

    def in_latest_window(self, known: np.ndarray, window: int) -> np.ndarray:
        known_origins = np.unique(self.origin_dates[known])
        return self.scores[known & np.isin(self.origin_dates, known_origins[-window:])]

    def miss_rates(
        self, known: np.ndarray, issued_intervals: list[_IssuedInterval]
    ) -> list[float]:
        return [
            float((self.scores[outcome_known] > interval.half_width).mean())
            for interval in issued_intervals
            if (outcome_known := known & (self.origin_dates == interval.origin)).any()
        ]


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
    scored_errors = _ScoredErrors.from_frame(errors)
    issued_intervals: list[_IssuedInterval] = []
    for origin in origins:
        as_of = origin.to_datetime64()
        known = scored_errors.target_dates <= as_of
        miss_rates = scored_errors.miss_rates(known, issued_intervals)
        miscoverage = target_miscoverage + step * sum(
            target_miscoverage - miss for miss in miss_rates
        )
        calibration = scored_errors.in_latest_window(known, window)
        half_width = _conformal_quantile(calibration, 1 - miscoverage)
        issued_intervals.append(_IssuedInterval(origin=as_of, half_width=half_width))
    return pd.Series(
        [interval.half_width for interval in issued_intervals],
        index=pd.DatetimeIndex(list(origins)),
    )


def jackknife_half_widths(
    errors: pd.DataFrame,
    origins: Sequence[pd.Timestamp],
    *,
    level: float,
    window: int,
    step: float,
) -> pd.Series:
    """Half-width of each held-out company's interval from the other companies' errors.

    ``errors`` holds ``ticker, origin_date, target_date, error``: each company's
    error from the model fit without it, all at one history length H. A
    company's interval is calibrated as in ``rolling_half_widths`` on every
    other company's errors, never its own: the jackknife of Barber et al.
    (2021), not the jackknife+, whose other models would have trained on the
    company being scored (spec R8).

    Returns:
        The half-width per company and origin, indexed by ticker and origin date.
    """
    half_widths: pd.Series = pd.concat(
        {
            ticker: rolling_half_widths(
                errors[errors["ticker"].ne(ticker)],
                origins,
                level=level,
                window=window,
                step=step,
            )
            for ticker in sorted(errors["ticker"].unique())
        },
        names=["ticker", "origin_date"],
    )
    return half_widths

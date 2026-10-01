from collections.abc import Mapping, Sequence
from typing import Final

import pandas as pd

from app.services.diagnostics.models import SegmentSettings

_BY_SEGMENT_COLUMNS: Final = (
    "segment",
    "value",
    "companies",
    "observations",
    "median",
    "lower_quartile",
    "upper_quartile",
)


def _covid_period(panel: pd.DataFrame) -> pd.Series:
    covid = panel["covid"].astype(bool)
    if not covid.any():
        return pd.Series("before_covid", index=panel.index)
    first_covid = panel.loc[covid, "date"].min()
    period = pd.Series("after_covid", index=panel.index)
    period[panel["date"] < first_covid] = "before_covid"
    period[covid] = "covid"
    return period


def segment_frame(
    target_frame: pd.DataFrame,
    panels: Mapping[str, pd.DataFrame],
    regimes: pd.Series,
) -> pd.DataFrame:
    """Label each target row with its sector, seasonality regime and covid period.

    The period follows NB00's ``covid`` flag: before it, the flagged quarters,
    and after it (spec D7).

    Returns:
        The target frame with ``sector``, ``regime``, ``period`` and the
        ``covid`` and ``structural_break`` flags of the origin quarter.
    """
    labels = pd.concat(
        [
            panel[["ticker", "date", "sector", "covid", "structural_break"]].assign(
                period=_covid_period(panel)
            )
            for panel in panels.values()
        ],
        ignore_index=True,
    )
    return target_frame.merge(labels, on=["ticker", "date"], how="left").assign(
        regime=lambda frame: frame["ticker"].map(regimes)
    )


def seasonal_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Average the target by the calendar quarter it forecasts, per regime.

    Returns:
        ``regime, target_quarter, mean_y``.
    """
    quarters_in_year = 4
    target_quarter = (
        frame["date"].dt.quarter - 1 + frame["horizon"]
    ) % quarters_in_year + 1
    return (
        frame
        .assign(target_quarter=target_quarter)
        .groupby(["regime", "target_quarter"], as_index=False)
        .agg(mean_y=("y", "mean"))
    )


def median_timeline(frame: pd.DataFrame) -> pd.DataFrame:
    """Take the panel-median target per quarter, marking covid and break quarters.

    Returns:
        ``date, median_y, covid, breaks`` (companies with a break that quarter).
    """
    return (
        frame
        .groupby("date", as_index=False)
        .agg(
            median_y=("y", "median"),
            covid=("covid", "any"),
            breaks=("structural_break", "sum"),
        )
        .astype({"breaks": int})
    )


class SegmentProfiler:
    """Compare the target's centre and spread across segments.

    Usage::

        profiler = container.segment_profiler()
        table = profiler.by_segment(frame, ["sector", "regime", "period"])
    """

    def __init__(self, settings: SegmentSettings) -> None:
        self._settings = settings

    def _profile(self, frame: pd.DataFrame, segment: str) -> pd.DataFrame:
        lower, upper = self._settings.spread_quantiles
        grouped = frame.groupby(segment)
        return pd.DataFrame({
            "segment": segment,
            "value": grouped["y"].median().index.astype(str),
            "companies": grouped["ticker"].nunique().to_numpy(),
            "observations": grouped["y"].count().to_numpy(),
            "median": grouped["y"].median().to_numpy(),
            "lower_quartile": grouped["y"].quantile(lower).to_numpy(),
            "upper_quartile": grouped["y"].quantile(upper).to_numpy(),
        })

    def by_segment(self, frame: pd.DataFrame, segments: Sequence[str]) -> pd.DataFrame:
        """Tabulate the target's median and spread per value of each segment.

        Returns:
            One row per segment value, in the order the segments are given.
        """
        return pd.concat(
            [self._profile(frame, segment) for segment in segments], ignore_index=True
        )[list(_BY_SEGMENT_COLUMNS)]

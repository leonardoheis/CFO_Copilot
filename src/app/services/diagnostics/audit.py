from collections.abc import Mapping, Sequence
from typing import Final, NamedTuple

import numpy as np
import pandas as pd

from app.services.diagnostics.models import OutlierSettings
from app.services.features.transforms import TargetVariable, trailing_revenue

REGISTER_COLUMNS: Final = (
    "ticker",
    "date",
    "column",
    "value",
    "change",
    "robust_z",
    "hampel_z",
    "direction",
)
SCORE_COLUMNS: Final = ("date", "value", "change", "robust_z", "hampel_z")
TARGET_EXTREME_COLUMNS: Final = (
    "ticker",
    "date",
    "arm",
    "horizon",
    "y",
    "robust_z",
    "direction",
)
_TARGET_GROUP: Final = ["ticker", "arm", "horizon"]
# For a normal distribution the MAD is 0.6745 and the mean absolute deviation
# 0.7979 standard deviations; dividing by them makes robust z read like z.
_MAD_TO_SIGMA: Final = 0.6745
_MEAN_AD_TO_SIGMA: Final = 0.7979
_DEGENERATE_SCALE: Final = 1e-9


def _robust_sigma(deviations: pd.Series, centre: float) -> float:
    # When over half the changes are identical the MAD collapses to ~0;
    # Iglewicz & Hoaglin fall back to the mean absolute deviation there.
    tolerance = _DEGENERATE_SCALE * max(1.0, abs(centre))
    mad = float(deviations.median())
    if mad > tolerance:
        return mad / _MAD_TO_SIGMA
    return float(deviations.mean()) / _MEAN_AD_TO_SIGMA


class _CompanySeries(NamedTuple):
    ticker: str
    panel: pd.DataFrame
    column: str


class _Scores(NamedTuple):
    change: pd.Series
    robust_z: pd.Series
    hampel_z: pd.Series


def _entries(
    series: _CompanySeries, mask: pd.Series, scores: _Scores, direction: str
) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": series.ticker,
        "date": series.panel.loc[mask, "date"],
        "column": series.column,
        "value": series.panel.loc[mask, series.column],
        "change": scores.change[mask],
        "robust_z": scores.robust_z[mask],
        "hampel_z": scores.hampel_z[mask],
        "direction": direction,
    })


def _empty_register() -> pd.DataFrame:
    return pd.DataFrame(columns=list(REGISTER_COLUMNS))


class OutlierRegister:
    """Register company-quarters whose change or sign is out of line.

    Each change is made relative to size, then scored by its robust z (distance
    from the company's median change in MAD units); above the threshold it is
    registered. A Hampel z against a rolling window shows whether the quarter
    is also unusual for its period. The register records; it changes no value.

    Usage::

        register = OutlierRegister(settings=OutlierSettings())
        table = register.register(panels, COMPANY_VALUE_COLUMNS)
    """

    def __init__(self, settings: OutlierSettings) -> None:
        self._settings = settings

    @property
    def z_threshold(self) -> float:
        return self._settings.z_threshold

    def scores_for(self, panel: pd.DataFrame, column: str) -> pd.DataFrame:
        """Score every quarter of one company's column, flagged or not.

        Returns:
            ``date, value, change, robust_z, hampel_z`` per quarter; empty when
            the series is too short or too flat to score.
        """
        scores = self._scores(_CompanySeries(ticker="", panel=panel, column=column))
        if scores is None:
            return pd.DataFrame(columns=list(SCORE_COLUMNS))
        return pd.DataFrame({
            "date": panel["date"],
            "value": panel[column],
            "change": scores.change,
            "robust_z": scores.robust_z,
            "hampel_z": scores.hampel_z,
        })

    def _relative_change(self, series: _CompanySeries) -> pd.Series:
        values = series.panel[series.column]
        if series.column in self._settings.ratio_columns:
            change = values.diff()
        elif series.column in self._settings.positive_columns:
            change = values.pct_change(fill_method=None)
        else:
            revenue = series.panel[TargetVariable.REVENUE]
            change = values.diff() / trailing_revenue(revenue)
        return change.replace([np.inf, -np.inf], np.nan)

    def _scores(self, series: _CompanySeries) -> _Scores | None:
        change = self._relative_change(series)
        observed = change.dropna()
        if len(observed) < self._settings.min_changes:
            return None
        median = float(observed.median())
        sigma = _robust_sigma((observed - median).abs(), median)
        # Changes that are all equal have no spread to judge a deviation by.
        if sigma <= _DEGENERATE_SCALE * max(1.0, abs(median)):
            return None
        window = self._settings.hampel_window
        local_median = change.rolling(window, center=True, min_periods=window // 2)
        local_centre = local_median.median()
        local_sigma = (
            (change - local_centre)
            .abs()
            .rolling(window, center=True, min_periods=window // 2)
            .median()
            .div(_MAD_TO_SIGMA)
            .clip(lower=self._settings.hampel_mad_floor * sigma)
        )
        return _Scores(
            change=change,
            robust_z=(change - median) / sigma,
            hampel_z=(change - local_centre) / local_sigma,
        )

    def _findings(self, series: _CompanySeries) -> list[pd.DataFrame]:
        scores = self._scores(series)
        if scores is None:
            return []
        threshold = self._settings.z_threshold
        findings = [
            _entries(series, scores.robust_z > threshold, scores, "up"),
            _entries(series, scores.robust_z < -threshold, scores, "down"),
        ]
        if series.column in self._settings.positive_columns:
            non_positive = series.panel[series.column] <= 0
            findings.append(_entries(series, non_positive, scores, "non_positive"))
        return [finding for finding in findings if not finding.empty]

    def _target_extremes(self, group: pd.DataFrame) -> pd.DataFrame:
        observed = group["y"].dropna()
        if len(observed) < self._settings.min_changes:
            return pd.DataFrame(columns=list(TARGET_EXTREME_COLUMNS))
        median = float(observed.median())
        sigma = _robust_sigma((observed - median).abs(), median)
        if sigma <= _DEGENERATE_SCALE * max(1.0, abs(median)):
            return pd.DataFrame(columns=list(TARGET_EXTREME_COLUMNS))
        robust_z = (group["y"] - median) / sigma
        extreme = robust_z.abs() > self._settings.z_threshold
        return group.loc[extreme].assign(
            robust_z=robust_z[extreme],
            direction=np.where(robust_z[extreme] > 0, "up", "down"),
        )[list(TARGET_EXTREME_COLUMNS)]

    def register_target(self, target_frame: pd.DataFrame) -> pd.DataFrame:
        """Register target values far from their company's usual target.

        The target is already a change, so it is scored as it is, per company,
        arm and horizon, by the same robust z as ``register``.

        Returns:
            One row per extreme target value, the most extreme first.
        """
        extremes = [
            found
            for _, group in target_frame.groupby(_TARGET_GROUP, sort=False)
            if not (found := self._target_extremes(group)).empty
        ]
        if not extremes:
            return pd.DataFrame(columns=list(TARGET_EXTREME_COLUMNS))
        return (
            pd
            .concat(extremes, ignore_index=True)
            .sort_values("robust_z", key=abs, ascending=False)
            .reset_index(drop=True)
        )

    def register(
        self, panels: Mapping[str, pd.DataFrame], columns: Sequence[str]
    ) -> pd.DataFrame:
        """Register every out-of-line company-quarter in the given columns.

        Returns:
            One row per finding, the most extreme robust z first.
        """
        findings = [
            finding
            for ticker, panel in panels.items()
            for column in columns
            if column not in self._settings.derived_columns
            for finding in self._findings(
                _CompanySeries(ticker=ticker, panel=panel, column=column)
            )
        ]
        if not findings:
            return _empty_register()
        return (
            pd
            .concat(findings, ignore_index=True)
            .sort_values("robust_z", key=abs, ascending=False, na_position="last")
            .reset_index(drop=True)
        )


class DataDictionary:
    """Describe each column by what can be computed from the data.

    Usage::

        dictionary = DataDictionary(settings=OutlierSettings())
        table = dictionary.describe(pooled, COMPANY_VALUE_COLUMNS, register=register)
    """

    def __init__(self, settings: OutlierSettings) -> None:
        self._settings = settings

    def _invalid_sign(self, values: pd.Series, column: str) -> int:
        if column not in self._settings.positive_columns:
            return 0
        return int((values <= 0).sum())

    def describe(
        self, pooled: pd.DataFrame, columns: Sequence[str], *, register: pd.DataFrame
    ) -> pd.DataFrame:
        """Tabulate type, completeness, range, sign and outlier count per column.

        Returns:
            One row per column in the given order.
        """
        return pd.DataFrame([
            {
                "column": column,
                "dtype": str(pooled[column].dtype),
                "missing_share": float(pooled[column].isna().mean()),
                "unique": int(pooled[column].nunique()),
                "min": pooled[column].min(),
                "max": pooled[column].max(),
                "invalid_sign": self._invalid_sign(pooled[column], column),
                "register_count": int((register["column"] == column).sum()),
            }
            for column in columns
        ])

from enum import StrEnum
from typing import Final

import pandas as pd
from pydantic import BaseModel, ConfigDict

from app.data.schema import MACRO_COLUMNS
from app.domain import TargetVariable
from app.services.features.exceptions import (
    MissingFlagsError,
    MissingRegimeError,
    MixedTickerPanelError,
)
from app.services.features.transforms import SEASONAL_LAG, target_growth

GROWTH_LAGS: Final = (1, 2, 3, 4, 5, 8)
ROLLING_WINDOWS: Final = (4, 8)
MARGIN_COLUMNS: Final = ("gross_margin", "operating_margin", "net_margin")
FLAG_COLUMNS: Final = ("covid", "structural_break")
_LAG_SHIFTS: Final = {f"growth_yoy_lag{lag}": lag - 1 for lag in GROWTH_LAGS}
_MEAN_WINDOWS: Final = {f"growth_yoy_mean_{w}q": w for w in ROLLING_WINDOWS}
_STD_WINDOWS: Final = {f"growth_yoy_std_{w}q": w for w in ROLLING_WINDOWS}
_MOMENTUM_COLUMN: Final = "growth_yoy_momentum"
_MOMENTUM_SHIFT: Final = 1
STATIC_COLUMNS: Final = ("sector", "seasonality_regime")
# Each growth value spans SEASONAL_LAG + 1 quarters, including the origin.
QUARTERS_READ_BY_FEATURE: Final = {
    **{column: SEASONAL_LAG + shift + 1 for column, shift in _LAG_SHIFTS.items()},
    **{
        column: SEASONAL_LAG + window
        for column, window in (_MEAN_WINDOWS | _STD_WINDOWS).items()
    },
    _MOMENTUM_COLUMN: SEASONAL_LAG + _MOMENTUM_SHIFT + 1,
}


class FeatureGroup(StrEnum):
    LAGS = "L"
    ROLLING = "R"
    MARGINS = "M"
    MACRO = "X"
    MACRO_DERIVED = "XD"
    CALENDAR = "C"
    STATIC = "S"
    FLAGS = "F"


class FeatureSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_variable: TargetVariable = TargetVariable.REVENUE
    groups: frozenset[FeatureGroup] = frozenset(FeatureGroup)


def feature_groups_by_column() -> dict[str, FeatureGroup]:
    """Map every column the builder can emit to its feature group.

    Returns:
        Feature column name to group, for every group.
    """
    columns_by_group: dict[FeatureGroup, tuple[str, ...]] = {
        FeatureGroup.LAGS: tuple(_LAG_SHIFTS),
        FeatureGroup.ROLLING: (*_MEAN_WINDOWS, *_STD_WINDOWS, _MOMENTUM_COLUMN),
        FeatureGroup.MARGINS: MARGIN_COLUMNS,
        FeatureGroup.MACRO: MACRO_COLUMNS,
        FeatureGroup.MACRO_DERIVED: ("real_rate",),
        FeatureGroup.CALENDAR: ("target_quarter",),
        FeatureGroup.STATIC: STATIC_COLUMNS,
        FeatureGroup.FLAGS: FLAG_COLUMNS,
    }
    return {
        column: group
        for group, columns in columns_by_group.items()
        for column in columns
    }


def _lag_features(growth: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        column: growth.shift(shift) for column, shift in _LAG_SHIFTS.items()
    })


def _rolling_features(growth: pd.Series) -> pd.DataFrame:
    means = {
        column: growth.rolling(window).mean()
        for column, window in _MEAN_WINDOWS.items()
    }
    stds = {
        column: growth.rolling(window).std() for column, window in _STD_WINDOWS.items()
    }
    return pd.DataFrame({
        **means,
        **stds,
        _MOMENTUM_COLUMN: growth - growth.shift(_MOMENTUM_SHIFT),
    })


def _static_features(panel: pd.DataFrame, regimes: pd.Series) -> pd.DataFrame:
    ticker = panel["ticker"].iloc[0]
    if ticker not in regimes.index:
        raise MissingRegimeError(ticker=str(ticker))
    return pd.DataFrame({
        "sector": panel["sector"],
        "seasonality_regime": regimes[ticker],
    })


def _flag_features(panel: pd.DataFrame) -> pd.DataFrame:
    absent = tuple(column for column in FLAG_COLUMNS if column not in panel.columns)
    if absent:
        raise MissingFlagsError(columns=absent)
    return panel[list(FLAG_COLUMNS)]


def _require_one_company(panel: pd.DataFrame) -> None:
    tickers = panel["ticker"].to_numpy()
    if tickers.size == 0 or (tickers != tickers[0]).any():
        raise MixedTickerPanelError(
            tickers=tuple(sorted({str(ticker) for ticker in tickers}))
        )


class FeatureBuilder:
    """Build one company's features for a fixed feature spec.

    Usage::

        builder = FeatureBuilder(spec=FeatureSpec())
        features = builder.build(panel, horizon=2, regimes=regimes)
    """

    def __init__(self, spec: FeatureSpec) -> None:
        self._spec = spec

    @property
    def target_variable(self) -> TargetVariable:
        return self._spec.target_variable

    def includes(self, group: FeatureGroup) -> bool:
        return group in self._spec.groups

    def build(
        self, panel: pd.DataFrame, *, horizon: int, regimes: pd.Series
    ) -> pd.DataFrame:
        """Build features that use only quarters up to each row's origin.

        Returns:
            One row per origin quarter, indexed like ``panel``.
        """
        _require_one_company(panel)
        growth = target_growth(
            self._spec.target_variable,
            panel[self._spec.target_variable],
            panel[TargetVariable.REVENUE],
        )
        target_dates = panel["date"] + pd.offsets.QuarterEnd(horizon)
        groups = self._spec.groups
        parts = [
            pd.DataFrame({
                "ticker": panel["ticker"],
                "origin_date": panel["date"],
                "target_date": target_dates,
            })
        ]
        if FeatureGroup.LAGS in groups:
            parts.append(_lag_features(growth))
        if FeatureGroup.ROLLING in groups:
            parts.append(_rolling_features(growth))
        if FeatureGroup.MARGINS in groups:
            parts.append(panel[list(MARGIN_COLUMNS)])
        if FeatureGroup.MACRO in groups:
            parts.append(panel[list(MACRO_COLUMNS)])
        if FeatureGroup.MACRO_DERIVED in groups:
            parts.append(
                pd.DataFrame({"real_rate": panel["fed_funds"] - panel["cpi_yoy"]})
            )
        if FeatureGroup.CALENDAR in groups:
            parts.append(pd.DataFrame({"target_quarter": target_dates.dt.quarter}))
        if FeatureGroup.STATIC in groups:
            parts.append(_static_features(panel, regimes))
        if FeatureGroup.FLAGS in groups:
            parts.append(_flag_features(panel))
        return pd.concat(parts, axis=1)

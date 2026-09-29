from enum import StrEnum
from typing import Final

import pandas as pd
from pydantic import BaseModel, ConfigDict

from app.data.schema import MACRO_COLUMNS
from app.services.features.exceptions import (
    MissingFlagsError,
    MissingRegimeError,
    MixedTickerPanelError,
)
from app.services.features.transforms import yoy_log_growth

GROWTH_LAGS: Final = (1, 2, 3, 4, 5, 8)
ROLLING_WINDOWS: Final = (4, 8)
MARGIN_COLUMNS: Final = ("gross_margin", "operating_margin", "net_margin")
FLAG_COLUMNS: Final = ("covid", "structural_break")


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

    target_variable: str = "revenue_usd_m"
    groups: frozenset[FeatureGroup] = frozenset(FeatureGroup)


def _lag_features(growth: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        f"growth_yoy_lag{k}": growth.shift(k - 1) for k in GROWTH_LAGS
    })


def _rolling_features(growth: pd.Series) -> pd.DataFrame:
    means = {f"growth_yoy_mean_{w}q": growth.rolling(w).mean() for w in ROLLING_WINDOWS}
    stds = {f"growth_yoy_std_{w}q": growth.rolling(w).std() for w in ROLLING_WINDOWS}
    return pd.DataFrame({
        **means,
        **stds,
        "growth_yoy_momentum": growth - growth.shift(1),
    })


def _static_features(panel: pd.DataFrame, regimes: pd.Series | None) -> pd.DataFrame:
    ticker = panel["ticker"].iloc[0]
    if regimes is None or ticker not in regimes.index:
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
    def target_variable(self) -> str:
        return self._spec.target_variable

    def includes(self, group: FeatureGroup) -> bool:
        return group in self._spec.groups

    def build(
        self, panel: pd.DataFrame, *, horizon: int, regimes: pd.Series | None = None
    ) -> pd.DataFrame:
        """Build features that use only quarters up to each row's origin.

        Returns:
            One row per origin quarter, indexed like ``panel``.
        """
        _require_one_company(panel)
        growth = yoy_log_growth(panel[self._spec.target_variable])
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

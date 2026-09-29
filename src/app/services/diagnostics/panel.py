from collections.abc import Mapping, Sequence
from typing import Final, Protocol, cast

import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.cluster import KMeans

from app.services.diagnostics.exceptions import TooFewCompaniesError
from app.services.diagnostics.models import RegimeSettings
from app.services.features.transforms import yoy_log_growth

_CLUSTERING_COLUMNS: Final = ["seasonal_strength", "trend_strength"]


class _Clusterer(Protocol):
    """The slice of sklearn's untyped KMeans API this module relies on."""

    def fit_predict(self, X: pd.DataFrame) -> npt.NDArray[np.int32]: ...


class SeasonalityRegimeClusterer:
    """Group companies into regimes ordered from least to most seasonal.

    Usage::

        clusterer = SeasonalityRegimeClusterer(settings=RegimeSettings())
        regimes = clusterer.assign(diagnostics, variable="revenue_usd_m")
    """

    def __init__(self, settings: RegimeSettings) -> None:
        self._settings = settings

    def assign(self, diagnostics: pd.DataFrame, *, variable: str) -> pd.Series:
        """Cluster fully diagnosed companies by seasonal and trend strength.

        Returns:
            Regime id per ticker; 0 is the least seasonal cluster.

        Raises:
            TooFewCompaniesError: Fewer fully diagnosed companies than regimes.
        """
        fully_diagnosed = diagnostics.loc[
            (diagnostics["variable"] == variable) & (diagnostics["status"] == "ok")
        ].set_index("ticker")
        n_regimes = self._settings.n_regimes
        if len(fully_diagnosed) < n_regimes:
            raise TooFewCompaniesError(
                companies=len(fully_diagnosed), regimes=n_regimes
            )
        clusterer = cast(
            "_Clusterer",
            # pyright infers n_init: str from sklearn's "auto" default; it takes an int.
            KMeans(n_clusters=n_regimes, random_state=self._settings.seed, n_init=10),  # pyright: ignore[reportArgumentType]
        )
        raw = pd.Series(
            clusterer.fit_predict(fully_diagnosed[_CLUSTERING_COLUMNS]),
            index=fully_diagnosed.index,
        )
        rank_by_seasonality = (
            fully_diagnosed["seasonal_strength"]
            .groupby(raw)
            .mean()
            .rank()
            .sub(1)
            .astype(int)
        )
        return raw.map(rank_by_seasonality).rename("seasonality_regime")


class MacroCorrelator:
    """Correlate each company's YoY growth with a fixed set of macro columns.

    Usage::

        correlator = MacroCorrelator(macro_columns=MACRO_COLUMNS)
        table = correlator.correlate(panels, variable="revenue_usd_m")
    """

    def __init__(self, macro_columns: Sequence[str]) -> None:
        self._macro_columns = tuple(macro_columns)

    def correlate(
        self, panels: Mapping[str, pd.DataFrame], *, variable: str
    ) -> pd.DataFrame:
        """Correlate each company's YoY log growth with every macro column.

        Returns:
            One row per ticker: a correlation per macro column plus ``sector``.
        """
        rows = {
            ticker: {
                **{
                    column: yoy_log_growth(panel[variable]).corr(panel[column])
                    for column in self._macro_columns
                },
                "sector": panel["sector"].iloc[0],
            }
            for ticker, panel in panels.items()
        }
        return pd.DataFrame.from_dict(rows, orient="index")

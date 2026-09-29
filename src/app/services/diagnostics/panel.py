from collections.abc import Mapping, Sequence
from typing import Final, Protocol, cast

import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.cluster import KMeans

from app.services.diagnostics.exceptions import TooFewCompaniesError
from app.services.diagnostics.models import (
    CompanyMacroSensitivity,
    MacroCorrelation,
    RegimeSettings,
)
from app.services.features.transforms import yoy_log_growth

_CLUSTERING_COLUMNS: Final = ["seasonal_strength", "trend_strength"]


class _Clusterer(Protocol):
    """The slice of sklearn's untyped KMeans API this module relies on."""

    def fit_predict(self, X: pd.DataFrame) -> npt.NDArray[np.int32]: ...


class _KMeansFactory(Protocol):
    """The KMeans constructor arguments this module passes."""

    def __call__(
        self, *, n_clusters: int, random_state: int, n_init: int
    ) -> _Clusterer: ...


# sklearn ships no stubs, and pyright would otherwise infer n_init: str from its
# "auto" default and reject an int; this states the real signature instead.
_kmeans = cast("_KMeansFactory", KMeans)


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
        n_regimes, seed = self._settings.n_regimes, self._settings.seed
        if len(fully_diagnosed) < n_regimes:
            raise TooFewCompaniesError(
                companies=len(fully_diagnosed), regimes=n_regimes
            )
        clusterer = _kmeans(
            n_clusters=n_regimes, random_state=seed, n_init=self._settings.n_init
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

    def _sensitivity(
        self, ticker: str, panel: pd.DataFrame, variable: str
    ) -> CompanyMacroSensitivity:
        """Correlate one company's YoY log growth with each macro column.

        Returns:
            The company's sector and one correlation per macro column.
        """
        growth = yoy_log_growth(panel[variable])
        return CompanyMacroSensitivity(
            ticker=ticker,
            sector=str(panel["sector"].iloc[0]),
            correlations=tuple(
                MacroCorrelation(
                    macro_column=column,
                    correlation=float(growth.corr(panel[column])),
                )
                for column in self._macro_columns
            ),
        )

    def correlate(
        self, panels: Mapping[str, pd.DataFrame], *, variable: str
    ) -> pd.DataFrame:
        """Correlate each company's YoY log growth with every macro column.

        Returns:
            One row per ticker: a correlation per macro column plus ``sector``.
        """
        sensitivities = [
            self._sensitivity(ticker, panel, variable)
            for ticker, panel in panels.items()
        ]
        return pd.DataFrame(
            [sensitivity.as_table_row() for sensitivity in sensitivities],
            index=[sensitivity.ticker for sensitivity in sensitivities],
        )

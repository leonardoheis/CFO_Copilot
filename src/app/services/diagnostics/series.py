import warnings
from typing import Literal, Protocol, cast

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import boxcox_normmax
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller, kpss

from app.services.diagnostics.models import DiagnosticsSettings, SeriesDiagnostics
from app.services.features.transforms import log_level

type _FloatArray = npt.NDArray[np.float64]


class _KpssResult(Protocol):
    """statsmodels ``KPSSResult``; H0 is stationarity."""

    @property
    def statistic(self) -> float: ...
    @property
    def pvalue(self) -> float: ...
    @property
    def lags(self) -> int: ...
    @property
    def critical_values(self) -> dict[str, float]: ...


class _KpssTest(Protocol):
    """statsmodels ``kpss`` returning its named result."""

    def __call__(
        self,
        x: pd.Series,
        *,
        regression: Literal["c", "ct"],
        nlags: Literal["auto", "legacy"],
        result_object: Literal[True],
    ) -> _KpssResult: ...


class _AdfResult(Protocol):
    """statsmodels ``ADFullerResult``; H0 is a unit root."""

    @property
    def statistic(self) -> float: ...
    @property
    def pvalue(self) -> float: ...
    @property
    def lags(self) -> int: ...
    @property
    def nobs(self) -> int: ...
    @property
    def critical_values(self) -> dict[str, float]: ...


class _AdfTest(Protocol):
    """statsmodels ``adfuller`` returning its named result."""

    def __call__(self, x: pd.Series, *, result_object: Literal[True]) -> _AdfResult: ...


class _StlFit(Protocol):
    """The decomposition components an STL fit exposes."""

    @property
    def seasonal(self) -> _FloatArray: ...
    @property
    def trend(self) -> _FloatArray: ...
    @property
    def resid(self) -> _FloatArray: ...


class _Stl(Protocol):
    def fit(self) -> _StlFit: ...


class _StlFactory(Protocol):
    """statsmodels ``STL`` constructor arguments this module passes."""

    def __call__(self, endog: _FloatArray, *, period: int, robust: bool) -> _Stl: ...


class _LjungBoxTest(Protocol):
    """statsmodels ``acorr_ljungbox``: a frame with an ``lb_pvalue`` column."""

    def __call__(
        self, x: pd.Series, *, lags: list[int], return_df: Literal[True]
    ) -> pd.DataFrame: ...


# statsmodels ships no stubs, so each call is typed once here with the
# signature and result shape this module relies on.
_kpss = cast("_KpssTest", kpss)
_adfuller = cast("_AdfTest", adfuller)
_stl = cast("_StlFactory", STL)
_acorr_ljungbox = cast("_LjungBoxTest", acorr_ljungbox)


def observed_since_last_gap(series: pd.Series) -> pd.Series:
    """Keep the run after the last missing value so no gap is spliced shut.

    Returns:
        The trailing run of observed values, possibly empty.
    """
    gap_positions = np.flatnonzero(series.isna().to_numpy())
    start = 0 if gap_positions.size == 0 else int(gap_positions[-1]) + 1
    return series.iloc[start:]


def _is_constant(series: pd.Series) -> bool:
    values = series.to_numpy()
    return bool((values == values[0]).all())


def _log_defined(observed: pd.Series) -> bool:
    return bool(len(observed) and (observed > 0).all())


def _strength(component: _FloatArray, remainder: _FloatArray) -> float:
    return float(max(0.0, 1.0 - np.var(remainder) / np.var(component + remainder)))


def _ljung_box_p(series: pd.Series, order: int, lag: int) -> float:
    differenced = series.diff(order).dropna() if order else series
    result = _acorr_ljungbox(differenced, lags=[lag], return_df=True)
    return float(result["lb_pvalue"].iloc[0])


def _unanalysed(
    ticker: str,
    variable: str,
    observed: pd.Series,
    status: Literal["insufficient_data", "constant"],
) -> SeriesDiagnostics:
    return SeriesDiagnostics(
        ticker=ticker,
        variable=variable,
        n_obs=len(observed),
        status=status,
        log_defined=_log_defined(observed),
    )


class SeriesDiagnostician:
    """Diagnose one company's variable: stationarity, seasonality, noise.

    Usage::

        diagnostician = SeriesDiagnostician(settings=DiagnosticsSettings())
        record = diagnostician.diagnose("AMZN", "revenue_usd_m", panel["revenue_usd_m"])
    """

    def __init__(self, settings: DiagnosticsSettings) -> None:
        self._settings = settings

    def _looks_stationary(self, series: pd.Series) -> bool:
        # kpss clips its p-value at the table bounds and warns; the direction of the
        # decision is still valid, so the warning carries no information here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InterpolationWarning)
            kpss = _kpss(series, regression="c", nlags="auto", result_object=True)
        adf = _adfuller(series, result_object=True)
        significance = self._settings.significance
        return bool(kpss.pvalue > significance > adf.pvalue)

    def differencing_order(self, series: pd.Series) -> int:
        """Find the smallest d at which ADF and KPSS both call the series stationary.

        Returns:
            The order, capped at the configured maximum.
        """
        current = series.dropna()
        for order in range(self._settings.max_differencing_order + 1):
            if self._looks_stationary(current):
                return order
            current = current.diff().dropna()
        return self._settings.max_differencing_order

    def seasonal_and_trend_strength(self, series: pd.Series) -> tuple[float, float]:
        """Measure STL seasonal and trend strength, each between 0 and 1.

        Returns:
            ``(seasonal_strength, trend_strength)``.
        """
        fit = _stl(
            series.to_numpy(dtype=np.float64),
            period=self._settings.seasonal_period,
            robust=True,
        ).fit()
        return (
            _strength(fit.seasonal, fit.resid),
            _strength(fit.trend, fit.resid),
        )

    def diagnose(
        self, ticker: str, variable: str, series: pd.Series
    ) -> SeriesDiagnostics:
        """Diagnose one series; a short, gapped or constant one yields a record.

        Returns:
            The record for this company and variable.
        """
        observed = observed_since_last_gap(series)
        if len(observed) < self._settings.min_observations:
            return _unanalysed(ticker, variable, observed, "insufficient_data")
        # ADF and KPSS divide by the variance, which a constant run does not have.
        if _is_constant(observed):
            return _unanalysed(ticker, variable, observed, "constant")
        log_defined = _log_defined(observed)
        d_levels = self.differencing_order(observed)
        seasonal_strength, trend_strength = self.seasonal_and_trend_strength(observed)
        return SeriesDiagnostics(
            ticker=ticker,
            variable=variable,
            n_obs=len(observed),
            status="ok",
            log_defined=log_defined,
            d_levels=d_levels,
            d_log=self.differencing_order(log_level(observed)) if log_defined else None,
            seasonal_strength=seasonal_strength,
            trend_strength=trend_strength,
            ljung_box_p=_ljung_box_p(observed, d_levels, self._settings.ljung_box_lag),
            box_cox_lambda=float(boxcox_normmax(observed, method="mle"))
            if log_defined
            else None,
            coefficient_of_variation=float(observed.std() / abs(observed.mean())),
        )

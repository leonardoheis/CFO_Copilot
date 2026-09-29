# statsmodels ships no type stubs, so every call into it reads as Unknown.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import warnings
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import boxcox_normmax
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller, kpss

from app.services.diagnostics.models import DiagnosticsSettings, SeriesDiagnostics
from app.services.features.transforms import log_level


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


def _strength(component: np.ndarray, remainder: np.ndarray) -> float:
    return float(max(0.0, 1.0 - np.var(remainder) / np.var(component + remainder)))


def _ljung_box_p(series: pd.Series, order: int, lag: int) -> float:
    differenced = series.diff(order).dropna() if order else series
    result = acorr_ljungbox(differenced, lags=[lag], return_df=True)
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
        log_defined=bool(len(observed) and (observed > 0).all()),
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
            kpss_p = kpss(series, regression="c", nlags="auto", result_object=False)[1]
        adf_p = adfuller(series, result_object=False)[1]
        significance = self._settings.significance
        return bool(adf_p < significance and kpss_p > significance)

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
        fit = STL(
            series.to_numpy(), period=self._settings.seasonal_period, robust=True
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
        log_defined = bool((observed > 0).all())
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

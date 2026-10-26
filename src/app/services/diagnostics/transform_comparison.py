"""Compare transforms of each forecast target (master plan O1, NB01b)."""

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Final, Literal, NamedTuple, Self, assert_never

import numpy as np
import numpy.typing as npt
import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator
from scipy.stats import (
    anderson,
    boxcox,
    boxcox_normmax,
    jarque_bera,
    kurtosis,
    skew,
    yeojohnson,
    yeojohnson_normmax,
)

from app.domain import TargetVariable
from app.services.diagnostics.models import DiagnosticsSettings
from app.services.diagnostics.series import (
    observed_since_last_gap,
    stl_remainder,
    with_short_interior_gaps_filled,
)
from app.services.features.transforms import (
    TargetFamily,
    target_family,
    trailing_revenue,
)


class LevelTransform(StrEnum):
    NONE = "none"
    LOG = "log"
    SQRT = "sqrt"
    BOX_COX = "box_cox"
    BOX_COX_SECTOR = "box_cox_sector"
    REVENUE_SCALED = "revenue_scaled"
    ASINH = "asinh"
    YEO_JOHNSON = "yeo_johnson"
    YEO_JOHNSON_SECTOR = "yeo_johnson_sector"


type Normality = Literal["jarque_bera", "anderson_darling"]
type _FloatArray = npt.NDArray[np.float64]


class TransformPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[LevelTransform, ...]
    baseline: LevelTransform

    @model_validator(mode="after")
    def _baseline_is_a_candidate(self) -> Self:
        if self.baseline not in self.candidates:
            msg = f"baseline {self.baseline} is not among {self.candidates}"
            raise ValueError(msg)
        return self


TRANSFORM_POLICIES: Final[Mapping[TargetFamily, TransformPolicy]] = {
    TargetFamily.POSITIVE: TransformPolicy(
        candidates=(
            LevelTransform.NONE,
            LevelTransform.LOG,
            LevelTransform.SQRT,
            LevelTransform.BOX_COX,
            LevelTransform.BOX_COX_SECTOR,
        ),
        baseline=LevelTransform.LOG,
    ),
    TargetFamily.SIGNED: TransformPolicy(
        candidates=(
            LevelTransform.NONE,
            LevelTransform.REVENUE_SCALED,
            LevelTransform.ASINH,
            LevelTransform.YEO_JOHNSON,
            LevelTransform.YEO_JOHNSON_SECTOR,
        ),
        baseline=LevelTransform.REVENUE_SCALED,
    ),
}
# Log and square root are Box-Cox at fixed lambdas, up to a shift and a scale that
# neither criterion sees: Spearman ranks and both normality statistics are
# affine-invariant.
_FIXED_LAMBDA: Final = {LevelTransform.LOG: 0.0, LevelTransform.SQRT: 0.5}
# Spec T6: a transform replaces the baseline only if it wins in most companies.
MAJORITY_SHARE: Final = 0.5


def candidates_for(variable: str) -> tuple[LevelTransform, ...]:
    """Name the transforms compared for a target (spec T1).

    Returns:
        Power transforms for revenue, transforms defined for signed values otherwise.
    """
    return TRANSFORM_POLICIES[target_family(variable)].candidates


def baseline_transform(variable: str) -> LevelTransform:
    """Name the transform the target arms use today (EDA spec F3).

    Returns:
        Log for revenue, the revenue-scaled value for the signed targets.
    """
    return TRANSFORM_POLICIES[target_family(variable)].baseline


def box_cox(series: pd.Series, lam: float) -> pd.Series:
    """Box-Cox transform at ``lam``; ``lam`` = 0 is the log.

    Returns:
        The transformed series, indexed like ``series``.
    """
    values = boxcox(series.to_numpy(dtype=np.float64), lmbda=lam)
    return pd.Series(values, index=series.index)


def _unit_free(series: pd.Series) -> _FloatArray:
    # asinh and Yeo-Johnson are not scale-invariant: millions and units would differ.
    return (series / series.abs().median()).to_numpy(dtype=np.float64)


def _box_cox_lambda(series: pd.Series) -> float:
    return float(boxcox_normmax(series.to_numpy(dtype=np.float64), method="mle"))


def _yeo_johnson_lambda(series: pd.Series) -> float:
    return float(yeojohnson_normmax(_unit_free(series)))


class _FittedFamily(NamedTuple):
    """One fitted transform family: its own lambda, its sector lambda, the estimator."""

    own: LevelTransform
    sector: LevelTransform
    estimator: Callable[[pd.Series], float]


_FITTED: Final = (
    _FittedFamily(
        LevelTransform.BOX_COX, LevelTransform.BOX_COX_SECTOR, _box_cox_lambda
    ),
    _FittedFamily(
        LevelTransform.YEO_JOHNSON,
        LevelTransform.YEO_JOHNSON_SECTOR,
        _yeo_johnson_lambda,
    ),
)


def _transformed(
    transform: LevelTransform, series: pd.Series, revenue: pd.Series, lam: float
) -> pd.Series:
    match transform:
        case LevelTransform.NONE:
            return series
        case (
            LevelTransform.LOG
            | LevelTransform.SQRT
            | LevelTransform.BOX_COX
            | LevelTransform.BOX_COX_SECTOR
        ):
            return box_cox(series, lam)
        case LevelTransform.REVENUE_SCALED:
            return observed_since_last_gap(series / trailing_revenue(revenue))
        case LevelTransform.ASINH:
            return pd.Series(np.arcsinh(_unit_free(series)), index=series.index)
        case LevelTransform.YEO_JOHNSON | LevelTransform.YEO_JOHNSON_SECTOR:
            values = yeojohnson(_unit_free(series), lmbda=lam)
            return pd.Series(values, index=series.index)
        case _:
            assert_never(transform)


class TransformComparer:
    """Score each candidate transform on variance stability and residual normality.

    Usage::

        comparer = container.transform_comparer()
        table = comparer.compare(panels, variable="revenue_usd_m")
        decision = preferred_transform(table, baseline=baseline_transform(variable))
    """

    def __init__(self, settings: DiagnosticsSettings) -> None:
        self._settings = settings

    def _prepared(self, series: pd.Series) -> pd.Series:
        filled, _ = with_short_interior_gaps_filled(
            series, self._settings.max_interpolated_gap
        )
        return observed_since_last_gap(filled)

    def _level_dependence(self, values: pd.Series, revenue: pd.Series) -> float:
        window = self._settings.variance_window
        change_size = values.diff(self._settings.seasonal_period).rolling(window).std()
        size = revenue.reindex(values.index).rolling(window).mean()
        return abs(float(size.corr(change_size, method="spearman")))

    def _scores(self, values: pd.Series, revenue: pd.Series) -> dict[str, float]:
        remainder = stl_remainder(values, self._settings.seasonal_period)
        normality = jarque_bera(remainder)
        # The stubs describe SciPy 1.17, which wants method="interpolate"; the
        # installed 1.16 (ydata-profiling caps it) has no such parameter.
        anderson_darling = anderson(remainder, dist="norm")  # pyright: ignore[reportDeprecated]
        return {
            "level_dependence": self._level_dependence(values, revenue),
            "jarque_bera": float(normality.statistic),
            "jarque_bera_p": float(normality.pvalue),
            "anderson_darling": float(anderson_darling.statistic),
            "skewness": float(skew(remainder)),
            "excess_kurtosis": float(kurtosis(remainder)),
        }

    def _usable(self, series: pd.Series, variable: str) -> bool:
        if len(series) < self._settings.min_observations:
            return False
        return variable != TargetVariable.REVENUE or bool((series > 0).all())

    def _company_rows(
        self,
        ticker: str,
        panel: pd.DataFrame,
        variable: str,
        lambdas: Mapping[LevelTransform, float],
    ) -> list[dict[str, object]]:
        series = self._prepared(panel[variable])
        revenue = panel[TargetVariable.REVENUE]
        candidates = {
            transform: _transformed(
                transform, series, revenue, lambdas.get(transform, np.nan)
            )
            for transform in candidates_for(variable)
        }
        shortest = min(len(values) for values in candidates.values())
        if shortest < self._settings.min_observations:
            return []
        return [
            {
                "variable": variable,
                "ticker": ticker,
                "sector": panel["sector"].iloc[0],
                "transform": transform.value,
                "lambda": lambdas.get(transform, np.nan),
                **self._scores(values, revenue),
            }
            for transform, values in candidates.items()
        ]

    def compare(
        self, panels: Mapping[str, pd.DataFrame], *, variable: str
    ) -> pd.DataFrame:
        """Score every candidate for every company with long enough series.

        Returns:
            One row per (ticker, transform) with the lambda used (NaN where none
            applies) and the scores.
        """
        usable = {
            ticker: panel
            for ticker, panel in panels.items()
            if self._usable(self._prepared(panel[variable]), variable)
        }
        lambdas = _fitted_lambdas(
            {
                ticker: self._prepared(panel[variable])
                for ticker, panel in usable.items()
            },
            pd.Series({
                ticker: panel["sector"].iloc[0] for ticker, panel in usable.items()
            }),
            variable,
        )
        rows = [
            row
            for ticker, panel in usable.items()
            for row in self._company_rows(
                ticker, panel, variable, {**_FIXED_LAMBDA, **lambdas[ticker]}
            )
        ]
        return pd.DataFrame(rows)


def _fitted_lambdas(
    observed: Mapping[str, pd.Series], sectors: pd.Series, variable: str
) -> dict[str, dict[LevelTransform, float]]:
    """Fit each company's lambda and its sector's median (spec T1).

    Returns:
        Per ticker, the lambda of every fitted candidate of ``variable``.
    """
    lambdas = pd.DataFrame(index=sectors.index)
    for family in _FITTED:
        if family.own in candidates_for(variable):
            lambdas[family.own] = [
                family.estimator(observed[ticker]) for ticker in sectors.index
            ]
            lambdas[family.sector] = (
                lambdas[family.own].groupby(sectors).transform("median")
            )
    return {
        str(ticker): {
            LevelTransform(str(name)): float(value) for name, value in row.items()
        }
        for ticker, row in lambdas.iterrows()
    }


def _beats_baseline(
    table: pd.DataFrame, baseline: LevelTransform, normality: Normality
) -> pd.Series:
    scores = table.pivot_table(
        index="ticker", columns="transform", values=["level_dependence", normality]
    )
    dependence, normal = scores["level_dependence"], scores[normality]
    return pd.DataFrame({
        transform: (dependence[transform] < dependence[baseline])
        & (normal[transform] < normal[baseline])
        for transform in dependence.columns
    }).mean()


def summarize_transforms(
    table: pd.DataFrame, *, baseline: LevelTransform, significance: float = 0.05
) -> pd.DataFrame:
    """Summarise one target's comparison per transform (spec T5).

    Returns:
        One row per transform: medians of the scores, the share of companies whose
        remainder passes Jarque-Bera, and the share in which it beats the baseline
        on both criteria, with Jarque-Bera and with Anderson-Darling.
    """
    grouped = table.groupby("transform")
    summary = pd.DataFrame({
        "companies": grouped["ticker"].nunique(),
        "level_dependence": grouped["level_dependence"].median(),
        "jarque_bera": grouped["jarque_bera"].median(),
        "anderson_darling": grouped["anderson_darling"].median(),
        "abs_skewness": grouped["skewness"].apply(lambda values: values.abs().median()),
        "excess_kurtosis": grouped["excess_kurtosis"].median(),
        "normal_share": grouped["jarque_bera_p"].apply(
            lambda values: (values > significance).mean()
        ),
        "beats_baseline_share": _beats_baseline(table, baseline, "jarque_bera"),
        "beats_baseline_share_ad": _beats_baseline(table, baseline, "anderson_darling"),
    })
    summary.index = pd.Index(
        [LevelTransform(name) for name in summary.index], name="transform"
    )
    return summary


def preferred_transform(
    table: pd.DataFrame,
    *,
    baseline: LevelTransform,
    normality: Normality = "jarque_bera",
) -> LevelTransform:
    """Keep the baseline unless a transform beats it in most companies (T6).

    Returns:
        The transform the target should use under the chosen normality test.
    """
    shares = _beats_baseline(table, baseline, normality)
    if shares.max() <= MAJORITY_SHARE:
        return baseline
    return LevelTransform(str(shares.idxmax()))

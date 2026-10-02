from collections.abc import Iterable, Mapping
from typing import Literal, NamedTuple

import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy.stats import kruskal

from app.services.diagnostics.models import DecisionSettings
from app.services.features.transforms import TargetVariable, arms_for, default_arm

DecisionType = Literal[
    "target_transform",
    "exclusions",
    "feature_groups",
    "pooled_or_segmented",
    "forecastable",
]


class DecisionRow(BaseModel):
    """One NB01 decision: what was found, why, and what to do about it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: DecisionType
    finding: str
    evidence: str
    action: str
    applies_to: str


class DecisionInputs(NamedTuple):
    """The EDA results the decision rules read, for one target variable."""

    variable: TargetVariable
    excluded_companies: Mapping[str, str]
    # The outlier register: ``ticker, column, direction`` at least.
    register: pd.DataFrame
    # The feature audit's group summary: ``group, best_mutual_information``.
    feature_groups: pd.DataFrame
    # An exported feature dataset: ``seasonality_regime, y``.
    dataset: pd.DataFrame
    # Per company, the Ljung-Box p-value of the variable's stationary series.
    ljung_box_p: pd.Series


def _comma_separated(items: Iterable[str]) -> str:
    return ", ".join(items)


def _transform_row(inputs: DecisionInputs) -> DecisionRow:
    arms = arms_for(inputs.variable)
    exported = f"export {default_arm(inputs.variable).value}"
    return DecisionRow(
        decision="target_transform",
        finding=f"arms available: {_comma_separated(arm.value for arm in arms)}",
        evidence="F3: log arms only for a variable that is never non-positive",
        action=f"{exported}; compare the arms in NB02" if len(arms) > 1 else exported,
        applies_to=inputs.variable.value,
    )


def _exclusions_row(inputs: DecisionInputs) -> DecisionRow:
    register = inputs.register
    non_positive = register[
        (register["column"] == inputs.variable.value)
        & (register["direction"] == "non_positive")
    ]
    sign_tickers = sorted(set(non_positive["ticker"].astype(str)))
    excluded = sorted(inputs.excluded_companies)
    tickers = excluded + [ticker for ticker in sign_tickers if ticker not in excluded]
    defects = _comma_separated(excluded) or "none"
    return DecisionRow(
        decision="exclusions",
        finding=f"{len(excluded)} excluded by an ingestion spec, "
        f"{len(sign_tickers)} with a non-positive target",
        evidence=f"ingestion defects: {defects}; "
        f"sign rule: {len(non_positive)} register entries",
        action=f"exclude {_comma_separated(tickers)}"
        if tickers
        else "exclude no company",
        applies_to=inputs.variable.value,
    )


class DecisionTableBuilder:
    """Turn the EDA's findings into NB01's decision table, one row per rule.

    Usage::

        builder = container.decision_table_builder()
        table = builder.build(DecisionInputs(variable=..., ...))
    """

    def __init__(self, settings: DecisionSettings) -> None:
        self._settings = settings

    def _feature_groups_row(self, inputs: DecisionInputs) -> DecisionRow:
        groups = inputs.feature_groups
        best = groups["best_mutual_information"]
        # Negated so an all-missing group (NaN score) is a drop candidate too.
        weak = groups.loc[~(best >= self._settings.mutual_information_floor), "group"]
        weak_groups = ", ".join(weak.astype(str))
        scores = ", ".join(
            f"{group} {score:.3f}"
            for group, score in zip(groups["group"], best, strict=True)
        )
        return DecisionRow(
            decision="feature_groups",
            finding=f"{len(weak)} of {len(groups)} groups below the floor",
            evidence=f"best mutual information per group: {scores}",
            action=f"drop candidates for the NB02 ablation: {weak_groups}"
            if weak_groups
            else "keep every group",
            applies_to=inputs.variable.value,
        )

    def _pooling_row(self, inputs: DecisionInputs) -> DecisionRow:
        labelled = inputs.dataset.dropna(subset=["y"])
        samples = [
            regime["y"].to_numpy()
            for _, regime in labelled.groupby("seasonality_regime")
        ]
        p_value = float(kruskal(*samples).pvalue) if len(samples) > 1 else 1.0
        differs = p_value < self._settings.significance
        return DecisionRow(
            decision="pooled_or_segmented",
            finding="the target differs across regimes"
            if differs
            else "no difference across regimes",
            evidence=f"Kruskal-Wallis p = {p_value:.3g} over {len(samples)} regimes",
            action="segmented: keep seasonality_regime; per-regime models "
            "are an NB02 option"
            if differs
            else "pooled: one model for every company",
            applies_to=inputs.variable.value,
        )

    def _forecastable_row(self, inputs: DecisionInputs) -> DecisionRow:
        tested = inputs.ljung_box_p.dropna()
        significant = int((tested < self._settings.significance).sum())
        share = significant / len(tested) if len(tested) else 0.0
        forecastable = share >= self._settings.forecastable_share
        return DecisionRow(
            decision="forecastable",
            finding=f"{significant} of {len(tested)} companies show autocorrelation",
            evidence=f"Ljung-Box p < {self._settings.significance}: {share:.0%} "
            f"(bar {self._settings.forecastable_share:.0%})",
            action="forecastable: carry to NB02"
            if forecastable
            else "not forecastable: report the seasonal-naive baseline only",
            applies_to=inputs.variable.value,
        )

    def build(self, inputs: DecisionInputs) -> tuple[DecisionRow, ...]:
        """Apply each decision rule to the variable's EDA results.

        Returns:
            One row per decision type, in the spec's order.
        """
        return (
            _transform_row(inputs),
            _exclusions_row(inputs),
            self._feature_groups_row(inputs),
            self._pooling_row(inputs),
            self._forecastable_row(inputs),
        )

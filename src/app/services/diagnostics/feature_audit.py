from collections.abc import Mapping
from typing import Final, NamedTuple

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression

from app.services.diagnostics.correlation import CorrelationAnalyzer
from app.services.diagnostics.models import AuditSettings

# A constant feature carries no information and has no rank correlation.
_MIN_DISTINCT_VALUES: Final = 2


class FeatureScore(NamedTuple):
    """How much one feature tells about the target, and how often it is there."""

    feature: str
    group: str
    missing_share: float
    spearman: float
    mutual_information: float


class FeatureAudit(NamedTuple):
    """The feature audit: per feature, per redundant pair, per group."""

    features: pd.DataFrame
    redundant_pairs: pd.DataFrame
    groups: pd.DataFrame


def _is_discrete(values: pd.Series) -> bool:
    return pd.api.types.is_bool_dtype(values) or not pd.api.types.is_numeric_dtype(
        values
    )


def _group_summary(features: pd.DataFrame) -> pd.DataFrame:
    return (
        features
        .groupby("group")
        .agg(
            features=("feature", "count"),
            mean_mutual_information=("mutual_information", "mean"),
            best_mutual_information=("mutual_information", "max"),
            mean_missing_share=("missing_share", "mean"),
        )
        .sort_values("best_mutual_information", ascending=False)
        .reset_index()
    )


class FeatureAuditor:
    """Score each feature against the target over the labelled rows.

    Spearman catches monotone links; mutual information also catches the
    non-monotone ones and scores categorical features.

    Usage::

        auditor = container.feature_auditor()
        audit = auditor.audit(dataset, groups=feature_groups_by_column())
    """

    def __init__(
        self, settings: AuditSettings, correlations: CorrelationAnalyzer
    ) -> None:
        self._settings = settings
        self._correlations = correlations

    def _score(self, labelled: pd.DataFrame, feature: str, group: str) -> FeatureScore:
        present = labelled[[feature, "y"]].dropna()
        missing_share = float(labelled[feature].isna().mean())
        if present[feature].nunique() < _MIN_DISTINCT_VALUES:
            return FeatureScore(feature, group, missing_share, np.nan, np.nan)
        values = present[feature]
        if _is_discrete(values):
            codes = pd.factorize(values)[0].reshape(-1, 1)
            information = mutual_info_regression(
                codes,
                present["y"],
                discrete_features=True,
                random_state=self._settings.seed,
            )
            spearman = np.nan
        else:
            information = mutual_info_regression(
                values.to_frame(), present["y"], random_state=self._settings.seed
            )
            spearman = float(values.corr(present["y"], method="spearman"))
        return FeatureScore(
            feature, group, missing_share, spearman, float(information[0])
        )

    def audit(
        self, dataset: pd.DataFrame, *, groups: Mapping[str, str]
    ) -> FeatureAudit:
        """Score every grouped feature present in ``dataset``.

        Returns:
            Features ranked by mutual information, redundant feature pairs, and
            one summary row per group.
        """
        columns = [column for column in groups if column in dataset.columns]
        labelled = dataset[dataset["y"].notna()]
        features = (
            pd
            .DataFrame([
                self._score(labelled, column, str(groups[column])) for column in columns
            ])
            .sort_values("mutual_information", ascending=False, na_position="last")
            .reset_index(drop=True)
        )
        matrix = self._correlations.matrix(labelled[columns])
        return FeatureAudit(
            features=features,
            redundant_pairs=self._correlations.redundant_pairs(matrix),
            groups=_group_summary(features),
        )

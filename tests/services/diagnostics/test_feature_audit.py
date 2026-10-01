import numpy as np
import pandas as pd
import pytest

from app.services.diagnostics import (
    AuditSettings,
    CorrelationAnalyzer,
    CorrelationSettings,
    FeatureAuditor,
)

ROWS = 400


@pytest.fixture
def auditor() -> FeatureAuditor:
    return FeatureAuditor(
        settings=AuditSettings(),
        correlations=CorrelationAnalyzer(settings=CorrelationSettings()),
    )


@pytest.fixture
def dataset() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    signal = rng.normal(size=ROWS)
    return pd.DataFrame({
        "ticker": "AAA",
        "growth_yoy_lag1": signal,
        "growth_yoy_lag2": signal + 0.01 * rng.normal(size=ROWS),
        "vix": rng.normal(size=ROWS),
        "real_rate": np.nan,
        "sector": rng.choice(["Energy", "Technology"], size=ROWS),
        "y": signal + 0.3 * rng.normal(size=ROWS),
    })


GROUPS = {
    "growth_yoy_lag1": "L",
    "growth_yoy_lag2": "L",
    "vix": "X",
    "real_rate": "XD",
    "sector": "S",
}


def test_an_informative_feature_outranks_noise(
    auditor: FeatureAuditor, dataset: pd.DataFrame
) -> None:
    audit = auditor.audit(dataset, groups=GROUPS)

    ranked = audit.features.set_index("feature")["mutual_information"]
    assert ranked["growth_yoy_lag1"] > ranked["vix"]
    assert audit.features["feature"].iloc[0] in {"growth_yoy_lag1", "growth_yoy_lag2"}


def test_a_fully_missing_feature_is_reported_not_scored(
    auditor: FeatureAuditor, dataset: pd.DataFrame
) -> None:
    audit = auditor.audit(dataset, groups=GROUPS)

    real_rate = audit.features.set_index("feature").loc["real_rate"]
    assert real_rate["missing_share"] == pytest.approx(1.0)
    assert np.isnan(real_rate["mutual_information"])


def test_a_categorical_feature_is_scored_as_discrete(
    auditor: FeatureAuditor, dataset: pd.DataFrame
) -> None:
    audit = auditor.audit(dataset, groups=GROUPS)

    sector = audit.features.set_index("feature").loc["sector"]
    assert sector["mutual_information"] >= 0
    assert np.isnan(sector["spearman"])


def test_near_duplicate_features_are_redundant(
    auditor: FeatureAuditor, dataset: pd.DataFrame
) -> None:
    audit = auditor.audit(dataset, groups=GROUPS)

    assert audit.redundant_pairs[["left", "right"]].to_numpy().tolist() == [
        ["growth_yoy_lag1", "growth_yoy_lag2"]
    ]


def test_the_group_summary_has_one_row_per_group(
    auditor: FeatureAuditor, dataset: pd.DataFrame
) -> None:
    audit = auditor.audit(dataset, groups=GROUPS)

    assert sorted(audit.groups["group"]) == ["L", "S", "X", "XD"]
    lags = audit.groups.set_index("group").loc["L"]
    assert lags["features"] == len([g for g in GROUPS.values() if g == "L"])

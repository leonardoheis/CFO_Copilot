import numpy as np
import pandas as pd
import pytest

from app.services.diagnostics import (
    DecisionInputs,
    DecisionSettings,
    DecisionTableBuilder,
)
from app.services.features import TargetVariable

ROWS_PER_REGIME = 60
COMPANIES = 4


@pytest.fixture
def builder() -> DecisionTableBuilder:
    return DecisionTableBuilder(settings=DecisionSettings())


def _dataset(regime_shift: float) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    regimes = np.repeat([0, 1, 2], ROWS_PER_REGIME)
    return pd.DataFrame({
        "seasonality_regime": regimes,
        "y": rng.normal(size=regimes.size) + regime_shift * regimes,
    })


def _inputs(
    *,
    regime_shift: float = 0.0,
    ljung_box_p: tuple[float, ...] = (0.01, 0.01, 0.01, 0.5),
    register: pd.DataFrame | None = None,
) -> DecisionInputs:
    return DecisionInputs(
        variable=TargetVariable.REVENUE,
        excluded_companies={"COP": "docs/specs/ingestion-defects-cop-ge.md"},
        register=register
        if register is not None
        else pd.DataFrame({"ticker": [], "column": [], "direction": []}),
        feature_groups=pd.DataFrame({
            "group": ["L", "F"],
            "best_mutual_information": [0.3, 0.002],
        }),
        dataset=_dataset(regime_shift),
        ljung_box_p=pd.Series(ljung_box_p, index=[f"T{i}" for i in range(COMPANIES)]),
    )


def _row(builder: DecisionTableBuilder, inputs: DecisionInputs, decision: str) -> str:
    table = builder.build(inputs)
    return next(row.action for row in table if row.decision == decision)


def test_there_is_one_row_per_decision_type(builder: DecisionTableBuilder) -> None:
    table = builder.build(_inputs())

    assert [row.decision for row in table] == [
        "target_transform",
        "exclusions",
        "feature_groups",
        "pooled_or_segmented",
        "forecastable",
    ]
    assert all(row.applies_to == "revenue_usd_m" for row in table)


def test_a_noise_group_is_a_drop_candidate_and_a_strong_one_is_not(
    builder: DecisionTableBuilder,
) -> None:
    action = _row(builder, _inputs(), "feature_groups")

    assert "F" in action
    assert "L" not in action


def test_differing_regimes_name_per_regime_models(
    builder: DecisionTableBuilder,
) -> None:
    assert "segmented" in _row(
        builder, _inputs(regime_shift=1.0), "pooled_or_segmented"
    )
    assert "pooled" in _row(builder, _inputs(regime_shift=0.0), "pooled_or_segmented")


def test_white_noise_targets_are_not_forecastable(
    builder: DecisionTableBuilder,
) -> None:
    noise = _inputs(ljung_box_p=(0.4, 0.6, 0.01, 0.9))

    assert _row(builder, _inputs(), "forecastable").startswith("forecastable")
    assert _row(builder, noise, "forecastable").startswith("not forecastable")


def test_exclusions_name_defect_companies_and_non_positive_targets(
    builder: DecisionTableBuilder,
) -> None:
    register = pd.DataFrame({
        "ticker": ["AAA", "BBB"],
        "column": ["revenue_usd_m", "stock_price"],
        "direction": ["non_positive", "non_positive"],
    })

    action = _row(builder, _inputs(register=register), "exclusions")

    assert "COP" in action
    assert "AAA" in action
    assert "BBB" not in action


def test_a_single_arm_variable_has_nothing_to_compare(
    builder: DecisionTableBuilder,
) -> None:
    ebitda = _inputs()._replace(variable=TargetVariable.EBITDA)

    assert _row(builder, ebitda, "target_transform") == "export revenue_scaled_yoy"
    assert "compare" in _row(builder, _inputs(), "target_transform")

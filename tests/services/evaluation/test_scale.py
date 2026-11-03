import numpy as np
import pandas as pd
import pytest

from app.domain import TargetVariable
from app.services.evaluation import on_error_scale, reconstruct_on_error_scale
from app.services.features import TargetArm, TargetTransformer, arms_for

QUARTERS = 16
HORIZON = 2


@pytest.fixture
def panel() -> pd.DataFrame:
    quarter = np.arange(QUARTERS)
    revenue = 100.0 * np.exp(0.02 * quarter + 0.1 * np.sin(np.pi * quarter / 2))
    return pd.DataFrame({
        "ticker": "AAA",
        "date": pd.date_range("2020-03-31", periods=QUARTERS, freq="QE"),
        TargetVariable.REVENUE: revenue,
        # Crosses zero, as EBITDA does for 28 companies in the panel.
        TargetVariable.EBITDA: 0.1 * revenue * np.cos(np.pi * quarter / 3),
    })


def _true_target(
    panel: pd.DataFrame, arm: TargetArm, variable: TargetVariable
) -> pd.Series:
    target = TargetTransformer(arm=arm, horizon=HORIZON).make(
        panel[variable], revenue=panel[TargetVariable.REVENUE]
    )
    return pd.Series(target.to_numpy(), index=panel["date"])


def test_revenue_is_scored_in_log_level(panel: pd.DataFrame) -> None:
    level = panel[TargetVariable.REVENUE]

    scaled = on_error_scale(TargetVariable.REVENUE, level, level)

    np.testing.assert_allclose(scaled, np.log(level))


def test_a_signed_target_is_scored_per_unit_of_trailing_revenue(
    panel: pd.DataFrame,
) -> None:
    revenue = panel[TargetVariable.REVENUE]

    scaled = on_error_scale(
        TargetVariable.EBITDA, panel[TargetVariable.EBITDA], revenue
    )

    origin = 7
    expected = (
        panel[TargetVariable.EBITDA][origin] / revenue[origin - 3 : origin + 1].sum()
    )
    assert scaled[origin] == pytest.approx(expected, rel=1e-12)
    assert scaled[:3].isna().all()


@pytest.mark.parametrize("arm", arms_for(TargetVariable.REVENUE))
def test_every_revenue_arm_scores_its_true_target_as_the_actual(
    panel: pd.DataFrame, arm: TargetArm
) -> None:
    scored = reconstruct_on_error_scale(
        panel,
        variable=TargetVariable.REVENUE,
        arm=arm,
        horizon=HORIZON,
        prediction=_true_target(panel, arm, TargetVariable.REVENUE),
    )

    known = scored.dropna()
    assert len(known) > 0
    np.testing.assert_allclose(known["y_hat_level"], known["y_level"], rtol=1e-9)
    np.testing.assert_allclose(known["y_hat_scaled"], known["y_scaled"], atol=1e-9)


def test_a_revenue_scaled_error_is_its_target_space_error(panel: pd.DataFrame) -> None:
    arm = TargetArm.REVENUE_SCALED_YOY
    truth = _true_target(panel, arm, TargetVariable.EBITDA)
    prediction = truth + np.random.default_rng(0).normal(0.0, 0.02, size=len(truth))

    scored = reconstruct_on_error_scale(
        panel,
        variable=TargetVariable.EBITDA,
        arm=arm,
        horizon=HORIZON,
        prediction=prediction,
    ).set_index("origin_date")

    error = (scored["y_hat_scaled"] - scored["y_scaled"]).dropna()
    target_space_error = (prediction - truth)[error.index]
    np.testing.assert_allclose(error, target_space_error, rtol=0, atol=1e-12)


def test_an_origin_without_a_prediction_stays_missing(panel: pd.DataFrame) -> None:
    arm = TargetArm.LOG_DIFF4
    prediction = _true_target(panel, arm, TargetVariable.REVENUE).drop(panel["date"][8])

    scored = reconstruct_on_error_scale(
        panel,
        variable=TargetVariable.REVENUE,
        arm=arm,
        horizon=HORIZON,
        prediction=prediction,
    )

    assert scored["y_hat_scaled"].isna()[8]
    assert scored["y_scaled"].notna()[8]

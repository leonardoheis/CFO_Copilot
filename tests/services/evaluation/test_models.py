from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain import TargetVariable
from app.services.evaluation import EvaluationRecord, EvaluationSettings
from app.services.features import TargetArm

RECORD: dict[str, Any] = {
    "model": "seasonal_naive",
    "variable": TargetVariable.REVENUE,
    "arm": TargetArm.SEASNAIVE_RESIDUAL,
    "protocol": "A",
    "ticker": "AAA",
    "sector": "Technology",
    "origin_date": date(2024, 3, 31),
    "target_date": date(2024, 6, 30),
    "horizon": 1,
    "level": 0.9,
    "y_scaled": 4.6,
    "y_level": 100.0,
    "y_hat_scaled": 4.5,
    "y_hat_level": 90.0,
    "harness_version": "nb02-dev",
    "data_freeze": "thesis_2026-10-30",
    "git_commit": "2949c0d",
}


def test_defaults_are_the_specs_values() -> None:
    assert EvaluationSettings().model_dump() == {
        "interval_levels": (0.80, 0.90, 0.95),
        "n_origins": 16,
        "n_folds": 12,
        "histories": (8, 12, 20, 40),
        "calibration_window": 20,
        "seed": 42,
    }


@pytest.mark.parametrize("levels", [(0.0, 0.9), (0.9, 1.0), (0.9, 0.8), (0.9, 0.9)])
def test_interval_levels_are_ascending_inside_the_unit_interval(
    levels: tuple[float, ...],
) -> None:
    with pytest.raises(ValidationError):
        EvaluationSettings(interval_levels=levels)


@pytest.mark.parametrize("histories", [(0, 8), (12, 8), (8, 8)])
def test_histories_are_positive_and_ascending(histories: tuple[int, ...]) -> None:
    with pytest.raises(ValidationError):
        EvaluationSettings(histories=histories)


def test_custom_levels_and_histories_are_kept() -> None:
    settings = EvaluationSettings(interval_levels=(0.5, 0.8), histories=(4, 40))

    assert settings.interval_levels == (0.5, 0.8)
    assert settings.histories == (4, 40)


def test_settings_refuse_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        EvaluationSettings(n_origin=16)  # type: ignore[call-arg]


def test_a_record_keeps_plain_strings_for_the_results_store() -> None:
    dumped = EvaluationRecord(**RECORD).model_dump()

    assert dumped["variable"] == "revenue_usd_m"
    assert dumped["arm"] == "seasnaive_residual"


def test_a_missing_prediction_is_recorded_not_refused() -> None:
    record = EvaluationRecord(**{**RECORD, "y_hat_scaled": None, "y_hat_level": None})

    assert record.y_hat_scaled is None


@pytest.mark.parametrize("extra", [{"fold": 3}, {"history": 8}])
def test_protocol_a_has_no_fold_or_history(extra: dict[str, int]) -> None:
    with pytest.raises(ValidationError, match="Protocol A"):
        EvaluationRecord(**{**RECORD, **extra})


def test_protocol_b_needs_its_fold() -> None:
    with pytest.raises(ValidationError, match="fold"):
        EvaluationRecord(**{**RECORD, "protocol": "B", "history": 8})


def test_protocol_b_with_all_history_has_no_history_value() -> None:
    record = EvaluationRecord(**{**RECORD, "protocol": "B", "fold": 3})

    assert record.history is None


@pytest.mark.parametrize("horizon", [0, 5])
def test_horizon_is_one_to_four(horizon: int) -> None:
    with pytest.raises(ValidationError):
        EvaluationRecord(**{**RECORD, "horizon": horizon})


def test_an_inverted_interval_is_refused() -> None:
    with pytest.raises(ValidationError, match="exceeds"):
        EvaluationRecord(**{**RECORD, "lower_scaled": 4.7, "upper_scaled": 4.5})


def test_a_target_on_or_before_its_origin_is_refused() -> None:
    with pytest.raises(ValidationError, match="not after origin"):
        EvaluationRecord(**{**RECORD, "target_date": date(2024, 3, 31)})

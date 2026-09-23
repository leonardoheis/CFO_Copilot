from pathlib import Path

import pytest

from app.services.helper import load_model, save_model
from app.services.training.scaled_linear_regression import ScaledLinearRegression


def test_load_model_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    assert load_model(tmp_path / "missing.joblib") is None


def test_save_then_load_model_round_trips(tmp_path: Path) -> None:
    model_path = tmp_path / "model.joblib"
    model = ScaledLinearRegression().fit([[1.0], [2.0]], [2.0, 4.0])

    save_model(model, model_path)

    loaded = load_model(model_path)
    assert loaded is not None
    assert loaded.predict([[3.0]])[0] == pytest.approx(6.0)

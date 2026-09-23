from pathlib import Path

import pytest

from app.domain import PredictionInput
from app.services.helper import save_model
from app.services.prediction import NoTrainedModelError, PredictionService
from app.services.training.scaled_linear_regression import ScaledLinearRegression


def test_predict_without_a_saved_model_raises(tmp_path: Path) -> None:
    service = PredictionService(model_path=tmp_path / "missing.joblib")
    prediction_input = PredictionInput(age=10)

    with pytest.raises(NoTrainedModelError):
        service.predict(prediction_input)


def test_predict_uses_the_saved_model(tmp_path: Path) -> None:
    model_path = tmp_path / "model.joblib"
    save_model(ScaledLinearRegression().fit([[1.0], [2.0]], [2.0, 4.0]), model_path)

    output = PredictionService(model_path=model_path).predict(PredictionInput(age=3))

    assert output.time_for_failure == pytest.approx(6.0)

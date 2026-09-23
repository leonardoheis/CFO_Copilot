from pathlib import Path

from app.services.helper import load_model, save_model
from app.services.training import TrainingService
from app.services.training.scaled_linear_regression import ScaledLinearRegression


def test_train_fits_and_persists_the_model(tmp_path: Path) -> None:
    model_path = tmp_path / "model.joblib"

    TrainingService(model_path=model_path).train([[1.0], [2.0], [3.0]], [2.0, 4.0, 6.0])

    assert load_model(model_path) is not None


def test_train_reuses_an_existing_saved_model(tmp_path: Path) -> None:
    model_path = tmp_path / "model.joblib"
    existing = ScaledLinearRegression()
    save_model(existing, model_path)

    trained = TrainingService(model_path=model_path).train([[1.0], [2.0]], [2.0, 4.0])

    assert isinstance(trained, ScaledLinearRegression)

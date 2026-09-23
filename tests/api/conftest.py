from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from app.api import create_app
from app.injections import configure_container
from app.services import PredictionService, TrainingService


@pytest.fixture
def client(_isolated_model_path: None) -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture
def _isolated_model_path(tmp_path: Path) -> Generator[None]:
    container = configure_container()
    model_path = tmp_path / "model.joblib"
    with (
        container.training_service.override(
            providers.Factory(TrainingService, model_path=model_path)
        ),
        container.prediction_service.override(
            providers.Factory(PredictionService, model_path=model_path)
        ),
    ):
        yield

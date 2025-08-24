from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector.wiring import Provide, inject

from app.services.training import TrainingService
from app.settings import Settings


@pytest.fixture
def model_path() -> Generator[Path]:
    model_path = Settings.MODEL_DIRECTORY / "model_test.joblib"
    model_path.unlink(missing_ok=True)
    yield model_path
    model_path.unlink(missing_ok=True)


@pytest.fixture
@inject
def training_service(
    model_path: Path,
    training_service_: TrainingService = Provide["training_service"],
) -> TrainingService:
    training_service_.model_path = model_path
    return training_service_


@pytest.fixture
def training_data_dimension_mismatch() -> tuple[list[list[float]], list[float]]:
    X = [[25.0], [30.0], [35.0]]
    y = [5.0, 6.0]
    return X, y

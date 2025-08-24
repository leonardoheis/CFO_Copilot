import pytest

from app.services.training import DimensionalityMismatchError, TrainingService


def test_train_with_mismatched_dimensions(
    training_service: TrainingService,
    training_data_dimension_mismatch: tuple[list[list[float]], list[float]],
) -> None:
    with pytest.raises(DimensionalityMismatchError):
        training_service.train(*training_data_dimension_mismatch)

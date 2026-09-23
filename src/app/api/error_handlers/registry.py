from collections.abc import Callable

from fastapi import Request, Response

from app.services.prediction import NoTrainedModelError
from app.services.training import DimensionalityMismatchError

from .prediction import no_trained_model_handler
from .training import dimensionality_mismatch_handler

ExceptionHandler = Callable[[Request, Exception], Response]

EXCEPTION_HANDLERS: dict[type[Exception], ExceptionHandler] = {
    DimensionalityMismatchError: dimensionality_mismatch_handler,  # type: ignore[dict-item]
    NoTrainedModelError: no_trained_model_handler,  # type: ignore[dict-item]
}

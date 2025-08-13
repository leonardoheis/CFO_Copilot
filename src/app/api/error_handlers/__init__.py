from collections.abc import Callable

from fastapi import Request, Response

from app.services.training import DimensionalityMismatchError

from .generic import generic_exception_handler
from .training import dimensionality_mismatch_handler

ExceptionHandler = Callable[[Request, Exception], Response]

EXCEPTION_HANDLERS: dict[type[Exception], ExceptionHandler] = {
    Exception: generic_exception_handler,
    DimensionalityMismatchError: dimensionality_mismatch_handler,  # type: ignore[dict-item]
}

__all__ = ["EXCEPTION_HANDLERS", "generic_exception_handler"]

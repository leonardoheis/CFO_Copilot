from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.training import DimensionalityMismatchError


def dimensionality_mismatch_handler(
    _: Request,
    exc: DimensionalityMismatchError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )

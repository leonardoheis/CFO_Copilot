from fastapi import Request
from fastapi.responses import JSONResponse


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001  # pylint: disable=unused-argument
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )

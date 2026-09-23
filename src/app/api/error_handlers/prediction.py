from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.prediction import NoTrainedModelError


def no_trained_model_handler(_: Request, exc: NoTrainedModelError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.message})

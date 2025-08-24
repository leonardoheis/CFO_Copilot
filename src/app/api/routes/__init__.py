from collections.abc import Iterable

from fastapi import APIRouter

from .health import health_router
from .prediction import PredictionRequest, PredictionResponse, prediction_router
from .train import TrainRequest, TrainResponse, train_router

ROUTERS: Iterable[APIRouter] = (
    health_router,
    prediction_router,
    train_router,
)

__all__ = [
    "ROUTERS",
    "PredictionRequest",
    "PredictionResponse",
    "TrainRequest",
    "TrainResponse",
    "health_router",
    "prediction_router",
    "train_router",
]

from .health import health_router
from .prediction import PredictionRequest, PredictionResponse, prediction_router
from .registry import ROUTERS
from .train import TrainRequest, TrainResponse, train_router

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

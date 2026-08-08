from collections.abc import Iterable

from fastapi import APIRouter

from .health import health_router
from .prediction import prediction_router
from .train import train_router

ROUTERS: Iterable[APIRouter] = (
    health_router,
    prediction_router,
    train_router,
)

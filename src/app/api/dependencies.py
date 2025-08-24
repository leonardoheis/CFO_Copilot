from typing import Annotated

from dependency_injector.wiring import Provide
from fastapi import Depends

from app.services import PredictionService, TrainingService

PredictionServiceDependency = Annotated[
    PredictionService,
    Depends(Provide["prediction_service"]),
]

TrainingServiceDependency = Annotated[
    TrainingService,
    Depends(Provide["training_service"]),
]

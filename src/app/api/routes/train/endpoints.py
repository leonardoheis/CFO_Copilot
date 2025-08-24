from dependency_injector.wiring import inject
from fastapi import APIRouter

from app.api.dependencies import TrainingServiceDependency

from .schemas import TrainRequest, TrainResponse

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.post("/train")
@inject
def train(
    training_record: TrainRequest, training_service: TrainingServiceDependency
) -> TrainResponse:
    ages = [[age] for age in training_record.age]
    training_service.train(ages, training_record.time_for_failure)
    return TrainResponse()

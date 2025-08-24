from dependency_injector.wiring import inject
from fastapi import APIRouter

from app.api.dependencies import TrainingServiceDependency

from .responses import RESPONSES
from .schemas import TrainRequest, TrainResponse

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.post("/train", responses=RESPONSES)
@inject
def train(
    training_record: TrainRequest,
    training_service: TrainingServiceDependency,
) -> TrainResponse:
    training_service.train(training_record.age, training_record.time_for_failure)
    return TrainResponse()

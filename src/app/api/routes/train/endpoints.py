from fastapi import APIRouter

from app.api.dependencies import TrainingServiceDependency

from .schemas import TrainRecord, TrainResponse

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.post("/train")
def train(
    training_record: TrainRecord, training_service: TrainingServiceDependency
) -> TrainResponse:
    model = training_service.train(
        training_record.age, training_record.time_for_failure
    )
    return TrainResponse(model=model)

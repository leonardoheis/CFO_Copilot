from automapper import mapper
from dependency_injector.wiring import inject
from fastapi import APIRouter

from app.api.dependencies import PredictionServiceDependency
from app.domain import PredictionInput

from .schemas import PredictionRequest, PredictionResponse

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.post("/predict")
@inject
async def predict(
    body: PredictionRequest,
    prediction_service: PredictionServiceDependency,
) -> PredictionResponse:
    prediction_input = mapper.to(PredictionInput).map(body)
    prediction_output = prediction_service.predict(prediction_input)
    return mapper.to(PredictionResponse).map(prediction_output)

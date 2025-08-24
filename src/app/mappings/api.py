from automapper import mapper

from app.api.routes import PredictionRequest, PredictionResponse
from app.domain import PredictionInput, PredictionOutput

mapper.add(
    PredictionRequest,
    PredictionInput,
    fields_mapping={"age": "PredictionRequest.input_"},
)
mapper.add(
    PredictionOutput,
    PredictionResponse,
    fields_mapping={"result": "PredictionOutput.time_for_failure"},
)

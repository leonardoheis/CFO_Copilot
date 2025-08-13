from pydantic import BaseModel, Field

from app.domain import MLModel, PredictionInput, PredictionOutput
from app.services.helper import load_model

from .exceptions import NoTrainedModelError


class PredictionService(BaseModel):
    model: MLModel | None = Field(default_factory=load_model)

    def predict(self, prediction_input: PredictionInput) -> PredictionOutput:
        if self.model is None:
            raise NoTrainedModelError
        time_for_failure = self.model.predict(prediction_input.age)  # pylint: disable=no-member
        return PredictionOutput(time_for_failure=time_for_failure)

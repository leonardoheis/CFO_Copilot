from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.domain import MLModel, PredictionInput, PredictionOutput
from app.services.helper import load_model
from app.settings import Settings

from .exceptions import NoTrainedModelError


class PredictionService(BaseModel):
    model_path: Path = Field(default=Settings.MODEL_PATH)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def model(self) -> MLModel | None:
        return load_model(self.model_path)

    def predict(self, prediction_input: PredictionInput) -> PredictionOutput:
        if self.model is None:
            raise NoTrainedModelError
        time_for_failure = self.model.predict([[prediction_input.age]])
        return PredictionOutput(time_for_failure=time_for_failure)

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.domain import MLModel
from app.services.helper import load_model, save_model
from app.settings import Settings

from .exceptions import DimensionalityMismatchError


class TrainingService(BaseModel):
    model_path: Path = Field(default=Settings.MODEL_PATH)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def model(self) -> MLModel:
        if self.model_path.exists():
            model = load_model(self.model_path)
            if model:
                return model

        return make_pipeline([StandardScaler(), LinearRegression()])  # type: ignore[return-value]

    def train(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> MLModel:
        if len(X) != len(y):
            raise DimensionalityMismatchError(x_dim=len(X), y_dim=len(y))

        pipeline = self.model
        pipeline_fit = pipeline.fit(X, y)
        save_model(pipeline_fit, self.model_path)
        return pipeline

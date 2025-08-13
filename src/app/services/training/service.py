from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.domain import MLModel
from app.services.helper import load_model, save_model

from .exceptions import DimensionalityMismatchError


class TrainingService(BaseModel):
    model: MLModel | None = Field(default_factory=load_model)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @staticmethod
    def build_model() -> MLModel:
        return make_pipeline([StandardScaler(), LinearRegression()])  # type: ignore[no-any-return]

    def train(self, X: Sequence[Any], y: Sequence[Any]) -> MLModel:
        if len(X) != len(y):
            raise DimensionalityMismatchError(x_dim=len(X), y_dim=len(y))

        pipeline = self.build_model()
        pipeline.fit(X, y)
        save_model(pipeline)
        return pipeline

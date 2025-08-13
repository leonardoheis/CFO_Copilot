from collections.abc import Sequence
from typing import Self

from pydantic import Field, model_validator

from app.api.schema import BaseSchema
from app.services.training import MLModel


class TrainRecord(BaseSchema):
    age: Sequence[float]
    time_for_failure: Sequence[float]

    @model_validator(mode="after")
    def features_and_labels_have_same_length(self) -> Self:
        if len(self.age) != len(self.time_for_failure):
            msg = "Features and labels must have the same length"
            raise ValueError(msg)
        return self


class TrainResponse(BaseSchema):
    model: MLModel = Field(exclude=True)

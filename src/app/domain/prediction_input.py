from pydantic import Field

from .base import BaseEntity


class PredictionInput(BaseEntity):
    age: float = Field(gt=0, description="Age of the machine in days")

from pydantic import Field

from .base import BaseEntity


class PredictionOutput(BaseEntity):
    time_for_failure: float = Field(gt=0, description="Time until failure in days")

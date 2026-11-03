from datetime import date
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.domain import EvaluationProtocol, TargetVariable
from app.services.features.transforms import MAX_HORIZON, TargetArm
from app.settings import RANDOM_SEED

UnitInterval = Annotated[float, Field(gt=0.0, lt=1.0)]


def _strictly_ascending[T: (float, int)](values: tuple[T, ...]) -> tuple[T, ...]:
    if list(values) != sorted(set(values)):
        message = f"must be strictly ascending, got {values}"
        raise ValueError(message)
    return values


class EvaluationSettings(BaseModel):
    """The fixed choices every model is scored under (spec R2, R3, R8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    interval_levels: Annotated[
        tuple[UnitInterval, ...], AfterValidator(_strictly_ascending)
    ] = (0.80, 0.90, 0.95)
    n_origins: int = Field(default=16, ge=1)
    n_folds: int = Field(default=12, ge=2)
    # Quarters of the held-out company's own history; "all" is not truncated.
    histories: Annotated[
        tuple[Annotated[int, Field(ge=1)], ...], AfterValidator(_strictly_ascending)
    ] = (8, 12, 20, 40)
    # Earlier origins whose errors calibrate an interval; it reaches back before
    # the first reported origin so that origin already has errors (plan step 9).
    calibration_window: int = Field(default=20, ge=1)
    seed: int = RANDOM_SEED


class EvaluationRecord(BaseModel):
    """One scored forecast at one interval level (spec R10).

    ``*_scaled`` values are on the error scale of spec R5; ``*_level`` values
    are in the target's own units. A missing prediction stays ``None`` (R4).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=True)

    model: str
    variable: TargetVariable
    arm: TargetArm
    protocol: EvaluationProtocol
    # Protocol B only: quarters of history kept, None for all of it.
    history: int | None = Field(default=None, ge=1)
    fold: int | None = Field(default=None, ge=0)
    ticker: str
    sector: str
    origin_date: date
    target_date: date
    horizon: int = Field(ge=1, le=MAX_HORIZON)
    level: UnitInterval
    y_scaled: float
    y_level: float
    y_hat_scaled: float | None
    y_hat_level: float | None
    lower_scaled: float | None = None
    upper_scaled: float | None = None
    harness_version: str
    data_freeze: str
    git_commit: str

    @model_validator(mode="after")
    def _fold_and_history_belong_to_protocol_b(self) -> Self:
        if self.protocol == "A" and (self.fold is not None or self.history is not None):
            message = "Protocol A has no fold and no history truncation"
            raise ValueError(message)
        if self.protocol == "B" and self.fold is None:
            message = "a Protocol B record needs the fold of its held-out company"
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _interval_is_ordered(self) -> Self:
        if (
            self.lower_scaled is not None
            and self.upper_scaled is not None
            and self.lower_scaled > self.upper_scaled
        ):
            message = f"lower {self.lower_scaled} exceeds upper {self.upper_scaled}"
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _target_follows_origin(self) -> Self:
        if self.target_date <= self.origin_date:
            message = f"target {self.target_date} is not after origin {self.origin_date}"
            raise ValueError(message)
        return self

import math
from collections.abc import Callable, Sequence
from typing import Self

import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator

from app.services.features.exceptions import LeakageError


class LeakageSettings(BaseModel):
    """How far the guard moves later quarters before rebuilding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scramble_scale: float = 3.0
    scramble_shift: float = 1.0

    @model_validator(mode="after")
    def _scrambles_something(self) -> Self:
        # Scale 1 with shift 0 leaves every value in place, so any builder passes.
        if math.isclose(self.scramble_scale, 1.0) and math.isclose(
            self.scramble_shift, 0.0, abs_tol=1e-12
        ):
            message = "scramble scale 1 with shift 0 would leave later quarters as is"
            raise ValueError(message)
        return self


class LookaheadGuard:
    """Prove a feature builder reads nothing after each row's origin.

    Usage::

        guard = LookaheadGuard(settings=LeakageSettings())
        guard.check(build, panel, origins=[3, 8, 15])
    """

    def __init__(self, settings: LeakageSettings) -> None:
        self._settings = settings

    def _with_later_quarters_scrambled(
        self, panel: pd.DataFrame, origin: int
    ) -> pd.DataFrame:
        scrambled = panel.copy()
        numeric_columns = scrambled.select_dtypes("number").columns
        later_rows = scrambled.index[origin + 1 :]
        scrambled.loc[later_rows, numeric_columns] = (
            scrambled.loc[later_rows, numeric_columns] * self._settings.scramble_scale
            + self._settings.scramble_shift
        )
        return scrambled

    def check(
        self,
        build: Callable[[pd.DataFrame], pd.DataFrame],
        panel: pd.DataFrame,
        *,
        origins: Sequence[int],
    ) -> None:
        """Fail when a row's features change after only later quarters change.

        Raises:
            LeakageError: naming the columns that moved and the origin row.
        """
        baseline = build(panel)
        for origin in origins:
            scrambled = build(self._with_later_quarters_scrambled(panel, origin))
            before, after = baseline.iloc[origin], scrambled.iloc[origin]
            unchanged = (before == after) | (before.isna() & after.isna())
            if not unchanged.all():
                moved = tuple(str(column) for column in unchanged.index[~unchanged])
                raise LeakageError(origin=origin, columns=moved)

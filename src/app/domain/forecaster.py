from typing import Protocol, Self

import pandas as pd


class Forecaster(Protocol):
    """What the evaluation harness needs from a model, whatever its family.

    ``train`` and ``test`` are rows of a feature dataset. ``predict`` returns a
    ``y_hat`` column indexed like ``test``, NaN where the model cannot predict,
    in the target space of the dataset's arm; the harness turns it into levels
    itself. Both arguments are positional-only, so a model that ignores one may
    name it ``_train``.

    Protocol B passes ``history``: predict as if the company had only that many
    quarters. Its features are already blanked to match, so only a model that
    reads the company's past itself, like a baseline, has to honour it.
    """

    def fit(self, train: pd.DataFrame, /) -> Self: ...

    def predict(
        self, test: pd.DataFrame, /, *, history: int | None = None
    ) -> pd.DataFrame: ...

from typing import Protocol, Self

import pandas as pd


class Forecaster(Protocol):
    """What the evaluation harness needs from a model, whatever its family.

    ``train`` and ``test`` are rows of a feature dataset; predictions are in
    the target space of the dataset's arm, and the harness turns them into
    levels itself. Both are positional-only, so a model that ignores one may
    name it ``_train``.
    """

    def fit(self, train: pd.DataFrame, /) -> Self: ...

    def predict(self, test: pd.DataFrame, /) -> pd.DataFrame:
        """Predict every test row.

        Returns:
            A ``y_hat`` column indexed like ``test``; NaN where the model
            cannot predict.
        """
        ...

from collections.abc import Sequence
from typing import Any, Protocol, Self, cast

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class _Estimator(Protocol):
    """The slice of sklearn's untyped estimator API this wrapper relies on."""

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> Self: ...

    def predict(self, X: Sequence[Sequence[float]]) -> Any: ...


class ScaledLinearRegression:
    """A standardising scaler feeding a linear regression, exposed as an `MLModel`."""

    def __init__(self) -> None:
        self._pipeline = cast(
            "_Estimator",
            Pipeline([
                ("scaler", StandardScaler()),
                ("regression", LinearRegression()),
            ]),
        )

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> Self:
        self._pipeline.fit(X, y)
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> Sequence[float]:
        return [float(value) for value in np.asarray(self._pipeline.predict(X))]

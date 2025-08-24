from collections.abc import Sequence
from typing import Protocol, Self, runtime_checkable


@runtime_checkable
class MLModel(Protocol):
    def predict(self, X: Sequence[Sequence[float]]) -> float: ...

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> Self: ...

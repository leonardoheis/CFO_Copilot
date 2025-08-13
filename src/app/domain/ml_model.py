from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class MLModel(Protocol):
    def predict(self, X: float) -> float: ...

    def fit(self, X: Sequence[float], y: Sequence[float]) -> None: ...

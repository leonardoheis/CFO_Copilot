from collections.abc import Sequence
from typing import Protocol


class MLModel(Protocol):
    def predict(self, X: float) -> float: ...

    def fit(self, X: Sequence[float], y: Sequence[float]) -> None: ...

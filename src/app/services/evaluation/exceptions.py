from dataclasses import dataclass


class EvaluationError(Exception):
    """Base error for the evaluation harness."""


@dataclass
class TooFewOriginsError(EvaluationError):
    """Raised when the data has fewer labelled origins than the protocol scores."""

    requested: int
    available: int

    def __str__(self) -> str:
        return (
            f"asked for {self.requested} labelled origins, "
            f"the data has {self.available}"
        )

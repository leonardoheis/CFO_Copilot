from dataclasses import dataclass


@dataclass
class DimensionalityMismatchError(Exception):
    x_dim: int
    y_dim: int

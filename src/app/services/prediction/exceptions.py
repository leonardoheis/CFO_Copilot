from dataclasses import dataclass


@dataclass
class NoTrainedModelError(Exception): ...

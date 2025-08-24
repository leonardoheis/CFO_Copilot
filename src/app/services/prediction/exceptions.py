from dataclasses import dataclass


@dataclass
class NoTrainedModelError(Exception):
    message: str = (
        "No trained model found. Please train the model before making predictions."
    )

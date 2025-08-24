from fastapi.openapi.models import Example

from .schemas import PredictionRequest

EXAMPLES: dict[str, Example] = {
    "normal": {
        "summary": "A normal example",
        "description": "A **normal** item works correctly.",
        "value": PredictionRequest.create_example().model_dump(by_alias=True),
    },
    "invalid": {
        "summary": "An invalid example",
        "description": "A **invalid** item does not work.",
        "value": PredictionRequest.create_example().model_dump(by_alias=True),
    },
}

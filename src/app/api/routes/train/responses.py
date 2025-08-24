from typing import Any

from app.services.training import DimensionalityMismatchError

RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "description": "Dimensionality mismatch error",
        "model": DimensionalityMismatchError,
    }
}

from pathlib import Path

import joblib

from app.domain.ml_model import MLModel


def load_model(model_path: Path) -> MLModel | None:
    if not model_path.exists():
        return None

    return joblib.load(model_path)  # type: ignore[no-any-return]


def save_model(model: MLModel, model_path: Path) -> None:
    joblib.dump(model, model_path)

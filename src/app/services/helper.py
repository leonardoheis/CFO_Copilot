import joblib

from app.domain.ml_model import MLModel
from app.settings import Settings


def load_model() -> MLModel | None:
    if not Settings.MODEL_PATH.exists():
        return None

    return joblib.load(Settings.MODEL_PATH)  # type: ignore[no-any-return]


def save_model(model: MLModel) -> None:
    joblib.dump(model, Settings.MODEL_PATH)

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings_(BaseSettings):
    MODEL_PATH: Path = Path("model.pkl")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


Settings = Settings_()

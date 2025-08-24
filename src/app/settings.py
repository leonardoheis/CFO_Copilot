from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class _Settings(BaseSettings):
    UI_PORT: int = 10000
    API_PORT: int = 8000
    HOST: str = "0.0.0.0"  # nosec

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def MODEL_DIRECTORY(self) -> Path:
        model_directory = self.APP_PATH / "ml_binaries"
        model_directory.mkdir(parents=True, exist_ok=True)
        return model_directory

    @property
    def MODEL_PATH(self) -> Path:
        return self.MODEL_DIRECTORY / "model.joblib"

    @property
    def SOCKET_URL(self) -> str:
        return f"http://{self.HOST}:{{port}}"

    @property
    def APP_PATH(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def ROOT_PATH(self) -> Path:
        return self.APP_PATH.parent.parent

    @property
    def UI_HOST(self) -> str:
        return self.SOCKET_URL.format(port=self.UI_PORT)

    @property
    def UI_PATH(self) -> Path:
        return self.APP_PATH / "frontend"

    @property
    def UI_EXECUTABLE(self) -> Path:
        return self.ROOT_PATH / ".venv/bin/streamlit"

    @property
    def UI_ENTRYPOINT(self) -> Path:
        return self.UI_PATH / "home.py"

    @property
    def API_PATH(self) -> Path:
        return self.APP_PATH / "api"

    @property
    def API_HOST(self) -> str:
        return self.SOCKET_URL.format(port=self.API_PORT)


Settings = _Settings()

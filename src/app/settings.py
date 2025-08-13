from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class _Settings(BaseSettings):
    MODEL_PATH: Path = Path("model.pkl")
    UI_PORT: int = 8501
    API_PORT: int = 8000
    HOST: str = "http://localhost:{port}"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def ROOT_PATH(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def UI_HOST(self) -> str:
        return self.HOST.format(port=self.UI_PORT)

    @property
    def UI_PATH(self) -> Path:
        return self.ROOT_PATH / "frontend"

    @property
    def UI_EXECUTABLE(self) -> Path:
        return Path(".venv/bin/streamlit")

    @property
    def UI_ENTRYPOINT(self) -> Path:
        return self.UI_PATH / "home.py"

    @property
    def API_PATH(self) -> Path:
        return self.ROOT_PATH / "api"

    @property
    def API_HOST(self) -> str:
        return self.HOST.format(port=self.API_PORT)


Settings = _Settings()

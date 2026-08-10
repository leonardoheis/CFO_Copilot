import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class _Settings(BaseSettings):
    UI_PORT: int = 10000
    API_PORT: int = 8000
    HOST: str = "0.0.0.0"  # nosec  # ruff: ignore[hardcoded-bind-all-interfaces]
    FRED_API_KEY: str = ""
    SEC_USER_AGENT: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""

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
        if sys.platform == "win32":
            return self.ROOT_PATH / ".venv/Scripts/streamlit.exe"
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

    @property
    def DATA_DIRECTORY(self) -> Path:
        data_directory = self.ROOT_PATH / "data"
        data_directory.mkdir(parents=True, exist_ok=True)
        return data_directory

    def panel_output_path(self, ticker: str) -> Path:
        processed_directory = self.DATA_DIRECTORY / "processed"
        processed_directory.mkdir(parents=True, exist_ok=True)
        return processed_directory / f"{ticker.upper()}_panel.parquet"


Settings = _Settings()

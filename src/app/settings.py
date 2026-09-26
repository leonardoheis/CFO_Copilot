import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# The container sets WORKDIR to the directory holding .env, so the bare relative
# name must stay. It resolves against the current directory though, which leaves
# every credential empty when the CLI is run from anywhere but the repo root, so
# the checkout's own .env is offered alongside it.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ENV_FILE = _REPOSITORY_ROOT / ".env"


class _Settings(BaseSettings):
    UI_PORT: int = 10000
    API_PORT: int = 8000
    REQUEST_TIMEOUT: int = 30
    HOST: str = "0.0.0.0"  # nosec  # ruff: ignore[hardcoded-bind-all-interfaces]
    FRED_API_KEY: str = ""
    SEC_USER_AGENT: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    LAST_REPORTED_QUARTER: date = date(2026, 6, 30)
    WANDB_PROJECT: str = "cfo-copilot"
    WANDB_ENTITY: str = ""
    WANDB_API_KEY: str = ""
    WANDB_MODE: Literal["online", "offline", "disabled"] = "offline"
    # wandb appends its own `wandb/` folder, so runs land in <repo>/wandb/.
    WANDB_DIR: Path = _REPOSITORY_ROOT

    model_config = SettingsConfigDict(
        env_file=(_REPOSITORY_ENV_FILE, ".env"),
        extra="ignore",
    )

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

    @property
    def COMPANY_REGISTRY_PATH(self) -> Path:
        return self.ROOT_PATH / "config" / "companies.yaml"

    @property
    def STRUCTURAL_BREAKS_PATH(self) -> Path:
        return self.ROOT_PATH / "config" / "structural_breaks.yaml"

    @property
    def PANEL_LONG_PATH(self) -> Path:
        return self.DATA_DIRECTORY / "processed" / "panel_long.parquet"

    @property
    def MACRO_Q_PATH(self) -> Path:
        return self.DATA_DIRECTORY / "processed" / "macro_q.parquet"

    def panel_output_path(self, ticker: str) -> Path:
        processed_directory = self.DATA_DIRECTORY / "processed"
        processed_directory.mkdir(parents=True, exist_ok=True)
        return processed_directory / f"{ticker.upper()}_panel.parquet"

    def features_output_path(self, horizon: int) -> Path:
        features_directory = self.DATA_DIRECTORY / "features"
        features_directory.mkdir(parents=True, exist_ok=True)
        return features_directory / f"features_h{horizon}.parquet"


Settings = _Settings()

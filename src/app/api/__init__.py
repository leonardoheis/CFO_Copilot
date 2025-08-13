import uvicorn

from app.settings import Settings

from .app import create_app


def run_api() -> None:
    uvicorn.run("src.app.api:create_app", factory=True, port=Settings.API_PORT)


__all__ = ["create_app", "run_api"]

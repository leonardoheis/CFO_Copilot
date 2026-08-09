from unittest.mock import patch

from app.api.runner import run_api
from app.settings import Settings


def test_run_api_starts_uvicorn_with_configured_host_and_port() -> None:
    with patch("app.api.runner.uvicorn.run") as uvicorn_run:
        run_api()

    uvicorn_run.assert_called_once_with(
        "app.api:create_app",
        factory=True,
        host=Settings.HOST,
        port=Settings.API_PORT,
    )

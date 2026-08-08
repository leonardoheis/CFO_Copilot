import subprocess  # nosec # ruff: ignore[suspicious-subprocess-import]
import sys

from app.settings import Settings


def run_streamlit() -> None:
    subprocess.run(  # nosec # ruff: ignore[subprocess-without-shell-equals-true]
        [
            sys.executable,
            str(Settings.UI_EXECUTABLE),
            "run",
            str(Settings.UI_ENTRYPOINT),
            "--server.port",
            str(Settings.UI_PORT),
            "--server.headless",
            "true",
        ],
        check=True,
    )

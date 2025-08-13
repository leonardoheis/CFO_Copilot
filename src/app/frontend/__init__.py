import subprocess  # nosec
import sys

from app.settings import Settings


def run_streamlit() -> None:
    subprocess.run(  # nosec
        [
            sys.executable,
            Settings.UI_EXECUTABLE,
            "run",
            Settings.UI_ENTRYPOINT,
            "--server.port",
            str(Settings.UI_PORT),
            "--server.headless",
            "true",
        ],
        check=True,
    )


__all__ = ["run_streamlit"]

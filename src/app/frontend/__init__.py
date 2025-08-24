import subprocess  # nosec # noqa: S404
import sys

from app.settings import Settings


def run_streamlit() -> None:
    subprocess.run(  # nosec # noqa: S603
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


__all__ = ["run_streamlit"]

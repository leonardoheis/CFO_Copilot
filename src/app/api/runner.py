import uvicorn

from app.settings import Settings


def run_api() -> None:
    uvicorn.run(
        "app.api:create_app",
        factory=True,
        host=Settings.HOST,
        port=Settings.API_PORT,
    )

from fastapi import FastAPI

from .error_handlers import EXCEPTION_HANDLERS
from .routes import prediction_router, train_router


def create_app() -> FastAPI:
    app = FastAPI(title="FastAPI Production Template")

    app.include_router(prediction_router)
    app.include_router(train_router)

    for exception, exception_handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception, exception_handler)

    return app

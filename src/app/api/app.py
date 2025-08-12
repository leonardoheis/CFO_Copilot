# FastAPI app scaffolding with exception handlers, routers, and service injection
from fastapi import FastAPI
from .routes.prediction.endpoints import router as prediction_router
from .error_handlers import register_error_handlers
from app.services import ServiceContainer

def create_app() -> FastAPI:
	app = FastAPI(title="FastAPI Production Template")

	# Dependency Injection: create service container
	services = ServiceContainer()
	app.state.services = services

	# Register routers
	app.include_router(prediction_router, prefix="/prediction")

	# Register exception handlers
	register_error_handlers(app)

	return app

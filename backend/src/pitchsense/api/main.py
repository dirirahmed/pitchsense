"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pitchsense import __version__
from pitchsense.api.routes import health, matches, predictions, replay
from pitchsense.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PitchSense API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(matches.router)
    app.include_router(predictions.router)
    app.include_router(replay.router)
    return app


app = create_app()

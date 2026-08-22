"""FastAPI application for the stock research backend.

Runs alongside the news archiver and shares its database. Routers are
registered here; keep this file to wiring only.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.db import dispose_engine


class Health(BaseModel):
    """Liveness response."""

    status: str


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build the application. Called by uvicorn and by tests."""
    settings = get_settings()
    app = FastAPI(title=settings.api_title, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=Health)
    async def health() -> Health:
        """Liveness check — does not touch the database."""
        return Health(status="ok")

    return app


app = create_app()

"""Vercel serverless ASGI handler for FastAPI app."""

import sys
from pathlib import Path

# The `archiver` package lives under ./src and is not guaranteed to be
# pip-installed inside Vercel's serverless function bundle, so make it
# importable directly. Without this, `import archiver` fails and every
# request falls into the error branch below.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI
from fastapi.responses import JSONResponse


def _to_async_url(url: str) -> str:
    """Normalize a Postgres URL to an async SQLAlchemy driver.

    Neon/Supabase/etc. hand out plain ``postgresql://`` (or ``postgres://``)
    URLs. SQLAlchemy's async engine requires an explicit async driver, so
    upgrade the scheme to ``postgresql+psycopg://`` (psycopg 3, which is in
    requirements.txt). SQLite and already-qualified URLs are left untouched.
    """
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://", "sqlite"):
        if url.startswith(prefix):
            return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


# Create app first with basic error handling
app = FastAPI(title="Trump News Archive")


@app.get("/health")
async def health():
    """Health check - doesn't require database."""
    return {"status": "ok"}


# Try to set up the real app, but don't crash if it fails
try:
    from archiver.config.settings import Settings
    from archiver.storage.db import Database
    from archiver.web.app import create_app
    
    # Load settings from environment variables
    settings = Settings()
    
    # Initialize the database from settings (normalizing the driver so a plain
    # Neon/Supabase postgresql:// URL works with the async engine).
    db = Database(_to_async_url(settings.database_url))
    
    # Create the real FastAPI application
    real_app = create_app(db)
    
    # Mount the real app to replace the health-check-only app
    app.mount("", real_app)
    
except Exception as e:
    print(f"ERROR initializing app: {e}")
    import traceback
    traceback.print_exc()
    
    # Keep the basic app with error info
    @app.get("/")
    async def error_page():
        return JSONResponse(
            status_code=500,
            content={
                "error": "Application initialization failed",
                "message": str(e),
                "hint": "Check that DATABASE_URL environment variable is set correctly",
            },
        )


# Export for Vercel's ASGI handler
__all__ = ["app"]

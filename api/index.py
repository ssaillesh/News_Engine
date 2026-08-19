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
    
    # Database() normalizes the driver, so a plain Neon/Supabase
    # postgresql:// URL works with the async engine as-is.
    db = Database(settings.database_url)
    
    # Create the real FastAPI application
    real_app = create_app(db)
    
    # Mount the real app to replace the health-check-only app
    app.mount("", real_app)
    
except Exception as exc:
    import traceback

    # Bind the text now: Python unbinds the `except ... as` name when the block
    # exits, so a closure that reads it would raise NameError at request time —
    # turning a readable config error into an opaque 500.
    _init_error = f"{type(exc).__name__}: {exc}"
    print(f"ERROR initializing app: {_init_error}")
    traceback.print_exc()

    # Keep the basic app with error info
    @app.get("/")
    async def error_page():
        return JSONResponse(
            status_code=500,
            content={
                "error": "Application initialization failed",
                "message": _init_error,
                "hint": "Check that DATABASE_URL environment variable is set correctly",
            },
        )


# Export for Vercel's ASGI handler
__all__ = ["app"]

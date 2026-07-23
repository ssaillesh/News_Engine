"""Vercel serverless ASGI handler for FastAPI app."""

import sys
from pathlib import Path

# Add src to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from archiver.config.settings import Settings
from archiver.storage.db import Database
from archiver.web.app import create_app


# Load settings from environment
settings = Settings()

# Initialize the database from settings
db = Database(settings.database_url)

# Create the FastAPI application
app = create_app(db)

# Export for Vercel's ASGI handler
__all__ = ["app"]

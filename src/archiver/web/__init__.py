"""Read-only web UI for browsing the archive (DESIGN.md §15).

A small FastAPI app that serves a dashboard plus a JSON API over the archive DB.
Read-only: it never writes. Launch with ``archiver serve``.
"""

from archiver.web.app import create_app, find_free_port

__all__ = ["create_app", "find_free_port"]

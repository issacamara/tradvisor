"""FastAPI application entry point for the packaged API runtime."""

from __future__ import annotations

from backend.app import create_app


app = create_app()

"""Compatibility ASGI entrypoint for the hardened Puchoo.si application."""

from backend.main import app, create_app

__all__ = ["app", "create_app"]

"""``uvicorn faceattend.main:app`` entry point (reads settings from the environment)."""

from .app import create_app

app = create_app()

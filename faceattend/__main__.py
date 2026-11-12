"""``python -m faceattend``: start the server."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from .app import create_app
from .config import Settings
from .faces import load_engine
from .models import ModelsMissingError


def main() -> int:
    parser = argparse.ArgumentParser(prog="faceattend", description="Run the FaceAttend server.")
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to allow other devices")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    settings = Settings.from_env()
    try:
        engine = load_engine(settings.models_dir, settings.detect_threshold)
    except ModelsMissingError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not settings.admin_token and args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "WARNING: the server is reachable from other devices and ATTENDANCE_ADMIN_TOKEN is "
            "not set, so anyone can register or delete people.",
            file=sys.stderr,
        )
    uvicorn.run(create_app(settings, engine=engine), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

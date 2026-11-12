"""Runtime settings. Everything can be overridden with ``ATTENDANCE_*`` environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PREFIX = "ATTENDANCE_"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = PROJECT_ROOT / "data"
    models_dir: Path = PROJECT_ROOT / "models"

    #: Minimum cosine similarity for two faces to count as the same person.
    #: The SFace authors suggest 0.363; a stricter default suits attendance, where a wrong
    #: match is worse than asking someone to look at the camera again.
    match_threshold: float = 0.40
    #: Minimum detector confidence for a face to be considered at all.
    detect_threshold: float = 0.85
    #: Smallest face (in pixels, after downscaling) accepted at registration.
    min_face_px: int = 80

    #: A person must be recognised this many times within ``confirm_window_s`` before
    #: attendance is recorded, so one bad frame can never mark the wrong person.
    confirm_hits: int = 2
    confirm_window_s: float = 6.0

    #: If set, registering, deleting, listing and exporting require this token.
    admin_token: str | None = None

    max_upload_bytes: int = 2_000_000
    max_image_side: int = 640
    min_register_frames: int = 3
    max_register_frames: int = 10
    max_faces_per_frame: int = 8

    @property
    def db_path(self) -> Path:
        return self.data_dir / "attendance.db"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        defaults = cls()

        def read(name: str, default, cast=str):
            raw = env.get(ENV_PREFIX + name)
            if raw is None or raw == "":
                return default
            try:
                return cast(raw)
            except ValueError as exc:
                raise ValueError(f"{ENV_PREFIX}{name} has an invalid value: {raw!r}") from exc

        return cls(
            data_dir=read("DATA_DIR", defaults.data_dir, Path),
            models_dir=read("MODELS_DIR", defaults.models_dir, Path),
            match_threshold=read("MATCH_THRESHOLD", defaults.match_threshold, float),
            detect_threshold=read("DETECT_THRESHOLD", defaults.detect_threshold, float),
            min_face_px=read("MIN_FACE_PX", defaults.min_face_px, int),
            confirm_hits=read("CONFIRM_HITS", defaults.confirm_hits, int),
            confirm_window_s=read("CONFIRM_WINDOW_S", defaults.confirm_window_s, float),
            admin_token=read("ADMIN_TOKEN", None),
        )

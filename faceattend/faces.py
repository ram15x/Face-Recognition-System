"""Face detection and embedding with OpenCV's YuNet and SFace models."""

from __future__ import annotations

import os

# Refuse to decode absurdly large images (decompression bombs). Must be set before cv2 loads.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(25_000_000))

import threading  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Protocol  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from .models import require_models  # noqa: E402

EMBEDDING_DIM = 128


class ImageError(ValueError):
    """The uploaded bytes are not a usable image."""


@dataclass(frozen=True)
class Face:
    #: x, y, width, height in pixels of the image the face was found in.
    box: tuple[int, int, int, int]
    score: float
    #: Detector output row (box, 5 landmarks, score); SFace needs it to align the face.
    raw: np.ndarray | None = None

    @property
    def area(self) -> int:
        return self.box[2] * self.box[3]


class FaceEngine(Protocol):
    """Anything that can find faces and describe them. Tests use a stub implementation."""

    def detect(self, image: np.ndarray) -> list[Face]: ...

    def embed(self, image: np.ndarray, face: Face) -> np.ndarray:
        """Return a unit-length vector of ``EMBEDDING_DIM`` floats."""
        ...


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else vector


def decode_image(data: bytes, max_side: int) -> np.ndarray:
    """Decode JPEG/PNG bytes to a BGR array, shrinking it so its longest side is ``max_side``."""
    if not data:
        raise ImageError("The image is empty.")
    try:
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise ImageError("The image could not be decoded.") from exc
    if image is None:
        raise ImageError("That file is not a valid image.")
    height, width = image.shape[:2]
    scale = max_side / max(height, width)
    if scale < 1:
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    return image


class OpenCVFaceEngine:
    """YuNet for detection, SFace for 128-d embeddings. Safe to share between threads."""

    def __init__(self, detector_path: Path, recognizer_path: Path, score_threshold: float = 0.85):
        self._detector = cv2.FaceDetectorYN.create(
            str(detector_path), "", (320, 320), score_threshold, 0.3, 5000
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        # Both OpenCV objects keep internal state between calls.
        self._lock = threading.Lock()

    def detect(self, image: np.ndarray) -> list[Face]:
        height, width = image.shape[:2]
        with self._lock:
            self._detector.setInputSize((width, height))
            _, rows = self._detector.detect(image)
        if rows is None:
            return []
        faces = [
            Face(
                box=(int(r[0]), int(r[1]), int(r[2]), int(r[3])),
                score=float(r[14]),
                raw=r.astype(np.float32),
            )
            for r in rows
        ]
        return sorted(faces, key=lambda f: f.area, reverse=True)

    def embed(self, image: np.ndarray, face: Face) -> np.ndarray:
        if face.raw is None:
            raise ValueError("This face has no detector data to align from.")
        with self._lock:
            aligned = self._recognizer.alignCrop(image, face.raw)
            feature = self._recognizer.feature(aligned)
        return l2_normalize(feature)


def load_engine(models_dir: Path, detect_threshold: float = 0.85) -> OpenCVFaceEngine:
    detector, recognizer = require_models(models_dir)
    return OpenCVFaceEngine(detector, recognizer, detect_threshold)

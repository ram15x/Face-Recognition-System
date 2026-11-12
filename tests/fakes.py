"""A stand-in for the real face models, so the app's logic can be tested without them.

Test "photos" are tiny lossless PNGs. The first pixel row describes the faces in the picture:
column k holds one face, with the person's identity in the blue channel, the face width in the
green channel and a red marker of 255.
"""

from __future__ import annotations

import cv2
import numpy as np

from faceattend.faces import EMBEDDING_DIM, Face, l2_normalize


def make_photo(*faces: tuple[int, int] | tuple[int, int, float]) -> bytes:
    """Each face is ``(identity, width)`` or ``(identity, width, detector_score)``."""
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    for k, face in enumerate(faces):
        identity, width = face[0], face[1]
        score = face[2] if len(face) == 3 else 0.99
        image[0, k] = (identity, width, 255)
        image[1, k] = (round(score * 100), 0, 0)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


class FakeEngine:
    def __init__(self, noise: float = 0.03):
        self.noise = noise
        self._rng = np.random.default_rng(0)

    def detect(self, image: np.ndarray) -> list[Face]:
        faces = []
        for k in range(image.shape[1]):
            identity, width, marker = (int(v) for v in image[0, k])
            if marker != 255:
                continue
            score = int(image[1, k][0]) / 100
            faces.append(
                Face(
                    box=(20 + k * 70, 30, width, width),
                    score=score,
                    raw=np.array([identity], dtype=np.float32),
                )
            )
        return sorted(faces, key=lambda f: f.area, reverse=True)

    def embed(self, image: np.ndarray, face: Face) -> np.ndarray:
        identity = int(face.raw[0])
        base = np.random.default_rng(1000 + identity).normal(size=EMBEDDING_DIM)
        # Same person, slightly different photo: a little noise.
        return l2_normalize(base + self.noise * self._rng.normal(size=EMBEDDING_DIM))

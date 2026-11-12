"""Checks the real YuNet + SFace models. Skipped until ``python -m faceattend.models`` has run."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from faceattend.config import Settings
from faceattend.db import Store
from faceattend.faces import EMBEDDING_DIM, load_engine
from faceattend.models import ModelsMissingError
from faceattend.service import AttendanceService, ServiceError

SETTINGS = Settings.from_env()


@pytest.fixture(scope="module")
def engine():
    try:
        return load_engine(SETTINGS.models_dir, SETTINGS.detect_threshold)
    except ModelsMissingError:
        pytest.skip("models not downloaded; run: python -m faceattend.models")


@pytest.fixture(scope="module")
def photo():
    """One well-known sample portrait that ships with scikit-image."""
    data = pytest.importorskip("skimage.data")
    bgr = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
    # Upscale so the face is about as large as it would be in a webcam frame.
    return cv2.resize(bgr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def one_face(engine, image):
    faces = [f for f in engine.detect(image) if f.score >= SETTINGS.detect_threshold]
    assert len(faces) == 1, f"expected one face, found {len(faces)}"
    return faces[0]


def rotate(image, degrees):
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)


def jpeg(image, quality):
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def variants(image):
    return {
        "darker": cv2.convertScaleAbs(image, alpha=0.65, beta=0),
        "brighter": cv2.convertScaleAbs(image, alpha=1.3, beta=10),
        "blurred": cv2.GaussianBlur(image, (7, 7), 0),
        "jpeg-low-quality": jpeg(image, 30),
        "rotated-left": rotate(image, 8),
        "rotated-right": rotate(image, -8),
        "smaller": cv2.resize(image, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA),
    }


def test_a_blank_image_has_no_faces(engine):
    assert engine.detect(np.full((480, 640, 3), 127, dtype=np.uint8)) == []


def test_embedding_is_a_unit_vector(engine, photo):
    embedding = engine.embed(photo, one_face(engine, photo))
    assert embedding.shape == (EMBEDDING_DIM,)
    assert float(np.linalg.norm(embedding)) == pytest.approx(1.0, abs=1e-4)


def test_the_same_face_still_matches_after_ordinary_changes(engine, photo):
    reference = engine.embed(photo, one_face(engine, photo))
    scores = {}
    for name, changed in variants(photo).items():
        scores[name] = float(reference @ engine.embed(changed, one_face(engine, changed)))
    print("similarity scores:", {k: round(v, 3) for k, v in scores.items()})
    too_low = {k: round(v, 3) for k, v in scores.items() if v < SETTINGS.match_threshold}
    assert not too_low, f"below the {SETTINGS.match_threshold} threshold: {too_low}"


def test_unrelated_noise_is_not_a_match(engine, photo):
    reference = engine.embed(photo, one_face(engine, photo))
    rng = np.random.default_rng(3)
    for _ in range(20):
        noise = rng.normal(size=EMBEDDING_DIM)
        assert float(reference @ (noise / np.linalg.norm(noise))) < SETTINGS.match_threshold


def test_register_then_recognise_with_the_real_models(engine, photo, tmp_path):
    service = AttendanceService(SETTINGS, Store(tmp_path / "real.db"), engine)
    shots = [photo, variants(photo)["darker"], variants(photo)["rotated-left"]]
    person = service.register("Sample Person", "S1", True, shots)
    assert person.samples == 3

    # The same face cannot be registered again under another name.
    with pytest.raises(ServiceError) as error:
        service.register("Someone Else", "S2", True, shots)
    assert error.value.status_code == 409

    first = service.recognize(variants(photo)["brighter"])
    assert [f.status for f in first.faces] == ["confirming"]
    second = service.recognize(variants(photo)["jpeg-low-quality"])
    assert [(f.status, f.name) for f in second.faces] == [("marked", "Sample Person")]

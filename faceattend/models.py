"""The two ONNX models FaceAttend uses, and a small downloader for them.

Both come from the OpenCV Zoo (https://github.com/opencv/opencv_zoo):
YuNet finds faces, SFace turns a face into a 128-number embedding.

Run ``python -m faceattend.models`` once to fetch them.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

_GITHUB = "https://github.com/opencv/opencv_zoo/raw/main/models/"
_HUGGING_FACE = "https://huggingface.co/opencv/"


class ModelsMissingError(RuntimeError):
    """The model files have not been downloaded yet."""


class ModelDownloadError(RuntimeError):
    """Every download source failed."""


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    urls: tuple[str, ...]
    #: Sanity bounds. They catch error pages and Git LFS pointer files saved as a model.
    min_bytes: int
    max_bytes: int


DETECTOR = ModelSpec(
    "face_detection_yunet_2023mar.onnx",
    (
        f"{_GITHUB}face_detection_yunet/face_detection_yunet_2023mar.onnx",
        f"{_HUGGING_FACE}face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    ),
    min_bytes=50_000,
    max_bytes=5_000_000,
)
RECOGNIZER = ModelSpec(
    "face_recognition_sface_2021dec.onnx",
    (
        f"{_GITHUB}face_recognition_sface/face_recognition_sface_2021dec.onnx",
        f"{_HUGGING_FACE}face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
    ),
    min_bytes=10_000_000,
    max_bytes=100_000_000,
)
ALL_MODELS = (DETECTOR, RECOGNIZER)


def model_path(models_dir: Path, spec: ModelSpec) -> Path:
    return models_dir / spec.filename


def missing_models(models_dir: Path) -> list[ModelSpec]:
    return [spec for spec in ALL_MODELS if not model_path(models_dir, spec).is_file()]


def require_models(models_dir: Path) -> tuple[Path, Path]:
    """Return (detector, recognizer) paths, or explain how to get them."""
    missing = missing_models(models_dir)
    if missing:
        names = ", ".join(spec.filename for spec in missing)
        raise ModelsMissingError(
            f"Model file(s) not found in {models_dir}: {names}\n"
            "Download them once with:  python -m faceattend.models"
        )
    return model_path(models_dir, DETECTOR), model_path(models_dir, RECOGNIZER)


def _fetch(spec: ModelSpec, destination: Path) -> str:
    errors: list[str] = []
    for url in spec.urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "faceattend"})
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                data = response.read()
        except (OSError, urllib.error.URLError) as exc:
            errors.append(f"{url}: {exc}")
            continue
        if not spec.min_bytes <= len(data) <= spec.max_bytes:
            errors.append(f"{url}: unexpected size ({len(data)} bytes)")
            continue
        partial = destination.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(destination)
        return hashlib.sha256(data).hexdigest()
    raise ModelDownloadError(
        f"Could not download {spec.filename}.\n  " + "\n  ".join(errors) + "\n"
        "You can download it manually and place it in the models folder."
    )


def download_models(models_dir: Path, *, force: bool = False) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    for spec in ALL_MODELS:
        destination = model_path(models_dir, spec)
        if destination.is_file() and not force:
            print(f"ok       {spec.filename}")
            continue
        print(f"fetching {spec.filename} ...", flush=True)
        digest = _fetch(spec, destination)
        print(f"saved    {destination}  (sha256 {digest[:16]}...)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the FaceAttend model files.")
    parser.add_argument("--dir", type=Path, help="target folder (default: ./models)")
    parser.add_argument("--force", action="store_true", help="download again even if present")
    args = parser.parse_args()
    models_dir = args.dir or Settings.from_env().models_dir
    try:
        download_models(models_dir, force=args.force)
    except ModelDownloadError as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

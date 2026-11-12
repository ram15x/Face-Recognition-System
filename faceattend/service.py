"""The rules of the system: who may register, who gets marked present, and when."""

from __future__ import annotations

import re
import threading
from collections import Counter, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import numpy as np

from .config import Settings
from .db import DuplicateCodeError, Person, Store
from .faces import Face, FaceEngine
from .matching import Gallery, best_match

Clock = Callable[[], datetime]
Status = Literal["marked", "already", "confirming", "unknown"]

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


class ServiceError(Exception):
    """A problem the caller can fix. ``status_code`` maps straight onto an HTTP status."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class FaceResult:
    box: tuple[int, int, int, int]
    status: Status
    score: float
    name: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class RecognizeResult:
    width: int
    height: int
    faces: list[FaceResult]


def default_clock() -> datetime:
    return datetime.now().astimezone()


def clean_name(value: str) -> str:
    name = " ".join(value.split())
    if not 1 <= len(name) <= 80 or any(ord(ch) < 32 for ch in name):
        raise ServiceError(422, "Name must be 1 to 80 characters.")
    return name


def clean_code(value: str) -> str:
    code = value.strip()
    if not _CODE_RE.match(code):
        raise ServiceError(
            422, "ID must be 1 to 32 characters: letters, numbers, dot, dash or underscore."
        )
    return code


class AttendanceService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        engine: FaceEngine,
        clock: Clock = default_clock,
    ):
        self.settings = settings
        self.store = store
        self.engine = engine
        self.clock = clock
        self._lock = threading.Lock()
        self._cache: tuple[Gallery, dict[int, Person]] | None = None
        self._hits: dict[int, deque[datetime]] = {}
        self._marked: set[tuple[str, int]] = set()

    # ---- cache -----------------------------------------------------------------------------

    def _snapshot(self) -> tuple[Gallery, dict[int, Person]]:
        with self._lock:
            if self._cache is None:
                people = {p.id: p for p in self.store.list_persons()}
                self._cache = (self.store.load_gallery(), people)
            return self._cache

    def _invalidate(self) -> None:
        with self._lock:
            self._cache = None

    # ---- registration ----------------------------------------------------------------------

    def register(self, name: str, code: str, consent: bool, images: Sequence[np.ndarray]) -> Person:
        s = self.settings
        if not consent:
            raise ServiceError(422, "The person must consent to their face being stored.")
        name, code = clean_name(name), clean_code(code)
        if not s.min_register_frames <= len(images) <= s.max_register_frames:
            raise ServiceError(
                422,
                f"Send between {s.min_register_frames} and {s.max_register_frames} photos.",
            )

        vectors: list[np.ndarray] = []
        problems: Counter[str] = Counter()
        for image in images:
            faces = [f for f in self.engine.detect(image) if f.score >= s.detect_threshold]
            if not faces:
                problems["no face found"] += 1
            elif len(faces) > 1:
                problems["more than one face"] += 1
            elif faces[0].box[2] < s.min_face_px:
                problems["face too small, move closer"] += 1
            else:
                vectors.append(self.engine.embed(image, faces[0]))

        if len(vectors) < s.min_register_frames:
            why = ", ".join(f"{n} x {reason}" for reason, n in problems.most_common())
            raise ServiceError(
                422,
                f"Only {len(vectors)} of {len(images)} photos were usable"
                f"{f' ({why})' if why else ''}. Need at least {s.min_register_frames}.",
            )

        # Refuse to register the same face twice under a different name.
        gallery, people = self._snapshot()
        for vector in vectors:
            match = best_match(vector, gallery, s.match_threshold)
            if match.person_id is not None:
                other = people[match.person_id]
                raise ServiceError(
                    409, f"This face already looks registered ({other.name}, ID {other.code})."
                )

        try:
            person = self.store.add_person(
                name, code, vectors, self.clock().isoformat(timespec="seconds")
            )
        except DuplicateCodeError:
            raise ServiceError(409, f"ID {code} is already in use.") from None
        self._invalidate()
        return person

    def delete_person(self, person_id: int) -> None:
        if not self.store.delete_person(person_id):
            raise ServiceError(404, "No such person.")
        with self._lock:
            self._hits.pop(person_id, None)
            self._marked = {(d, p) for d, p in self._marked if p != person_id}
        self._invalidate()

    # ---- recognition -----------------------------------------------------------------------

    def recognize(self, image: np.ndarray) -> RecognizeResult:
        s = self.settings
        now = self.clock()
        day = now.date().isoformat()
        height, width = image.shape[:2]

        faces: list[Face] = [f for f in self.engine.detect(image) if f.score >= s.detect_threshold][
            : s.max_faces_per_frame
        ]
        gallery, people = self._snapshot()

        results: list[FaceResult] = []
        counted: set[int] = set()
        for face in faces:
            embedding = self.engine.embed(image, face)
            match = best_match(embedding, gallery, s.match_threshold)
            if match.person_id is None:
                results.append(FaceResult(face.box, "unknown", match.score))
                continue
            person = people[match.person_id]
            status = self._status_for(person.id, match.score, now, day, counted)
            results.append(FaceResult(face.box, status, match.score, person.name, person.code))
        return RecognizeResult(width, height, results)

    def _status_for(
        self, person_id: int, score: float, now: datetime, day: str, counted: set[int]
    ) -> Status:
        if (day, person_id) in self._marked:
            return "already"
        if not self._confirmed(person_id, now, counted):
            return "confirming"
        created = self.store.mark_attendance(
            person_id, day, now.isoformat(timespec="seconds"), score
        )
        with self._lock:
            self._marked.add((day, person_id))
        return "marked" if created else "already"

    def _confirmed(self, person_id: int, now: datetime, counted: set[int]) -> bool:
        needed = self.settings.confirm_hits
        if needed <= 1:
            return True
        with self._lock:
            hits = self._hits.setdefault(person_id, deque())
            # The same person twice in one frame still counts as a single sighting.
            if person_id not in counted:
                counted.add(person_id)
                hits.append(now)
            cutoff = now - timedelta(seconds=self.settings.confirm_window_s)
            while hits and hits[0] < cutoff:
                hits.popleft()
            return len(hits) >= needed

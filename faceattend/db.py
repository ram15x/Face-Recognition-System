"""SQLite storage. Only face embeddings are stored, never photos."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .faces import EMBEDDING_DIM
from .matching import Gallery

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    code       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    vector    BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_embeddings_person ON embeddings(person_id);
CREATE TABLE IF NOT EXISTS attendance (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    day       TEXT NOT NULL,
    marked_at TEXT NOT NULL,
    score     REAL NOT NULL,
    UNIQUE (person_id, day)
);
CREATE INDEX IF NOT EXISTS idx_attendance_day ON attendance(day);
"""


class DuplicateCodeError(Exception):
    """A person with this ID already exists."""


@dataclass(frozen=True)
class Person:
    id: int
    name: str
    code: str
    created_at: str
    samples: int = 0


@dataclass(frozen=True)
class AttendanceRow:
    day: str
    person_id: int
    name: str
    code: str
    marked_at: str
    score: float


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA journal_mode = WAL")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- people ----------------------------------------------------------------------------

    def add_person(
        self, name: str, code: str, vectors: Sequence[np.ndarray], created_at: str
    ) -> Person:
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO persons (name, code, created_at) VALUES (?, ?, ?)",
                    (name, code, created_at),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateCodeError(code) from exc
            person_id = int(cursor.lastrowid or 0)
            conn.executemany(
                "INSERT INTO embeddings (person_id, vector) VALUES (?, ?)",
                [(person_id, np.asarray(v, dtype=np.float32).tobytes()) for v in vectors],
            )
        return Person(person_id, name, code, created_at, samples=len(vectors))

    def list_persons(self) -> list[Person]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT p.id, p.name, p.code, p.created_at, COUNT(e.id) AS samples
                   FROM persons p LEFT JOIN embeddings e ON e.person_id = p.id
                   GROUP BY p.id ORDER BY LOWER(p.name), p.id"""
            ).fetchall()
        return [Person(r["id"], r["name"], r["code"], r["created_at"], r["samples"]) for r in rows]

    def delete_person(self, person_id: int) -> bool:
        """Remove a person together with their embeddings and attendance history."""
        with self._connect() as conn:
            return conn.execute("DELETE FROM persons WHERE id = ?", (person_id,)).rowcount > 0

    def load_gallery(self) -> Gallery:
        with self._connect() as conn:
            rows = conn.execute("SELECT person_id, vector FROM embeddings").fetchall()
        if not rows:
            return Gallery.empty()
        ids = np.array([r["person_id"] for r in rows], dtype=np.int64)
        vectors = np.stack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])
        if vectors.shape[1] != EMBEDDING_DIM:
            raise RuntimeError("Stored embeddings do not match the current model.")
        return Gallery(ids, vectors)

    # ---- attendance ------------------------------------------------------------------------

    def mark_attendance(self, person_id: int, day: str, marked_at: str, score: float) -> bool:
        """Record attendance once per person per day. Returns False if already recorded."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO attendance (person_id, day, marked_at, score)"
                " VALUES (?, ?, ?, ?)",
                (person_id, day, marked_at, score),
            )
            return cursor.rowcount == 1

    def attendance_between(self, start: str, end: str) -> list[AttendanceRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT a.day, a.person_id, p.name, p.code, a.marked_at, a.score
                   FROM attendance a JOIN persons p ON p.id = a.person_id
                   WHERE a.day BETWEEN ? AND ?
                   ORDER BY a.day, a.marked_at""",
                (start, end),
            ).fetchall()
        return [
            AttendanceRow(
                r["day"], r["person_id"], r["name"], r["code"], r["marked_at"], r["score"]
            )
            for r in rows
        ]

    def daily_counts(self, start: str, end: str) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT day, COUNT(*) AS n FROM attendance WHERE day BETWEEN ? AND ? GROUP BY day",
                (start, end),
            ).fetchall()
        return {r["day"]: r["n"] for r in rows}

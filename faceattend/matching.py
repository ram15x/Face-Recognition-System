"""Matching a face against everyone who is registered."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .faces import EMBEDDING_DIM


@dataclass(frozen=True)
class Gallery:
    """Every stored embedding, one row each, with the person each row belongs to."""

    person_ids: np.ndarray  # shape (N,)
    vectors: np.ndarray  # shape (N, EMBEDDING_DIM), unit length

    @classmethod
    def empty(cls) -> Gallery:
        return cls(np.empty(0, dtype=np.int64), np.empty((0, EMBEDDING_DIM), dtype=np.float32))

    def __len__(self) -> int:
        return int(self.person_ids.shape[0])


@dataclass(frozen=True)
class Match:
    #: ``None`` means nobody was similar enough: the face is unknown.
    person_id: int | None
    #: Cosine similarity of the closest stored face, reported even when it is not enough.
    score: float


def best_match(query: np.ndarray, gallery: Gallery, threshold: float) -> Match:
    """Find the closest registered face. Unknown faces are rejected, never forced to a name.

    A person has several stored embeddings, and the best of them counts, so a registration
    photo taken from a slightly different angle still helps.
    """
    if len(gallery) == 0:
        return Match(None, 0.0)
    similarities = gallery.vectors @ query
    best = int(np.argmax(similarities))
    score = float(similarities[best])
    if score >= threshold:
        return Match(int(gallery.person_ids[best]), score)
    return Match(None, score)

import numpy as np
import pytest

from faceattend.db import DuplicateCodeError, Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def vec(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=128).astype(np.float32)
    return v / np.linalg.norm(v)


def test_add_and_list_people(store):
    store.add_person("Zoya", "B2", [vec(1), vec(2)], "2026-01-01T09:00:00+00:00")
    store.add_person("Asha", "A1", [vec(3)], "2026-01-01T09:00:00+00:00")
    people = store.list_persons()
    assert [(p.name, p.samples) for p in people] == [("Asha", 1), ("Zoya", 2)]


def test_ids_are_unique_ignoring_case(store):
    store.add_person("Asha", "emp-1", [vec(1)], "t")
    with pytest.raises(DuplicateCodeError):
        store.add_person("Someone else", "EMP-1", [vec(2)], "t")


def test_embeddings_survive_a_round_trip(store):
    original = vec(5)
    person = store.add_person("Asha", "A1", [original], "t")
    gallery = store.load_gallery()
    assert list(gallery.person_ids) == [person.id]
    assert np.allclose(gallery.vectors[0], original)


def test_attendance_is_recorded_once_per_day(store):
    person = store.add_person("Asha", "A1", [vec(1)], "t")
    assert store.mark_attendance(person.id, "2026-03-01", "2026-03-01T09:00:00+00:00", 0.7)
    assert not store.mark_attendance(person.id, "2026-03-01", "2026-03-01T17:00:00+00:00", 0.9)
    assert store.mark_attendance(person.id, "2026-03-02", "2026-03-02T09:00:00+00:00", 0.7)
    rows = store.attendance_between("2026-03-01", "2026-03-02")
    assert [r.marked_at[11:19] for r in rows] == ["09:00:00", "09:00:00"]
    assert store.daily_counts("2026-03-01", "2026-03-31") == {"2026-03-01": 1, "2026-03-02": 1}


def test_deleting_a_person_removes_their_embeddings_and_history(store):
    keep = store.add_person("Keep", "K", [vec(1)], "t")
    gone = store.add_person("Gone", "G", [vec(2), vec(3)], "t")
    store.mark_attendance(gone.id, "2026-03-01", "2026-03-01T09:00:00+00:00", 0.7)
    assert store.delete_person(gone.id)
    assert not store.delete_person(gone.id)
    assert list(store.load_gallery().person_ids) == [keep.id]
    assert store.attendance_between("2026-03-01", "2026-03-01") == []

import numpy as np

from faceattend.matching import Gallery, best_match


def unit(*values: float) -> np.ndarray:
    v = np.array(values + (0.0,) * (128 - len(values)), dtype=np.float32)
    return v / np.linalg.norm(v)


def gallery(*rows: tuple[int, np.ndarray]) -> Gallery:
    return Gallery(np.array([r[0] for r in rows], dtype=np.int64), np.stack([r[1] for r in rows]))


def test_empty_gallery_never_matches():
    assert best_match(unit(1), Gallery.empty(), 0.4).person_id is None


def test_identical_face_matches_with_score_one():
    match = best_match(unit(1, 0), gallery((7, unit(1, 0))), 0.4)
    assert match.person_id == 7
    assert match.score > 0.999


def test_unrelated_face_is_unknown_instead_of_forced_to_a_name():
    match = best_match(unit(0, 1), gallery((7, unit(1, 0))), 0.4)
    assert match.person_id is None
    assert match.score < 0.01


def test_threshold_is_inclusive():
    query = unit(1, 1)
    stored = unit(1, 0)
    score = float(query @ stored)
    assert best_match(query, gallery((1, stored)), score).person_id == 1
    assert best_match(query, gallery((1, stored)), score + 1e-4).person_id is None


def test_any_of_a_persons_samples_can_match():
    people = gallery((1, unit(1, 0)), (1, unit(0, 1)), (2, unit(1, 1)))
    assert best_match(unit(0, 1), people, 0.9).person_id == 1


def test_closest_person_wins():
    people = gallery((1, unit(1, 0.4)), (2, unit(1, 0.05)))
    assert best_match(unit(1, 0), people, 0.4).person_id == 2

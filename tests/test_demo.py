from faceattend.db import Store
from faceattend.demo import PEOPLE, seed


def test_demo_data_is_created(tmp_path):
    store = Store(tmp_path / "demo.db")
    seed(store)
    assert len(store.list_persons()) == len(PEOPLE)
    assert len(store.load_gallery()) == len(PEOPLE) * 5
    counts = store.daily_counts("0000-01-01", "9999-12-31")
    assert counts and max(counts.values()) <= len(PEOPLE)

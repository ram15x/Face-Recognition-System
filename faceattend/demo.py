"""Fill a data folder with made-up people and two weeks of attendance.

For screenshots and trying out the dashboard. The stored "faces" are random numbers, so
they will never match a real person standing in front of the camera.

    ATTENDANCE_DATA_DIR=demo-data python -m faceattend.demo
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import numpy as np

from .config import Settings
from .db import Store
from .faces import EMBEDDING_DIM, l2_normalize

PEOPLE = [
    ("Aarav Mehta", "EMP-101"),
    ("Diya Nair", "EMP-102"),
    ("Kabir Singh", "EMP-103"),
    ("Meera Iyer", "EMP-104"),
    ("Rohan Das", "EMP-105"),
    ("Sana Khan", "EMP-106"),
    ("Tanvi Reddy", "EMP-107"),
    ("Vihaan Shah", "EMP-108"),
    ("Ishita Bose", "EMP-109"),
    ("Neel Joshi", "EMP-110"),
]

#: People who are always shown as not yet arrived on the current day.
ABSENT_TODAY = {"EMP-104", "EMP-108", "EMP-110"}


def seed(store: Store, days: int = 14, seed_value: int = 7) -> None:
    rng = random.Random(seed_value)
    np_rng = np.random.default_rng(seed_value)
    now = datetime.now().astimezone().replace(microsecond=0)
    people = [
        store.add_person(
            name,
            code,
            [l2_normalize(np_rng.normal(size=EMBEDDING_DIM)) for _ in range(5)],
            (now - timedelta(days=days)).isoformat(timespec="seconds"),
        )
        for name, code in PEOPLE
    ]
    for offset in range(days):
        day = (now - timedelta(days=offset)).replace(hour=9, minute=0, second=0)
        if day.weekday() >= 5:  # weekend
            continue
        for person in people:
            # Today: a few people have not arrived yet, so the Absent list has something in it.
            if offset == 0 and person.code in ABSENT_TODAY:
                continue
            if rng.random() < 0.82:
                marked = day + timedelta(minutes=rng.randint(-15, 35), seconds=rng.randint(0, 59))
                store.mark_attendance(
                    person.id,
                    marked.date().isoformat(),
                    marked.isoformat(timespec="seconds"),
                    round(rng.uniform(0.55, 0.9), 3),
                )


def main() -> None:
    settings = Settings.from_env()
    store = Store(settings.db_path)
    if store.list_persons():
        raise SystemExit(
            f"{settings.db_path} already has people; use an empty ATTENDANCE_DATA_DIR."
        )
    seed(store)
    print(f"Demo data written to {settings.db_path}")


if __name__ == "__main__":
    main()

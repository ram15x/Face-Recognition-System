from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from faceattend.app import create_app
from faceattend.config import Settings

from .fakes import FakeEngine, make_photo

IST = timezone(timedelta(hours=5, minutes=30))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 3, 2, 9, 0, 0, tzinfo=IST)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


def make_client(tmp_path, clock, **overrides):
    settings = Settings(data_dir=tmp_path, models_dir=tmp_path, **overrides)
    return TestClient(create_app(settings, engine=FakeEngine(), clock=clock))


@pytest.fixture
def client(tmp_path, clock):
    with make_client(tmp_path, clock) as c:
        yield c


def photos(identity: int, count: int = 4, width: int = 120):
    return [
        ("frames", (f"p{i}.png", make_photo((identity, width)), "image/png")) for i in range(count)
    ]


def register(client, identity=1, name="Asha Rao", code="A1", consent="true", **kwargs):
    return client.post(
        "/api/persons",
        data={"name": name, "code": code, "consent": consent},
        files=kwargs.get("files", photos(identity)),
        headers=kwargs.get("headers"),
    )


def scan(client, *faces):
    response = client.post(
        "/api/recognize", files={"frame": ("f.png", make_photo(*faces), "image/png")}
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---- basics ------------------------------------------------------------------------------------


def test_health_and_config(client):
    assert client.get("/api/health").json()["status"] == "ok"
    config = client.get("/api/config").json()
    assert config["admin_required"] is False


def test_web_ui_is_served_with_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "FaceAttend" in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


# ---- registration ------------------------------------------------------------------------------


def test_register_a_person(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["samples"] == 4
    assert [p["name"] for p in client.get("/api/persons").json()] == ["Asha Rao"]


def test_registration_needs_consent(client):
    response = register(client, consent="false")
    assert response.status_code == 422
    assert "consent" in response.json()["detail"].lower()
    assert client.get("/api/persons").json() == []


def test_same_id_cannot_be_used_twice(client):
    assert register(client, identity=1, code="A1").status_code == 201
    response = register(client, identity=2, name="Other", code="a1")
    assert response.status_code == 409
    assert "already in use" in response.json()["detail"]


def test_same_face_cannot_be_registered_under_a_second_name(client):
    assert register(client, identity=1, name="Asha", code="A1").status_code == 201
    response = register(client, identity=1, name="Asha again", code="A2")
    assert response.status_code == 409
    assert "Asha" in response.json()["detail"]


@pytest.mark.parametrize(
    ("frame_faces", "reason"),
    [
        ([], "no face found"),
        ([(1, 40)], "too small"),
        ([(1, 120), (2, 120)], "more than one face"),
        ([(1, 120, 0.5)], "no face found"),
    ],
)
def test_unusable_photos_are_rejected_with_a_reason(client, frame_faces, reason):
    files = [("frames", (f"p{i}.png", make_photo(*frame_faces), "image/png")) for i in range(4)]
    response = client.post(
        "/api/persons",
        data={"name": "Asha", "code": "A1", "consent": "true"},
        files=files,
    )
    assert response.status_code == 422
    assert reason in response.json()["detail"]


def test_too_few_photos(client):
    response = register(client, files=photos(1, count=2))
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("name", "code"),
    [("", "A1"), ("   ", "A1"), ("Asha", ""), ("Asha", "has space"), ("Asha", "../x")],
)
def test_invalid_name_or_id(client, name, code):
    assert register(client, name=name, code=code).status_code == 422


def test_garbage_upload_is_rejected(client):
    files = [("frames", (f"p{i}.png", b"not an image", "image/png")) for i in range(3)]
    response = client.post(
        "/api/persons", data={"name": "A", "code": "A1", "consent": "true"}, files=files
    )
    assert response.status_code == 422


def test_oversized_upload_is_rejected(tmp_path, clock):
    with make_client(tmp_path, clock, max_upload_bytes=100) as c:
        response = c.post(
            "/api/recognize", files={"frame": ("f.png", make_photo((1, 100)), "image/png")}
        )
    assert response.status_code == 413


# ---- recognition -------------------------------------------------------------------------------


def test_unknown_face_is_reported_and_never_marked(client):
    register(client, identity=1)
    result = scan(client, (99, 120))
    assert result["faces"][0]["status"] == "unknown"
    assert result["faces"][0]["name"] is None
    assert client.get("/api/attendance").json()["records"] == []


def test_attendance_needs_two_sightings_then_is_marked_once(client, clock):
    register(client, identity=1)
    assert scan(client, (1, 120))["faces"][0]["status"] == "confirming"
    clock.advance(seconds=1)
    first = scan(client, (1, 120))["faces"][0]
    assert first["status"] == "marked"
    assert first["name"] == "Asha Rao"
    clock.advance(seconds=1)
    assert scan(client, (1, 120))["faces"][0]["status"] == "already"
    records = client.get("/api/attendance").json()["records"]
    assert [(r["name"], r["time"]) for r in records] == [("Asha Rao", "09:00:01")]


def test_one_stray_sighting_expires_before_it_can_mark_anyone(client, clock):
    register(client, identity=1)
    assert scan(client, (1, 120))["faces"][0]["status"] == "confirming"
    clock.advance(seconds=30)
    assert scan(client, (1, 120))["faces"][0]["status"] == "confirming"
    assert client.get("/api/attendance").json()["records"] == []


def test_attendance_starts_again_the_next_day(client, clock):
    register(client, identity=1)
    scan(client, (1, 120))
    scan(client, (1, 120))
    clock.advance(days=1)
    scan(client, (1, 120))
    assert scan(client, (1, 120))["faces"][0]["status"] == "marked"
    assert client.get("/api/attendance", params={"day": "2026-03-02"}).json()["records"]
    assert client.get("/api/attendance", params={"day": "2026-03-03"}).json()["records"]


def test_several_people_in_one_frame(client):
    register(client, identity=1, name="Asha", code="A1")
    register(client, identity=2, name="Ravi", code="R1")
    scan(client, (1, 120), (2, 100), (77, 90))
    result = scan(client, (1, 120), (2, 100), (77, 90))
    statuses = {f["name"]: f["status"] for f in result["faces"]}
    assert statuses == {"Asha": "marked", "Ravi": "marked", None: "unknown"}


def test_dashboard_lists_present_and_absent(client):
    register(client, identity=1, name="Asha", code="A1")
    register(client, identity=2, name="Ravi", code="R1")
    scan(client, (1, 120))
    scan(client, (1, 120))
    data = client.get("/api/attendance").json()
    assert data["registered"] == 2
    assert [r["name"] for r in data["records"]] == ["Asha"]
    assert [a["name"] for a in data["absent"]] == ["Ravi"]


def test_deleting_a_person_forgets_their_face_and_history(client):
    person = register(client, identity=1).json()
    scan(client, (1, 120))
    scan(client, (1, 120))
    assert client.delete(f"/api/persons/{person['id']}").status_code == 204
    assert client.delete(f"/api/persons/{person['id']}").status_code == 404
    assert scan(client, (1, 120))["faces"][0]["status"] == "unknown"
    assert client.get("/api/attendance").json()["records"] == []


def test_summary(client, clock):
    register(client, identity=1)
    scan(client, (1, 120))
    scan(client, (1, 120))
    series = client.get("/api/attendance/summary", params={"days": 3}).json()["days"]
    assert [d["day"] for d in series] == ["2026-02-28", "2026-03-01", "2026-03-02"]
    assert [d["present"] for d in series] == [0, 0, 1]


# ---- export ------------------------------------------------------------------------------------


def test_csv_export_neutralises_spreadsheet_formulas(client):
    register(client, identity=1, name='=HYPERLINK("http://evil")', code="A1")
    scan(client, (1, 120))
    scan(client, (1, 120))
    response = client.get(
        "/api/attendance/export", params={"start": "2026-03-01", "end": "2026-03-02"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0] == "date,id,name,time,match_score"
    assert "'=HYPERLINK" in lines[1]
    assert not any(line.split(",")[2].startswith("=") for line in lines[1:])


@pytest.mark.parametrize(
    "params",
    [
        {"start": "nope", "end": "2026-03-02"},
        {"start": "2026-03-05", "end": "2026-03-02"},
        {"start": "2024-01-01", "end": "2026-03-02"},
    ],
)
def test_csv_export_validates_dates(client, params):
    assert client.get("/api/attendance/export", params=params).status_code == 422


# ---- admin token -------------------------------------------------------------------------------


def test_admin_token_protects_management_but_not_scanning(tmp_path, clock):
    with make_client(tmp_path, clock, admin_token="s3cret", confirm_hits=1) as c:
        assert c.get("/api/config").json()["admin_required"] is True
        for method, path in [
            ("get", "/api/persons"),
            ("get", "/api/attendance"),
            ("delete", "/api/persons/1"),
        ]:
            assert getattr(c, method)(path).status_code == 401
        assert register(c).status_code == 401
        assert register(c, headers={"X-Admin-Token": "wrong"}).status_code == 401

        good = {"X-Admin-Token": "s3cret"}
        assert register(c, headers=good).status_code == 201
        assert c.get("/api/persons", headers=good).status_code == 200
        # Scanning stays open so a kiosk can run without the token.
        assert scan(c, (1, 120))["faces"][0]["status"] == "marked"

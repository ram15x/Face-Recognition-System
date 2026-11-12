"""The HTTP API and the web UI."""

from __future__ import annotations

import csv
import io
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings
from .db import Store
from .faces import FaceEngine, ImageError, decode_image, load_engine
from .service import AttendanceService, Clock, ServiceError, default_clock

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_EXPORT_DAYS = 366

# The page only ever loads its own files and uses the camera. Nothing else is allowed.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
}


def csv_safe(value: str) -> str:
    """Stop spreadsheet apps from running a name like ``=HYPERLINK(...)`` as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def parse_day(value: str, field: str = "date") -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ServiceError(422, f"{field} must look like 2026-01-31.") from None


def create_app(
    settings: Settings | None = None,
    engine: FaceEngine | None = None,
    clock: Clock = default_clock,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        face_engine = engine or load_engine(settings.models_dir, settings.detect_threshold)
        app.state.service = AttendanceService(settings, Store(settings.db_path), face_engine, clock)
        yield

    app = FastAPI(title="FaceAttend", version=__version__, lifespan=lifespan)

    def service(request: Request) -> AttendanceService:
        return request.app.state.service

    def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
        expected = settings.admin_token
        if expected and not (
            x_admin_token and secrets.compare_digest(x_admin_token.encode(), expected.encode())
        ):
            raise ServiceError(401, "Admin token required.")

    admin = [Depends(require_admin)]

    def read_image(upload: UploadFile):
        data = upload.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise ServiceError(413, "Image is too large.")
        try:
            return decode_image(data, settings.max_image_side)
        except ImageError as exc:
            raise ServiceError(422, str(exc)) from None

    # ---- errors and headers ----------------------------------------------------------------

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---- public endpoints ------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/config")
    def public_config() -> dict:
        return {
            "version": __version__,
            "admin_required": bool(settings.admin_token),
            "min_register_frames": settings.min_register_frames,
        }

    @app.post("/api/recognize")
    def recognize(request: Request, frame: UploadFile = File(...)) -> dict:
        result = service(request).recognize(read_image(frame))
        return {
            "image": {"width": result.width, "height": result.height},
            "faces": [
                {
                    "box": list(f.box),
                    "status": f.status,
                    "name": f.name,
                    "code": f.code,
                    "score": round(f.score, 3),
                }
                for f in result.faces
            ],
        }

    # ---- admin endpoints -------------------------------------------------------------------

    @app.post("/api/persons", status_code=201, dependencies=admin)
    def register(
        request: Request,
        name: str = Form(...),
        code: str = Form(...),
        consent: bool = Form(False),
        frames: list[UploadFile] = File(...),
    ) -> dict:
        images = [read_image(f) for f in frames]
        person = service(request).register(name, code, consent, images)
        return {
            "id": person.id,
            "name": person.name,
            "code": person.code,
            "samples": person.samples,
        }

    @app.get("/api/persons", dependencies=admin)
    def list_persons(request: Request) -> list[dict]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "code": p.code,
                "samples": p.samples,
                "created_at": p.created_at,
            }
            for p in service(request).store.list_persons()
        ]

    @app.delete("/api/persons/{person_id}", status_code=204, dependencies=admin)
    def delete_person(request: Request, person_id: int) -> Response:
        service(request).delete_person(person_id)
        return Response(status_code=204)

    @app.get("/api/attendance", dependencies=admin)
    def attendance(request: Request, day: str | None = None) -> dict:
        svc = service(request)
        target = parse_day(day, "day") if day else svc.clock().date()
        iso = target.isoformat()
        records = svc.store.attendance_between(iso, iso)
        present_ids = {r.person_id for r in records}
        people = svc.store.list_persons()
        return {
            "day": iso,
            "registered": len(people),
            "records": [
                {
                    "person_id": r.person_id,
                    "name": r.name,
                    "code": r.code,
                    "time": r.marked_at[11:19],
                    "score": round(r.score, 3),
                }
                for r in records
            ],
            "absent": [
                {"person_id": p.id, "name": p.name, "code": p.code}
                for p in people
                if p.id not in present_ids
            ],
        }

    @app.get("/api/attendance/summary", dependencies=admin)
    def summary(request: Request, days: int = Query(14, ge=1, le=90)) -> dict:
        svc = service(request)
        end = svc.clock().date()
        start = end - timedelta(days=days - 1)
        counts = svc.store.daily_counts(start.isoformat(), end.isoformat())
        series = []
        for offset in range(days):
            iso = (start + timedelta(days=offset)).isoformat()
            series.append({"day": iso, "present": counts.get(iso, 0)})
        return {"registered": len(svc.store.list_persons()), "days": series}

    @app.get("/api/attendance/export", dependencies=admin)
    def export(request: Request, start: str, end: str) -> Response:
        first, last = parse_day(start, "start"), parse_day(end, "end")
        if last < first:
            raise ServiceError(422, "end must not be before start.")
        if (last - first).days >= MAX_EXPORT_DAYS:
            raise ServiceError(422, f"Export at most {MAX_EXPORT_DAYS} days at a time.")
        rows = service(request).store.attendance_between(first.isoformat(), last.isoformat())
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "id", "name", "time", "match_score"])
        for r in rows:
            time = r.marked_at[11:19]
            writer.writerow([r.day, csv_safe(r.code), csv_safe(r.name), time, r.score])
        return Response(
            buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="attendance_{start}_{end}.csv"'},
        )

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app

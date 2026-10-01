"""FastAPI app: Pipecat SmallWebRTC signalling, REST (/api), /ws, uploads, /admin."""

from __future__ import annotations

import asyncio
import io
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from PIL import Image, ImageOps
from pydantic import BaseModel
from sqlmodel import select

from kbos import db
from kbos.config import settings
from kbos.domain import people as people_d
from kbos.domain import tickets as tickets_d
from kbos.domain.checks import add_check
from kbos.domain.people import DomainError
from kbos.models import Check, GlossaryTerm, Machine, Person, Photo, ShiftSession, Ticket
from kbos.realtime import hub, iso
from kbos.seed import MACHINES, seed
from kbos.telemetry import SHIFT_S, telemetry
from kbos.voice.keypool import KeyPool
from kbos.voice.sessions import sessions

# --- shared helpers ---------------------------------------------------------------


def shift_elapsed_s() -> float:
    ist = people_d.to_ist(db.now())
    start_h = 8 if people_d.current_shift() == "day" else 20
    elapsed = (ist.hour - start_h) % 24 * 3600 + ist.minute * 60
    return min(max(elapsed, 1800), SHIFT_S)


def reset_world(wipe: bool) -> None:
    if wipe:
        db.reset_schema()
    with db.session() as s:
        empty = s.exec(select(Person)).first() is None
    targets = {code: t for code, _, _, t, _ in MACHINES}
    telemetry.reset(targets, shift_elapsed_s())
    if empty:
        with db.session() as s:
            seed(s)
        logger.info("seeded demo data")


def broadcast_ticket(type_: str, key: str, extra: dict | None = None) -> dict:
    with db.session() as s:
        d = tickets_d.ticket_summary(s, tickets_d.get_ticket(s, key))
    hub.publish(type_, {"ticket": d, **(extra or {})})
    return d


def to_http(e: DomainError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


# --- request bodies ---------------------------------------------------------------


class StartShiftBody(BaseModel):
    person_id: int


class EndShiftBody(BaseModel):
    summary: str = ""


class CheckBody(BaseModel):
    what_checked: str
    what_found: str
    new_status: str | None = None
    next_check_minutes: int | None = None
    unclear: bool = False


class PatchTicketBody(BaseModel):
    title: str | None = None
    description: str | None = None
    severity: str | None = None
    assignee_ids: list[int] | None = None
    status: str | None = None
    check: CheckBody | None = None


class GlossaryBody(BaseModel):
    terms: list[dict[str, str]]


class InjectBody(BaseModel):
    machine_code: str
    kind: str = "vibration"


class ClearBody(BaseModel):
    machine_code: str


# --- app ----------------------------------------------------------------------------


def create_app(db_path: Path | str | None = None, *, probe_keys: bool = True) -> FastAPI:
    db.init_engine(db_path or settings.db_path)
    pool = KeyPool(settings.sarvam_keys)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    async def telemetry_loop() -> None:
        while True:
            await asyncio.sleep(1)
            telemetry.tick()
            hub.publish("telemetry", telemetry.compact())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.attach_loop()
        tasks = [asyncio.create_task(hub.run()), asyncio.create_task(telemetry_loop())]
        if probe_keys:
            tasks.append(asyncio.create_task(pool.probe()))
        yield
        for t in tasks:
            t.cancel()
        await sessions.close()

    reset_world(wipe=False)
    app = FastAPI(title="KBOS", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.pool = pool
    sessions.pool = pool

    # ---- voice signalling (shapes match the RN SmallWebRTC transport) ----
    @app.post("/start")
    async def start(request: Request) -> dict[str, Any]:
        data = await request.json()
        return {"sessionId": sessions.register(data.get("body") or {})}

    @app.api_route("/sessions/{session_id}/api/offer", methods=["POST", "PATCH"])
    async def offer(session_id: str, request: Request, background_tasks: BackgroundTasks):
        data = await request.json()
        if request.method == "PATCH":
            await sessions.patch(data)
            return {"status": "success"}
        answer = await sessions.offer(session_id, data, background_tasks)
        if answer is None:
            return Response("unknown session", status_code=404)
        return answer

    # ---- REST ----
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        with db.session() as s:
            n = len(s.exec(select(Ticket.id)).all())
        return {
            "ok": True,
            "uptime_s": round(time.time() - started),
            "db": {"tickets": n},
            "keys": pool.public_status(),
            "providers": {"llm": settings.llm_provider, "tts": settings.tts_provider, "tts_voice": settings.tts_voice,
                          "stt": f"{settings.stt_model} {settings.stt_mode} {settings.stt_language}"},
            "sessions": sessions.public(),
            "ws_clients": hub.client_count,
            "latency": sessions.latency_log[-10:],
            "shift_now": people_d.current_shift(),
        }  # fmt: skip

    @app.get("/api/people")
    async def list_people(all: int = 0) -> list[dict]:
        with db.session() as s:
            return people_d.list_people(s, include_admin=bool(all))

    @app.post("/api/shifts/start")
    async def start_shift(body: StartShiftBody) -> dict:
        with db.session() as s:
            try:
                ss = people_d.start_shift(s, body.person_id)
            except DomainError as e:
                raise to_http(e) from e
            p = s.get(Person, ss.person_id)
            out = {"shift_session": people_d.shift_dict(ss, p), "person": people_d.person_dict(p)}
        hub.publish("shift.started", out)
        return out

    @app.post("/api/shifts/{shift_id}/end")
    async def end_shift(shift_id: int, body: EndShiftBody) -> dict:
        with db.session() as s:
            try:
                ss = people_d.end_shift(s, shift_id, body.summary)
            except DomainError as e:
                raise to_http(e) from e
            out = {"shift_session": people_d.shift_dict(ss, s.get(Person, ss.person_id))}
        hub.publish("shift.ended", out)
        return out

    @app.get("/api/shifts")
    async def list_shifts(limit: int = 30) -> list[dict]:
        with db.session() as s:
            rows = s.exec(select(ShiftSession).order_by(ShiftSession.started_at.desc()).limit(limit)).all()
            return [people_d.shift_dict(r, s.get(Person, r.person_id)) for r in rows]

    @app.get("/api/tickets")
    async def list_tickets(
        status: str | None = None, machine: str | None = None, assignee: int | None = None,
        q: str | None = None, since: str | None = None,
    ) -> list[dict]:  # fmt: skip
        since_dt = datetime.fromisoformat(since) if since else None
        with db.session() as s:
            return tickets_d.list_tickets(s, status, machine, assignee, q, since_dt)

    @app.get("/api/tickets/{key}")
    async def get_ticket(key: str) -> dict:
        with db.session() as s:
            try:
                return tickets_d.ticket_detail(s, tickets_d.get_ticket(s, key))
            except DomainError as e:
                raise HTTPException(404, str(e)) from e

    @app.patch("/api/tickets/{key}")
    async def patch_ticket(key: str, body: PatchTicketBody) -> dict:
        with db.session() as s:
            try:
                t = tickets_d.get_ticket(s, key)
                if body.status and body.status != t.status:
                    if not body.check:
                        raise DomainError("a status change needs a check: what was checked and what was found")
                    _, c = add_check(s, t.key, None, body.check.what_checked, body.check.what_found,
                                     new_status=body.status, next_check_minutes=body.check.next_check_minutes,
                                     unclear=body.check.unclear)  # fmt: skip
                    hub.publish("check.added", {"ticket_key": t.key, "check": tickets_d.check_dict(s, c)})
                tickets_d.update_ticket(s, t.key, title=body.title, description=body.description, severity=body.severity)
                if body.assignee_ids is not None:
                    tickets_d.set_assignees(s, t, body.assignee_ids)
                key = t.key
            except DomainError as e:
                raise to_http(e) from e
        d = broadcast_ticket("ticket.updated", key, {"by": "admin"})
        return d

    @app.post("/api/tickets/{key}/checks")
    async def post_check(key: str, body: CheckBody) -> dict:
        with db.session() as s:
            try:
                t, c = add_check(s, key, None, body.what_checked, body.what_found, new_status=body.new_status,
                                 next_check_minutes=body.next_check_minutes, unclear=body.unclear)  # fmt: skip
            except DomainError as e:
                raise to_http(e) from e
            check = tickets_d.check_dict(s, c)
            key = t.key
        hub.publish("check.added", {"ticket_key": key, "check": check})
        d = broadcast_ticket("ticket.updated", key, {"by": "admin"})
        return d

    @app.post("/api/uploads")
    async def upload(file: UploadFile = File(...), session_id: str = Form(""), person_id: int | None = Form(None)) -> dict:
        raw = await file.read()
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        except Exception as e:
            raise HTTPException(400, "not an image") from e
        img.thumbnail((1600, 1600))
        name = f"{uuid.uuid4().hex[:12]}.jpg"
        img.save(settings.uploads_dir / name, "JPEG", quality=85)
        with db.session() as s:
            p = Photo(session_id=session_id, path=name, uploader_id=person_id, created_at=db.now())
            s.add(p)
            s.commit()
            s.refresh(p)
            return {"photo_id": p.id, "url": f"/uploads/{name}"}

    @app.get("/api/machines")
    async def machines() -> list[dict]:
        with db.session() as s:
            rows = s.exec(select(Machine)).all()
            active = tickets_d.list_tickets(s, status="active")
        return [
            {
                "code": m.code, "name": m.name, "line": m.line, "unit": m.unit,
                "target_per_shift": m.target_per_shift,
                "telemetry": telemetry.current(m.code),
                "open_tickets": [d["key"] for d in active if d["machine_code"] == m.code],
            }
            for m in rows
        ]  # fmt: skip

    @app.get("/api/machines/{code}/telemetry")
    async def machine_telemetry(code: str, minutes: int = 30) -> list[dict]:
        if code.upper() not in telemetry.machines:
            raise HTTPException(404, "no such machine")
        return telemetry.series(code.upper(), minutes, 600)

    @app.get("/api/glossary")
    async def get_glossary() -> list[dict]:
        with db.session() as s:
            return [{"term": g.term, "meaning": g.meaning} for g in s.exec(select(GlossaryTerm)).all()]

    @app.put("/api/glossary")
    async def put_glossary(body: GlossaryBody) -> list[dict]:
        with db.session() as s:
            for g in s.exec(select(GlossaryTerm)).all():
                s.delete(g)
            s.flush()
            for row in body.terms:
                if row.get("term", "").strip():
                    s.add(GlossaryTerm(term=row["term"].strip(), meaning=row.get("meaning", "").strip()))
            s.commit()
            out = [{"term": g.term, "meaning": g.meaning} for g in s.exec(select(GlossaryTerm)).all()]
        hub.publish("glossary.updated", {"terms": out})
        return out

    @app.get("/api/metrics")
    async def metrics() -> dict:
        with db.session() as s:
            active = tickets_d.list_tickets(s, status="active")
            week = db.now() - timedelta(days=7)
            closed = s.exec(select(Ticket).where(Ticket.status == "closed", Ticket.closed_at >= week)).all()
            unclear = len(s.exec(select(Check.id).where(Check.unclear == True)).all())  # noqa: E712
        mttc = [(t.closed_at - t.created_at).total_seconds() / 3600 for t in closed if t.closed_at]
        return {
            "open": len(active),
            "critical": sum(d["severity"] == "critical" for d in active),
            "overdue_monitoring": sum(d["overdue"] for d in active),
            "unclear_checks": unclear,
            "mean_time_to_close_h": round(sum(mttc) / len(mttc), 1) if mttc else None,
            "closed_7d": len(closed),
        }

    @app.get("/api/events")
    async def events(limit: int = 50) -> list[dict]:
        from kbos.models import Event

        with db.session() as s:
            rows = s.exec(select(Event).order_by(Event.at.desc()).limit(limit)).all()
            return [{"id": e.id, "type": e.type, "at": iso(e.at), "data": e.payload} for e in rows]

    @app.post("/api/demo/inject")
    async def inject(body: InjectBody) -> dict:
        code = body.machine_code.upper()
        if code not in telemetry.machines:
            raise HTTPException(404, "no such machine")
        telemetry.inject(code, body.kind)
        hub.publish("demo.injected", {"machine_code": code, "kind": body.kind})
        return {"ok": True}

    @app.post("/api/demo/clear")
    async def clear(body: ClearBody) -> dict:
        code = body.machine_code.upper()
        if code not in telemetry.machines:
            raise HTTPException(404, "no such machine")
        telemetry.clear(code)
        hub.publish("demo.cleared", {"machine_code": code})
        return {"ok": True}

    @app.post("/api/demo/reset")
    async def demo_reset() -> dict:
        await sessions.close()
        reset_world(wipe=True)
        for f in settings.uploads_dir.glob("*.jpg"):
            f.unlink()
        hub.publish("demo.reset", {})
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await hub.serve(websocket)

    # ---- static ----
    app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")
    dash = settings.dashboard_dir

    @app.get("/admin")
    @app.get("/admin/{path:path}")
    async def admin(path: str = "") -> FileResponse:
        target = dash / path
        if path and target.is_file():
            return FileResponse(target)
        index = dash / "index.html"
        if not index.exists():
            raise HTTPException(404, "dashboard not built (cd dashboard && pnpm build)")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()

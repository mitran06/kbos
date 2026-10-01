"""Tickets: listing, detail, filing, edits, assignment. Rules live here, not in prompts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from kbos import db
from kbos.domain.people import DomainError, ist_hm, match_person, on_shift
from kbos.models import SEVERITIES, Check, Machine, Person, Photo, Ticket, TicketAssignee, TicketLink
from kbos.realtime import iso

NOT_GIVEN = "not given"
WORDS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
         "six": "6", "seven": "7", "eight": "8", "nine": "9"}  # fmt: skip


# -- keys ----------------------------------------------------------------------

def normalize_key(raw: str) -> str:
    """'KB-0141', '0141', '141', 'one four one', 'kb 141' -> 'KB-0141'."""
    text = raw.lower()
    digits = "".join(re.findall(r"\d", text))
    if not digits:
        spoken = [WORDS[w] for w in re.findall(r"[a-z]+", text) if w in WORDS]
        if len(spoken) >= 2:
            digits = "".join(spoken)
    if not digits:
        raise DomainError(f"'{raw}' is not a ticket number")
    return f"KB-{int(digits):04d}"


def next_key(s: Session) -> str:
    keys = s.exec(select(Ticket.key)).all()
    n = max((int(k.split("-")[1]) for k in keys), default=118) + 1
    return f"KB-{n:04d}"


def get_ticket(s: Session, key: str) -> Ticket:
    t = s.exec(select(Ticket).where(Ticket.key == normalize_key(key))).first()
    if not t:
        raise DomainError(f"there is no ticket {normalize_key(key)}")
    return t


# -- derived flags ---------------------------------------------------------------

def is_overdue(t: Ticket, at: datetime | None = None) -> bool:
    return t.status == "monitoring" and t.next_check_at is not None and t.next_check_at < (at or db.now())


def checks_of(s: Session, t: Ticket) -> list[Check]:
    return list(s.exec(select(Check).where(Check.ticket_id == t.id).order_by(Check.created_at)).all())


def assignees_of(s: Session, t: Ticket) -> list[Person]:
    ids = s.exec(select(TicketAssignee.person_id).where(TicketAssignee.ticket_id == t.id)).all()
    return [s.get(Person, i) for i in ids]


def links_of(s: Session, t: Ticket) -> list[Ticket]:
    ids = s.exec(select(TicketLink.related_ticket_id).where(TicketLink.ticket_id == t.id)).all()
    return [s.get(Ticket, i) for i in ids]


def mini_person(p: Person | None) -> dict | None:
    if not p:
        return None
    return {"id": p.id, "name": p.name, "initials": p.initials, "avatar_hue": p.avatar_hue, "role": p.role}


def check_dict(s: Session, c: Check) -> dict:
    author = s.get(Person, c.author_id) if c.author_id else None
    return {
        "id": c.id,
        "author": mini_person(author) or {"id": None, "name": "Admin", "initials": "AD", "avatar_hue": 0, "role": "admin"},
        "what_checked": c.what_checked,
        "what_found": c.what_found,
        "status_from": c.status_from,
        "status_to": c.status_to,
        "unclear": c.unclear,
        "next_check_at": iso(c.next_check_at),
        "created_at": iso(c.created_at),
    }


def ticket_summary(s: Session, t: Ticket) -> dict[str, Any]:
    checks = checks_of(s, t)
    machine = s.get(Machine, t.machine_code)
    reporter = s.get(Person, t.reporter_id) if t.reporter_id else None
    owner = s.get(Person, t.monitoring_owner_id) if t.monitoring_owner_id else None
    return {
        "id": t.id,
        "key": t.key,
        "title": t.title,
        "machine_code": t.machine_code,
        "machine_name": machine.name if machine else t.machine_code,
        "severity": t.severity,
        "status": t.status,
        "overdue": is_overdue(t),
        "unclear": any(c.unclear for c in checks),
        "assignees": [mini_person(p) for p in assignees_of(s, t)],
        "reporter": mini_person(reporter),
        "monitoring_owner": mini_person(owner),
        "next_check_at": iso(t.next_check_at),
        "created_at": iso(t.created_at),
        "updated_at": iso(t.updated_at),
        "closed_at": iso(t.closed_at),
        "last_check": check_dict(s, checks[-1]) if checks else None,
        "related_keys": [r.key for r in links_of(s, t)],
        "photo_count": len(s.exec(select(Photo.id).where(Photo.ticket_id == t.id)).all()),
    }


def ticket_detail(s: Session, t: Ticket) -> dict[str, Any]:
    d = ticket_summary(s, t)
    photos = s.exec(select(Photo).where(Photo.ticket_id == t.id).order_by(Photo.created_at)).all()
    d.update(
        description=t.description,
        symptom=t.symptom,
        since_text=t.since_text,
        context=t.context,
        machine_running=t.machine_running,
        telemetry_snapshot=t.telemetry_snapshot,
        transcript=t.transcript,
        source_language=t.source_language,
        checks=[check_dict(s, c) for c in checks_of(s, t)],
        photos=[{"id": p.id, "url": f"/uploads/{p.path}"} for p in photos],
        related=[ticket_summary(s, r) for r in links_of(s, t)],
    )
    return d


SEV_ORDER = {sev: i for i, sev in enumerate(SEVERITIES)}


def sort_key(d: dict) -> tuple:
    """Critical first, then overdue Monitoring, then by Severity, oldest first."""
    return (d["status"] == "closed", d["severity"] != "critical", not d["overdue"], SEV_ORDER[d["severity"]], d["created_at"] or "")


def list_tickets(
    s: Session,
    status: str | None = None,
    machine: str | None = None,
    assignee: int | None = None,
    q: str | None = None,
    since: datetime | None = None,
) -> list[dict]:
    query = select(Ticket)
    if status == "active":
        query = query.where(Ticket.status != "closed")
    elif status:
        query = query.where(Ticket.status.in_(status.split(",")))
    if machine:
        query = query.where(Ticket.machine_code == machine.upper())
    if since:
        query = query.where(Ticket.updated_at >= since)
    out = []
    for t in s.exec(query).all():
        d = ticket_summary(s, t)
        if assignee is not None and assignee not in [a["id"] for a in d["assignees"]]:
            continue
        if q and q.lower() not in f"{t.key} {t.title} {t.symptom} {t.machine_code}".lower():
            continue
        out.append(d)
    out.sort(key=sort_key)
    return out


# -- filing ------------------------------------------------------------------------

def _given(v: Any) -> bool:
    return v is not None and str(v).strip().lower() not in ("", NOT_GIVEN, "unknown", "none")


def make_title(draft: dict) -> str:
    if _given(draft.get("title")):
        return str(draft["title"]).strip()
    symptom = str(draft.get("symptom") or "Problem").strip()
    return f"{symptom[0].upper()}{symptom[1:]} on {draft['machine_code']}"


def file_ticket(
    s: Session,
    draft: dict,
    reporter_id: int,
    *,
    related_key: str | None = None,
    session_id: str = "",
    transcript: list[dict] | None = None,
    language: str = "en",
    snapshot: dict | None = None,
) -> Ticket:
    code = str(draft.get("machine_code") or "").upper().strip()
    if not s.get(Machine, code):
        raise DomainError("needs a machine: ask which machine it is")
    if not _given(draft.get("symptom")):
        raise DomainError("needs a symptom: ask what is wrong")
    severity = str(draft.get("severity") or "medium").lower()
    if severity not in SEVERITIES:
        severity = "medium"
    t_now = db.now()
    running = draft.get("machine_running")
    t = Ticket(
        key=next_key(s),
        title=make_title({**draft, "machine_code": code}),
        machine_code=code,
        severity=severity,
        status="open",
        reporter_id=reporter_id,
        symptom=str(draft.get("symptom")),
        since_text=str(draft.get("since") or NOT_GIVEN),
        context=str(draft.get("context") or NOT_GIVEN),
        machine_running=running if isinstance(running, bool) else None,
        description=str(draft.get("description") or ""),
        telemetry_snapshot=snapshot,
        transcript=transcript or [],
        source_language=language,
        created_at=t_now,
        updated_at=t_now,
    )
    s.add(t)
    s.flush()
    # auto-assign: on-shift Maintenance Technician; Critical also the on-shift Supervisor
    roles = ["maintenance"] + (["supervisor"] if severity == "critical" else [])
    for role in roles:
        for p in on_shift(s, role):
            s.add(TicketAssignee(ticket_id=t.id, person_id=p.id))
    if related_key:
        rel = get_ticket(s, related_key)
        s.add(TicketLink(ticket_id=t.id, related_ticket_id=rel.id))
        s.add(TicketLink(ticket_id=rel.id, related_ticket_id=t.id))
    if session_id:
        for photo in s.exec(select(Photo).where(Photo.session_id == session_id, Photo.ticket_id == None)).all():  # noqa: E711
            photo.ticket_id = t.id
            s.add(photo)
    s.commit()
    s.refresh(t)
    return t


# -- edits -------------------------------------------------------------------------

def update_ticket(s: Session, key: str, **fields: Any) -> Ticket:
    t = get_ticket(s, key)
    for name in ("title", "description", "severity"):
        v = fields.get(name)
        if v is None:
            continue
        if name == "severity":
            v = str(v).lower()
            if v not in SEVERITIES:
                raise DomainError(f"severity must be one of {', '.join(SEVERITIES)}")
        setattr(t, name, v)
    t.updated_at = db.now()
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def set_assignees(s: Session, t: Ticket, person_ids: list[int]) -> None:
    for pid in person_ids:
        if not s.get(Person, pid):
            raise DomainError(f"no person with id {pid}")
    for a in s.exec(select(TicketAssignee).where(TicketAssignee.ticket_id == t.id)).all():
        s.delete(a)
    s.flush()
    for pid in dict.fromkeys(person_ids):
        s.add(TicketAssignee(ticket_id=t.id, person_id=pid))
    t.updated_at = db.now()
    s.add(t)
    s.commit()


def assign(s: Session, key: str, add_names: list[str], remove_names: list[str]) -> Ticket:
    t = get_ticket(s, key)
    current = [p.id for p in assignees_of(s, t)]

    def resolve(name: str) -> Person:
        found = match_person(s, name)
        if not found:
            raise DomainError(f"nobody called {name}; ask who they meant")
        if len(found) > 1:
            names = " or ".join(p.name for p in found)
            raise DomainError(f"'{name}' is ambiguous: ask whether they mean {names}")
        return found[0]

    adds = [resolve(n).id for n in add_names]
    removes = {resolve(n).id for n in remove_names}
    set_assignees(s, t, [i for i in current if i not in removes] + adds)
    s.refresh(t)
    return t


def default_next_check(minutes: int | None) -> datetime:
    return db.now() + timedelta(minutes=minutes or 120)


def describe_line(s: Session, d: dict) -> str:
    """Compact one-line form used in KB's live context."""
    parts = [d["key"], d["machine_code"], d["severity"], d["status"].replace("_", " ")]
    if d["status"] == "monitoring":
        due = ist_hm(datetime.fromisoformat(d["next_check_at"])) if d["next_check_at"] else "?"
        parts[-1] += f" OVERDUE (due {due})" if d["overdue"] else f" (next check {due})"
    parts.append(d["title"])
    lc = d["last_check"]
    if lc:
        who = lc["author"]["name"].split()[0]
        at = ist_hm(datetime.fromisoformat(lc["created_at"]))
        if lc["unclear"]:
            parts.append(f"UNCLEAR check by {who} {at}: '{lc['what_found'] or lc['what_checked'] or 'nothing said'}'")
        else:
            parts.append(f"last check by {who} {at}: {lc['what_checked']} -> {lc['what_found']}")
    names = ", ".join(a["name"].split()[0] for a in d["assignees"]) or "unassigned"
    parts.append(f"assignees: {names}")
    reporter = d["reporter"]["name"].split()[0] if d["reporter"] else "?"
    parts.append(f"reported by {reporter} {ist_hm(datetime.fromisoformat(d['created_at']))}")
    if d["related_keys"]:
        parts.append("related: " + ", ".join(d["related_keys"]))
    return " | ".join(parts)

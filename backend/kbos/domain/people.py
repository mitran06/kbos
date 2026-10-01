"""People, shifts on the wall clock (IST), and name matching."""

from __future__ import annotations

import difflib
from datetime import datetime, timedelta

from sqlmodel import Session, select

from kbos import db
from kbos.models import Person, ShiftSession

IST = timedelta(hours=5, minutes=30)
ROLE_LABEL = {
    "operator": "Operator",
    "supervisor": "Supervisor",
    "maintenance": "Maintenance Technician",
    "admin": "Admin",
}


class DomainError(Exception):
    """A rule refused the action. The message is safe for KB to relay."""


def to_ist(dt: datetime) -> datetime:
    return dt + IST


def ist_hm(dt: datetime | None) -> str:
    return to_ist(dt).strftime("%H:%M") if dt else ""


# Shifts are 08:00–20:00 (Day) and 20:00–08:00 (Night) IST, but the people grid
# switches crews 2 h early so the incoming crew can log in before handover.
EARLY_LOGIN_H = 2


def current_shift(at: datetime | None = None) -> str:
    """The crew logging in now: 'day' from 06:00 to 20:00 IST, else 'night'."""
    h = to_ist(at or db.now()).hour
    return "day" if 8 - EARLY_LOGIN_H <= h < 20 else "night"


def person_dict(p: Person, on_shift: str | None = None) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "first_name": p.name.split()[0],
        "initials": p.initials,
        "role": p.role,
        "role_label": ROLE_LABEL[p.role],
        "shift": p.shift,
        "preferred_language": p.preferred_language,
        "avatar_hue": p.avatar_hue,
        "on_shift_now": p.shift == (on_shift or current_shift()),
    }


def list_people(s: Session, include_admin: bool = False) -> list[dict]:
    shift = current_shift()
    people = s.exec(select(Person)).all()
    out = [person_dict(p, shift) for p in people if include_admin or p.role != "admin"]
    role_order = {"operator": 0, "supervisor": 1, "maintenance": 2, "admin": 3}
    out.sort(key=lambda d: (not d["on_shift_now"], role_order[d["role"]], d["name"]))
    return out


def get_person(s: Session, person_id: int) -> Person:
    p = s.get(Person, person_id)
    if not p:
        raise DomainError(f"no person with id {person_id}")
    return p


def on_shift(s: Session, role: str | None = None) -> list[Person]:
    shift = current_shift()
    q = select(Person).where(Person.shift == shift)
    if role:
        q = q.where(Person.role == role)
    return list(s.exec(q).all())


def match_person(s: Session, name: str) -> list[Person]:
    """Fuzzy match a spoken name against people (first name, full name, initials)."""
    name = name.strip().lower()
    people = [p for p in s.exec(select(Person)).all() if p.role != "admin"]
    exact = [p for p in people if name in (p.name.lower(), p.name.split()[0].lower(), p.initials.lower())]
    if exact:
        return exact
    scored = []
    for p in people:
        options = [p.name.lower(), p.name.split()[0].lower(), p.name.split()[-1].lower()]
        best = max(difflib.SequenceMatcher(None, name, o).ratio() for o in options)
        if best >= 0.75:
            scored.append((best, p))
    scored.sort(key=lambda t: -t[0])
    if len(scored) > 1 and scored[0][0] - scored[1][0] > 0.1:
        return [scored[0][1]]
    return [p for _, p in scored]


def start_shift(s: Session, person_id: int) -> ShiftSession:
    get_person(s, person_id)
    t = db.now()
    for open_ in s.exec(
        select(ShiftSession).where(ShiftSession.person_id == person_id, ShiftSession.ended_at == None)  # noqa: E711
    ).all():
        open_.ended_at = t
        s.add(open_)
    ss = ShiftSession(person_id=person_id, started_at=t)
    s.add(ss)
    s.commit()
    s.refresh(ss)
    return ss


def end_shift(s: Session, shift_session_id: int, summary: str = "") -> ShiftSession:
    ss = s.get(ShiftSession, shift_session_id)
    if not ss:
        raise DomainError("no such shift session")
    ss.ended_at = ss.ended_at or db.now()
    if summary:
        ss.handover_summary = summary
    s.add(ss)
    s.commit()
    s.refresh(ss)
    return ss


def last_finished_shift(s: Session, person_id: int, before: datetime | None = None) -> ShiftSession | None:
    q = select(ShiftSession).where(ShiftSession.person_id == person_id, ShiftSession.ended_at != None)  # noqa: E711
    if before:
        q = q.where(ShiftSession.ended_at < before)
    return s.exec(q.order_by(ShiftSession.ended_at.desc())).first()


def shift_dict(ss: ShiftSession, p: Person | None = None) -> dict:
    from kbos.realtime import iso

    return {
        "id": ss.id,
        "person_id": ss.person_id,
        "person_name": p.name if p else None,
        "started_at": iso(ss.started_at),
        "ended_at": iso(ss.ended_at),
        "brief_text": ss.brief_text,
        "handover_summary": ss.handover_summary,
    }

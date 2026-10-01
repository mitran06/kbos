"""Shift Brief data: what a person needs to hear when their shift starts."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, select

from kbos import db
from kbos.domain.people import get_person, ist_hm, last_finished_shift
from kbos.domain.tickets import list_tickets, ticket_summary
from kbos.models import Check, Ticket


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def brief_data(s: Session, person_id: int, started_at: datetime | None = None) -> dict:
    person = get_person(s, person_id)
    last = last_finished_shift(s, person_id, before=started_at)
    since = last.ended_at if last else db.now() - timedelta(hours=12)

    active = list_tickets(s, status="active")
    critical = [d for d in active if d["severity"] == "critical"]
    overdue = [d for d in active if d["overdue"]]
    mine = [d for d in active if person_id in [a["id"] for a in d["assignees"]]]

    unclear = []
    for c in s.exec(select(Check).where(Check.unclear == True, Check.created_at >= since)).all():  # noqa: E712
        t = s.get(Ticket, c.ticket_id)
        if t and t.status != "closed":
            unclear.append(t.key)
    changed = [d for d in active if (_dt(d["updated_at"]) or since) >= since]
    closed_since = [
        ticket_summary(s, t)
        for t in s.exec(select(Ticket).where(Ticket.status == "closed", Ticket.closed_at >= since)).all()
    ]

    # cards: critical, then overdue/unclear, then mine, then the rest of what's active
    order: list[str] = []
    for group in (critical, overdue, [d for d in active if d["key"] in unclear], mine, active):
        for d in group:
            if d["key"] not in order:
                order.append(d["key"])
    by_key = {d["key"]: d for d in active}
    return {
        "person": person.name,
        "since": ist_hm(since),
        "active_count": len(active),
        "critical": [d["key"] for d in critical],
        "overdue": [d["key"] for d in overdue],
        "unclear": sorted(set(unclear)),
        "assigned_to_me": [d["key"] for d in mine],
        "changed_since": [d["key"] for d in changed],
        "closed_since": [d["key"] for d in closed_since],
        "tickets": [by_key[k] for k in order],
    }

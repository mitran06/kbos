"""Checks and Status changes. Every Status change carries a Check."""

from __future__ import annotations

import re

from sqlmodel import Session

from kbos import db
from kbos.domain.people import DomainError, on_shift
from kbos.domain.tickets import assignees_of, default_next_check, get_ticket
from kbos.models import STATUSES, Check, Person, Ticket

BARE = {"", "checked", "check", "ok", "okay", "done", "fine", "all ok", "all good", "fixed", "not given",
        "checked it", "it's fine", "its fine", "nothing", "na", "n/a", "ok kar diya", "theek hai"}  # fmt: skip
CLOSERS = {"supervisor", "maintenance", "admin"}


def is_bare(text: str | None) -> bool:
    t = re.sub(r"[^\w\s/']", "", (text or "").strip().lower())
    return t in BARE


def normalize_status(status: str | None) -> str | None:
    if status is None or str(status).strip() == "":
        return None
    v = str(status).strip().lower().replace(" ", "_").replace("-", "_")
    v = {"resolved": "closed", "close": "closed", "done": "closed", "inprogress": "in_progress",
         "monitor": "monitoring", "reopen": "open", "reopened": "open"}.get(v, v)  # fmt: skip
    if v not in STATUSES:
        raise DomainError(f"status must be one of open, in progress, monitoring, closed (got {status})")
    return v


def _fallback_owner(s: Session, t: Ticket) -> int | None:
    """Monitoring always has an owner: the first assignee, else the on-shift Supervisor."""
    assignees = assignees_of(s, t)
    if assignees:
        return assignees[0].id
    sups = on_shift(s, "supervisor")
    return sups[0].id if sups else None


def add_check(
    s: Session,
    key: str,
    actor: Person | None,
    what_checked: str,
    what_found: str,
    *,
    new_status: str | None = None,
    next_check_minutes: int | None = None,
    unclear: bool = False,
) -> tuple[Ticket, Check]:
    """Record a Check, optionally changing Status. `actor=None` means the Admin (dashboard)."""
    t = get_ticket(s, key)
    status_to = normalize_status(new_status)
    if status_to == t.status:
        status_to = None
    role = actor.role if actor else "admin"
    if status_to == "closed" and role not in CLOSERS:
        raise DomainError(
            "operators can't close tickets: explain that a supervisor or maintenance technician closes it, "
            "and offer to put it in Monitoring instead"
        )
    if (is_bare(what_checked) or is_bare(what_found)) and not unclear:
        raise DomainError(
            "needs a check: ask once what was checked and what was found; "
            "if they won't say, call add_check again with unclear=true"
        )
    unclear = unclear or is_bare(what_checked) or is_bare(what_found)

    t_now = db.now()
    c = Check(
        ticket_id=t.id,
        author_id=actor.id if actor else None,
        what_checked=what_checked.strip(),
        what_found=what_found.strip(),
        status_from=t.status if status_to else None,
        status_to=status_to,
        unclear=unclear,
        created_at=t_now,
    )
    if status_to:
        t.status = status_to
        if status_to == "monitoring":
            t.next_check_at = default_next_check(next_check_minutes)
            t.monitoring_owner_id = actor.id if actor else (t.monitoring_owner_id or _fallback_owner(s, t))
            c.next_check_at = t.next_check_at
        else:
            t.next_check_at = None
            t.monitoring_owner_id = None
        t.closed_at = t_now if status_to == "closed" else None
    elif t.status == "monitoring" and next_check_minutes:
        t.next_check_at = default_next_check(next_check_minutes)
        c.next_check_at = t.next_check_at
    t.updated_at = t_now
    s.add(t)
    s.add(c)
    s.commit()
    s.refresh(t)
    s.refresh(c)
    return t, c

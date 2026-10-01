"""SQLModel tables. Domain words follow CONTEXT.md."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

ROLES = ("operator", "supervisor", "maintenance", "admin")
SEVERITIES = ("critical", "high", "medium", "low")
STATUSES = ("open", "in_progress", "monitoring", "closed")


class Person(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    initials: str
    role: str  # operator | supervisor | maintenance | admin
    shift: str  # day | night
    preferred_language: str = "en"  # en | hi
    avatar_hue: int = 210


class Machine(SQLModel, table=True):
    code: str = Field(primary_key=True)
    name: str
    line: str
    target_per_shift: int | None = None
    unit: str = "parts"


class Ticket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    title: str
    description: str = ""
    machine_code: str = Field(foreign_key="machine.code", index=True)
    severity: str = "medium"
    status: str = "open"
    reporter_id: int | None = Field(default=None, foreign_key="person.id")
    symptom: str = ""
    since_text: str = ""
    context: str = ""
    machine_running: bool | None = None
    next_check_at: datetime | None = None
    monitoring_owner_id: int | None = Field(default=None, foreign_key="person.id")
    telemetry_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    transcript: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    source_language: str = "en"
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


class TicketAssignee(SQLModel, table=True):
    ticket_id: int = Field(foreign_key="ticket.id", primary_key=True)
    person_id: int = Field(foreign_key="person.id", primary_key=True)


class TicketLink(SQLModel, table=True):
    ticket_id: int = Field(foreign_key="ticket.id", primary_key=True)
    related_ticket_id: int = Field(foreign_key="ticket.id", primary_key=True)


class Check(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="ticket.id", index=True)
    author_id: int | None = Field(default=None, foreign_key="person.id")
    what_checked: str = ""
    what_found: str = ""
    status_from: str | None = None
    status_to: str | None = None
    unclear: bool = False
    next_check_at: datetime | None = None
    created_at: datetime


class Photo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int | None = Field(default=None, foreign_key="ticket.id", index=True)
    session_id: str = ""
    path: str
    uploader_id: int | None = Field(default=None, foreign_key="person.id")
    created_at: datetime


class ShiftSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    started_at: datetime
    ended_at: datetime | None = None
    brief_text: str = ""
    handover_summary: str = ""


class GlossaryTerm(SQLModel, table=True):
    term: str = Field(primary_key=True)
    meaning: str


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    at: datetime

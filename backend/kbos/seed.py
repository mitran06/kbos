"""Demo seed, relative to now.

The story: the previous shift's Operator (Priya) filed KB-0141 about 4B
vibration after a tool change; the previous shift's Supervisor (Suresh) marked
it "Checked" without saying what, put it in Monitoring, and the next check is
now overdue. Ramesh's crew is the current shift.

The current crew is always whichever shift is on now (people.current_shift), so
seeding at night swaps the two crews' shift labels and the story still holds.
"""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session

from kbos import db
from kbos.domain.people import current_shift
from kbos.models import (
    Check,
    Event,
    GlossaryTerm,
    Machine,
    Person,
    ShiftSession,
    Ticket,
    TicketAssignee,
)
from kbos.telemetry import telemetry

MACHINES = [
    ("4B", "CNC Lathe", "Line 4", 120, "parts"),
    ("2A", "Hydraulic Press", "Line 2", 900, "strokes"),
    ("3C", "Belt Conveyor", "Line 3", None, ""),
    ("1D", "Air Compressor", "Utilities", None, ""),
    ("5A", "CNC Mill", "Line 5", 80, "parts"),
    ("6B", "Surface Grinder", "Line 6", 150, "parts"),
]

GLOSSARY = [
    ("TC", "tool change"),
    ("vib", "vibration"),
    ("SB", "spindle bearing"),
    ("PM", "preventive maintenance"),
    ("LC", "light curtain"),
    ("hyd", "hydraulic"),
    ("jhatka", "jerk / shock load"),
    ("awaaz", "abnormal noise"),
    ("garam", "running hot"),
    ("leakage", "fluid leak"),
    ("ok kar diya", "fixed (ask how)"),
]

# (name, initials, role, crew, language, hue). crew "current" = on shift now.
PEOPLE = [
    ("Ramesh Yadav", "RY", "operator", "current", "en", 28),
    ("Kavita Sharma", "KS", "supervisor", "current", "en", 330),
    ("Imran Shaikh", "IS", "maintenance", "current", "hi", 200),
    ("Priya Nair", "PN", "operator", "previous", "en", 280),
    ("Suresh Patil", "SP", "supervisor", "previous", "hi", 150),
    ("Arjun Mehta", "AM", "maintenance", "previous", "en", 45),
    ("Neha Kulkarni", "NK", "admin", "current", "en", 250),
]


def seed(s: Session) -> dict[str, int]:
    now = db.now()
    cur = current_shift(now)
    prev = "night" if cur == "day" else "day"

    for code, name, line, target, unit in MACHINES:
        s.add(Machine(code=code, name=name, line=line, target_per_shift=target, unit=unit))
    for term, meaning in GLOSSARY:
        s.add(GlossaryTerm(term=term, meaning=meaning))
    ids: dict[str, int] = {}
    for name, initials, role, crew, lang, hue in PEOPLE:
        p = Person(
            name=name, initials=initials, role=role, shift=cur if crew == "current" else prev,
            preferred_language=lang, avatar_hue=hue,
        )  # fmt: skip
        s.add(p)
        s.flush()
        ids[name.split()[0].lower()] = p.id
    s.commit()

    def ago(**kw) -> timedelta:
        return now - timedelta(**kw)

    def ticket(key, machine, title, severity, status, reporter, created, **kw) -> Ticket:
        t = Ticket(
            key=key, title=title, machine_code=machine, severity=severity, status=status,
            reporter_id=ids[reporter], created_at=created, updated_at=kw.pop("updated_at", created), **kw,
        )  # fmt: skip
        s.add(t)
        s.flush()
        return t

    def check(t, author, checked, found, frm, to, at, unclear=False, next_check=None):
        s.add(Check(
            ticket_id=t.id, author_id=ids[author], what_checked=checked, what_found=found,
            status_from=frm, status_to=to, unclear=unclear, next_check_at=next_check, created_at=at,
        ))  # fmt: skip

    def assign(t, *names):
        for n in names:
            s.add(TicketAssignee(ticket_id=t.id, person_id=ids[n]))

    # --- 4B history: closed 3 days ago
    t = ticket("KB-0127", "4B", "Chuck jaw wear causing poor grip", "medium", "closed", "priya", ago(days=4),
               symptom="chuck jaws worn, parts slipping", since_text="this morning", context="after a long run",
               machine_running=True, closed_at=ago(days=3), updated_at=ago(days=3))  # fmt: skip
    assign(t, "arjun")
    check(t, "arjun", "measured chuck jaw wear on all three jaws", "jaws worn 0.4 mm, replaced the set; grip test OK",
          "open", "closed", ago(days=3))  # fmt: skip

    t = ticket("KB-0119", "6B", "Wheel guard bolt loose", "high", "closed", "ramesh", ago(days=6),
               symptom="wheel guard bolt loose", since_text="start of shift", context="during setup",
               machine_running=False, closed_at=ago(days=6) + timedelta(hours=2), updated_at=ago(days=6))  # fmt: skip
    assign(t, "imran")
    check(t, "imran", "checked all four guard bolts", "one bolt sheared; replaced and torqued all four to spec",
          "open", "closed", ago(days=6) + timedelta(hours=2))  # fmt: skip

    t = ticket("KB-0123", "5A", "Coolant concentration low", "low", "closed", "priya", ago(days=5),
               symptom="coolant concentration low", since_text="yesterday", context="refractometer reading 3%",
               machine_running=True, closed_at=ago(days=5) + timedelta(hours=5), updated_at=ago(days=5))  # fmt: skip
    assign(t, "arjun")
    check(t, "arjun", "refractometer reading of the coolant sump", "was 3%, topped up concentrate, now 7%",
          "open", "closed", ago(days=5) + timedelta(hours=5))  # fmt: skip

    t = ticket("KB-0131", "5A", "Spindle warm-up alarm at start", "medium", "closed", "ramesh", ago(days=2),
               symptom="spindle warm-up alarm on start", since_text="today", context="cold start",
               machine_running=False, closed_at=ago(days=2) + timedelta(hours=3), updated_at=ago(days=2))  # fmt: skip
    assign(t, "imran")
    check(t, "imran", "spindle warm-up cycle parameters", "warm-up program was skipped; re-enabled it, alarm cleared",
          "open", "closed", ago(days=2) + timedelta(hours=3))  # fmt: skip

    t = ticket("KB-0134", "3C", "Belt slipping at drive pulley", "medium", "in_progress", "kavita", ago(hours=20),
               symptom="belt slipping at the drive pulley", since_text="yesterday afternoon", context="under full load",
               machine_running=True, updated_at=ago(hours=18))  # fmt: skip
    assign(t, "imran")
    check(t, "imran", "belt tension at the drive pulley", "tension low; ordered a new belt, re-tensioned for now",
          "open", "in_progress", ago(hours=18))  # fmt: skip

    t = ticket("KB-0136", "2A", "Light curtain intermittent trip", "high", "open", "priya", ago(hours=9),
               symptom="light curtain trips the press randomly", since_text="start of night shift",
               context="about once an hour, nobody in the zone", machine_running=True)  # fmt: skip

    t = ticket("KB-0138", "1D", "Compressor pressure dropping to 5.8 bar", "high", "monitoring", "priya", ago(hours=7),
               symptom="line pressure dropping to 5.8 bar", since_text="around midnight", context="normal demand",
               machine_running=True, next_check_at=now + timedelta(hours=2), monitoring_owner_id=ids["arjun"],
               updated_at=ago(hours=1))  # fmt: skip
    assign(t, "arjun")
    check(t, "arjun", "checked the auto-drain valve", "found it stuck partly open; cleaned and closed it, pressure back to 6.9 bar",
          "open", "monitoring", ago(hours=1), next_check=now + timedelta(hours=2))  # fmt: skip

    t = ticket("KB-0140", "2A", "Hydraulic oil leak at the main cylinder seal", "critical", "open", "suresh", ago(hours=3),
               symptom="hydraulic oil leaking at the main cylinder seal", since_text="about 3 hours ago",
               context="puddle under the press, level dropping", machine_running=True)  # fmt: skip
    assign(t, "arjun", "suresh")

    snap = telemetry.snapshot("4B") if "4B" in telemetry.machines else None
    if snap:
        snap = {**snap, "current": {**snap["current"], "vibration_mm_s": 4.6}, "vibration_band": "warning"}
    t = ticket("KB-0141", "4B", "Unusual vibration on 4B after tool change", "high", "monitoring", "priya",
               ago(hours=5, minutes=40),
               symptom="unusual vibration, felt through the guard", since_text="right after the tool change",
               context="right after a tool change", machine_running=True,
               next_check_at=ago(minutes=15), monitoring_owner_id=ids["suresh"], telemetry_snapshot=snap,
               updated_at=ago(hours=2, minutes=15), source_language="en",
               transcript=[
                   {"who": "user", "text": "KB, 4B is vibrating more than usual. I can feel it through the guard.", "lang": "en"},
                   {"who": "kb", "text": "Got it. Since when?", "lang": "en"},
                   {"who": "user", "text": "Right after the tool change.", "lang": "en"},
                   {"who": "kb", "text": "Is the machine still running?", "lang": "en"},
                   {"who": "user", "text": "Yes, still running. File it as high.", "lang": "en"},
               ])  # fmt: skip
    assign(t, "arjun")
    check(t, "suresh", "", "Checked", "open", "monitoring", ago(hours=2, minutes=15), unclear=True,
          next_check=ago(minutes=15))  # fmt: skip

    # previous shift's sessions (and Ramesh's last day shift) so Briefs know "since when"
    s.add(ShiftSession(person_id=ids["priya"], started_at=ago(hours=11, minutes=50), ended_at=ago(minutes=20),
                       handover_summary="Filed the 4B vibration and the 2A light curtain trips."))  # fmt: skip
    s.add(ShiftSession(person_id=ids["suresh"], started_at=ago(hours=11, minutes=55), ended_at=ago(minutes=15),
                       handover_summary="4B checked. 2A leak reported."))  # fmt: skip
    s.add(ShiftSession(person_id=ids["arjun"], started_at=ago(hours=11, minutes=45), ended_at=ago(minutes=10),
                       handover_summary="1D auto-drain valve cleaned, pressure 6.9 bar, monitoring. 2A leak needs a seal kit."))  # fmt: skip
    for n in ("ramesh", "kavita", "imran"):
        s.add(ShiftSession(person_id=ids[n], started_at=ago(hours=24), ended_at=ago(hours=12)))
    s.add(Event(type="demo.seeded", payload={}, at=now))
    s.commit()
    return ids

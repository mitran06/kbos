"""Related Tickets: same Machine, similar symptom."""

from __future__ import annotations

import re
from datetime import timedelta

from sqlmodel import Session, select

from kbos import db
from kbos.models import Ticket

STOP = {"the", "a", "an", "on", "at", "of", "and", "is", "in", "after", "from", "to", "with", "machine",
        "again", "very", "not", "given", "since", "it", "its", "there", "some", "bad", "badly", "high"}  # fmt: skip
SYNONYMS = {
    "vibrat": "vibration", "shak": "vibration", "jhatka": "vibration", "wobbl": "vibration",
    "leak": "leak", "oil": "leak", "drip": "leak",
    "nois": "noise", "sound": "noise", "awaaz": "noise", "rattl": "noise", "grind": "noise",
    "hot": "heat", "heat": "heat", "garam": "heat", "temperatur": "heat", "overheat": "heat",
    "pressur": "pressure", "trip": "trip", "alarm": "alarm", "slip": "slip", "belt": "belt",
    "spindl": "spindle", "bearing": "bearing", "chuck": "chuck", "coolant": "coolant",
}  # fmt: skip


def stems(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if w in STOP or len(w) < 3:
            continue
        mapped = next((v for k, v in SYNONYMS.items() if w.startswith(k)), None)
        out.add(mapped or w[:6])
    return out


def related_candidates(s: Session, machine_code: str, text: str, exclude_id: int | None = None) -> list[tuple[float, Ticket]]:
    """Non-closed tickets on the machine + ones closed in the last 7 days, ranked by overlap."""
    cutoff = db.now() - timedelta(days=7)
    want = stems(text)
    scored = []
    for t in s.exec(select(Ticket).where(Ticket.machine_code == machine_code.upper())).all():
        if t.id == exclude_id:
            continue
        if t.status == "closed" and (t.closed_at is None or t.closed_at < cutoff):
            continue
        have = stems(f"{t.title} {t.symptom}")
        overlap = len(want & have)
        if overlap == 0:
            continue
        score = overlap / max(1, len(want)) + (0.2 if t.status != "closed" else 0)
        scored.append((score, t))
    scored.sort(key=lambda p: -p[0])
    return scored

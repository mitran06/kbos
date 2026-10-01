"""Conversation scenarios in text mode against the real LLM (PLAN §9.2).

Opt-in (costs a little LLM credit, no STT/TTS):  uv run pytest -m llm -q tests/test_scenarios.py
Each scenario runs 3x on a freshly seeded DB.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from sqlmodel import select

from kbos import db
from kbos.domain import tickets as T
from kbos.domain.checks import add_check
from kbos.domain.people import start_shift
from kbos.models import Check, Person
from kbos.voice.language import DEVANAGARI, detect
from kbos.voice.textmode import TextSession

pytestmark = pytest.mark.llm
RUNS = range(3)


def pid(name: str) -> int:
    with db.session() as s:
        return s.exec(select(Person).where(Person.name.startswith(name))).one().id


def session_for(name: str, key_index: int) -> TextSession:
    with db.session() as s:
        ss = start_shift(s, pid(name))
    return TextSession(pid(name), ss.id, key_index=key_index)


def run(coro):
    return asyncio.run(coro)


def all_tools(turns) -> list[dict]:
    return [c for t in turns for c in t.tools]


def mentions(text: str, key: str) -> bool:
    n = key.split("-")[1].lstrip("0")
    spoken = "-".join({"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
                       "7": "seven", "8": "eight", "9": "nine"}[c] for c in n)  # fmt: skip
    return key in text or n in text or spoken in text.lower() or key.replace("-", "") in text


@pytest.mark.parametrize("i", RUNS)
def test_hinglish_filing_links_related_and_assigns(client, i):
    async def go():
        ts = session_for("Ramesh", i)
        turns = [await ts.say("KB, 4B pe phir se bahut vibration aa raha hai, awaaz bhi aa rahi hai, machine abhi chal rahi hai.")]
        asked_related = mentions(turns[0].text, "KB-0141")
        for _ in range(10):
            last = turns[-1]
            if any(c["name"] == "file_ticket" and "ticket_key" in c["result"] for c in last.tools):
                break
            d = ts.state.draft or {}
            ui_types = [u["type"] for u in last.ui]
            text = last.text.lower()
            if "ui.camera" in ui_types:
                turns.append(await ts.client_message("photo.skipped"))
            elif ts.state.related_asked and not d.get("related_ticket_key"):
                turns.append(await ts.say("Haan, same problem hai."))
            elif "since" in T_missing(ts):
                turns.append(await ts.say("Das minute se."))
            elif "context" in T_missing(ts):
                turns.append(await ts.say("Tool change ke baad se."))
            elif "severity" in T_missing(ts):
                turns.append(await ts.say("Critical, production ruk jayega."))
            elif "machine_running" in T_missing(ts):
                turns.append(await ts.say("Haan, chal rahi hai."))
            elif "file" in text or "फ़ाइल" in last.text or "फाइल" in last.text or "?" in last.text:
                turns.append(await ts.say("Haan, file kar do."))
            else:
                turns.append(await ts.say("Haan."))
        return ts, turns, asked_related

    ts, turns, asked_related = run(go())
    transcript = "\n".join(f"U: {t.user}\nKB: {t.text}" for t in turns)
    assert asked_related, f"KB should ask about KB-0141 first\n{transcript}"
    with db.session() as s:
        t = T.get_ticket(s, "KB-0142")
        d = T.ticket_detail(s, t)
    assert d["related_keys"] == ["KB-0141"], transcript
    assert "Imran Shaikh" in [a["name"] for a in d["assignees"]], transcript
    for field in ("symptom", "title", "context", "since_text"):
        assert detect(d[field]) == "en" and not DEVANAGARI.search(d[field]), f"{field}={d[field]!r}\n{transcript}"
    assert d["severity"] == "critical", transcript
    assert d["telemetry_snapshot"] and d["transcript"], "snapshot + transcript attached"
    hindi_replies = [t for t in turns if t.text and t.user not in ("photo.skipped",)]
    assert sum(bool(DEVANAGARI.search(t.text)) for t in hindi_replies) >= len(hindi_replies) - 1, transcript
    for t in turns:
        assert t.text.count("?") <= 1 or len(t.text) < 160, f"one question at a time: {t.text}"


def T_missing(ts: TextSession) -> list[str]:
    from kbos.voice.tools import draft_missing

    return draft_missing(ts.state.draft or {})


@pytest.mark.parametrize("i", RUNS)
def test_english_whats_open(client, i):
    ts = session_for("Ramesh", i)
    t = run(ts.say("What's open today?"))
    shown = [k for c in t.called("show_tickets") for k in c["result"].get("shown", [])]
    assert len(shown) >= 4 and "KB-0140" in shown and "KB-0141" in shown, (t.text, t.tools)
    assert not DEVANAGARI.search(t.text), t.text
    low = t.text.lower()
    first_critical = min((low.find(w) for w in ("critical", "leak", "2a") if w in low), default=999)
    assert first_critical < 120, f"critical first: {t.text}"
    assert "overdue" in low or mentions(t.text, "KB-0141"), t.text


@pytest.mark.parametrize("i", RUNS)
def test_maintenance_assigned_then_close_with_specific_check(client, i):
    with db.session() as s:
        T.file_ticket(s, {"machine_code": "4B", "symptom": "heavy vibration and abnormal noise", "since": "10 minutes",
                          "context": "after tool change", "severity": "critical", "machine_running": True},
                      pid("Ramesh"), related_key="KB-0141")  # fmt: skip
    ts = session_for("Imran", i)
    t1 = run(ts.say("What's assigned to me?"))
    shown = [k for c in t1.called("show_tickets") for k in c["result"].get("shown", [])]
    assert "KB-0142" in shown, (t1.text, t1.tools)
    t2 = run(ts.say("Close one-four-two. I replaced the spindle bearing, vibration is back to two millimetres per second."))
    checks = t2.called("add_check")
    assert checks and checks[-1]["result"].get("status") == "closed", (t2.text, t2.tools)
    args = checks[-1]["args"]
    assert "bearing" in args["what_checked"].lower() + args["what_found"].lower()
    assert not checks[-1]["result"]["unclear"]
    with db.session() as s:
        assert T.get_ticket(s, "KB-0142").status == "closed"


@pytest.mark.parametrize("i", RUNS)
def test_bare_checked_is_asked_once_then_unclear(client, i):
    ts = session_for("Imran", i)
    t1 = run(ts.say("3C checked."))
    with db.session() as s:
        before = len(s.exec(select(Check).where(Check.ticket_id == T.get_ticket(s, "KB-0134").id)).all())
    assert "?" in t1.text, f"KB must ask what was checked/found: {t1.text}"
    assert not any(c["result"].get("ok") for c in t1.called("add_check")), t1.tools
    t2 = run(ts.say("Bas check kar liya."))
    with db.session() as s:
        t = T.get_ticket(s, "KB-0134")
        checks = s.exec(select(Check).where(Check.ticket_id == t.id).order_by(Check.created_at)).all()
    assert len(checks) == before + 1, (t2.text, t2.tools)
    assert checks[-1].unclear, (t2.text, t2.tools)
    assert checks[-1].author_id == pid("Imran")


@pytest.mark.parametrize("i", RUNS)
def test_operator_cannot_close(client, i):
    ts = session_for("Ramesh", i)
    t = run(ts.say("Close 0141, it's fine now."))
    with db.session() as s:
        assert T.get_ticket(s, "KB-0141").status == "monitoring"
    assert "monitor" in t.text.lower() or "मॉनिटर" in t.text, t.text


@pytest.mark.parametrize("i", RUNS)
def test_assign_two_people(client, i):
    ts = session_for("Kavita", i)
    t = run(ts.say("Assign the 2A leak to Arjun and Imran."))
    with db.session() as s:
        names = [p.name for p in T.assignees_of(s, T.get_ticket(s, "KB-0140"))]
    assert "Arjun Mehta" in names and "Imran Shaikh" in names, (t.text, t.tools, names)


@pytest.mark.parametrize("i", RUNS)
def test_handover_records_checks_and_ends_shift(client, i):
    ts = session_for("Ramesh", i)
    with db.session() as s:
        ramesh = s.get(Person, pid("Ramesh"))
        add_check(s, "KB-0136", ramesh, "watched the light curtain for an hour", "tripped twice, both with nobody in the zone")
        T.file_ticket(s, {"machine_code": "6B", "symptom": "grinding wheel making a squealing noise", "since": "an hour",
                          "context": "during dressing", "severity": "medium", "machine_running": True}, ramesh.id)  # fmt: skip
    turns = [run(ts.handover())]
    answers = ["Still tripping now and then, Kavita knows about it.", "Squeal is still there, wheel needs dressing.",
               "That's all.", "Yes."]  # fmt: skip
    for a in answers:
        if any(c["name"] == "end_shift" for c in all_tools(turns)):
            break
        turns.append(run(ts.say(a)))
    tools = all_tools(turns)
    transcript = "\n".join(f"U: {t.user}\nKB: {t.text} {[c['name'] for c in t.tools]}" for t in turns)
    checked = {c["args"]["ticket_key"].upper().replace("KB", "KB-").replace("--", "-") for c in tools
               if c["name"] == "add_check" and c["result"].get("ok")}  # fmt: skip
    assert {"KB-0136", "KB-0142"} <= {T.normalize_key(k) for k in checked}, transcript
    assert any(c["name"] == "end_shift" and c["result"].get("ok") for c in tools), transcript
    assert re.search(r"\w", turns[-1].text), transcript

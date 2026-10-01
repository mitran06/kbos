"""KB's tools: JSON schemas + handlers shared by the voice pipeline and text mode.

Handlers take the per-session KBState and the parsed arguments and return a
JSON-able result for the LLM. UI effects go through `state.push` (RTVI server
messages) and the /ws hub. All arguments are English (ADR 0002).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlmodel import select

from kbos import db
from kbos.domain import tickets as T
from kbos.domain.checks import add_check
from kbos.domain.people import DomainError, end_shift, get_person, on_shift, shift_dict
from kbos.domain.related import related_candidates
from kbos.models import Check, Machine, Person, Photo, ShiftSession, Ticket, TicketAssignee
from kbos.realtime import hub
from kbos.telemetry import telemetry
from kbos.voice.language import detect

DRAFT_FIELDS = ("machine_code", "symptom", "since", "context", "machine_running", "severity")


@dataclass
class KBState:
    person_id: int
    shift_session_id: int | None
    session_id: str
    push: Callable[[dict], Awaitable[None]]
    draft: dict | None = None
    focused: str | None = None
    photos: list[dict] = field(default_factory=list)
    photo_offered: bool = False
    related_asked: bool = False
    filed: list[str] = field(default_factory=list)
    touched: set[str] = field(default_factory=set)
    mode: str = "chat"  # chat | brief | handover
    handover_keys: list[str] = field(default_factory=list)
    shift_ended: bool = False
    transcript: list[dict] = field(default_factory=list)  # [{who, text, lang}]
    draft_transcript_from: int = 0
    tool_log: list[dict] = field(default_factory=list)

    def person(self) -> Person:
        with db.session() as s:
            return get_person(s, self.person_id)


# ---- schemas -----------------------------------------------------------------------

def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


S = {"type": "string"}
TOOLS: list[dict] = [
    {
        "name": "show_tickets",
        "description": "Show ticket cards on the user's screen. Use whenever you talk about specific tickets. "
        "Speak your answer in the same response.",
        "parameters": _obj(
            {"ticket_keys": {"type": "array", "items": S, "description": "e.g. ['KB-0141']"},
             "heading": {"type": "string", "description": "short English heading, e.g. 'Open on 4B'"}},
            ["ticket_keys", "heading"],
        ),
    },
    {
        "name": "focus_ticket",
        "description": "Open one ticket's detail card and get its full history (all checks). Use when the user "
        "asks about one ticket in detail.",
        "parameters": _obj({"ticket_key": S}, ["ticket_key"]),
    },
    {
        "name": "update_draft",
        "description": "Create or update the Draft of a new ticket the user is reporting. Call as soon as you "
        "learn anything. Pass ONLY fields the user actually said (never guess severity or since-when), translated "
        "into short clear English (e.g. 'bahut vibration aa raha hai' -> 'heavy vibration'). Use 'not given' "
        "when the user doesn't know. The result's 'next' tells you exactly what to do next.",
        "parameters": _obj({
            "machine_code": {"type": "string", "description": "floor code like 4B, 2A"},
            "title": {"type": "string", "description": "short English title"},
            "symptom": {"type": "string", "description": "what is wrong, in English"},
            "since": {"type": "string", "description": "since when, e.g. '10 minutes'"},
            "context": {"type": "string", "description": "what was happening, e.g. 'after tool change'"},
            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            "machine_running": {"type": "boolean", "description": "is the machine still running"},
            "related_ticket_key": {"type": "string", "description": "the existing ticket key once the user confirms it's the same problem, or 'none' if they say no"},
        }),  # fmt: skip
    },
    {
        "name": "request_photo",
        "description": "Open the camera so the user can attach a photo to the Draft. Offer once; they may skip.",
        "parameters": _obj({"reason": S}),
    },
    {
        "name": "file_ticket",
        "description": "File the Draft as a ticket after the user approves the read-back summary.",
        "parameters": _obj({"related_ticket_key": {"type": "string", "description": "related ticket if confirmed"}}),
    },
    {
        "name": "discard_draft",
        "description": "Throw away the current Draft when the user cancels.",
        "parameters": _obj({}),
    },
    {
        "name": "add_check",
        "description": "Record a Check on a ticket (what was checked, what was found), optionally changing its "
        "status. Every status change needs a Check. If the user only says 'checked'/'done'/'ok kar diya', first ask "
        "once what they checked and found; if they still won't say, call with unclear=true and their words.",
        "parameters": _obj({
            "ticket_key": S,
            "what_checked": {"type": "string", "description": "English"},
            "what_found": {"type": "string", "description": "English"},
            "new_status": {"type": "string", "enum": ["open", "in_progress", "monitoring", "closed"]},
            "next_check_minutes": {"type": "integer", "description": "for monitoring; default 120"},
            "unclear": {"type": "boolean", "description": "true only if the user refused to say what was checked/found"},
        }, ["ticket_key", "what_checked", "what_found", "unclear"]),  # fmt: skip
    },
    {
        "name": "update_ticket",
        "description": "Edit a ticket's title, description or severity (not status).",
        "parameters": _obj({"ticket_key": S, "title": S, "description": S,
                            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]}},
                           ["ticket_key"]),  # fmt: skip
    },
    {
        "name": "assign_ticket",
        "description": "Add or remove assignees on a ticket by person name.",
        "parameters": _obj({"ticket_key": S, "add_names": {"type": "array", "items": S},
                            "remove_names": {"type": "array", "items": S}}, ["ticket_key"]),  # fmt: skip
    },
    {
        "name": "end_shift",
        "description": "Only during the Handover: end the user's shift once every touched ticket has an update.",
        "parameters": _obj({"summary": {"type": "string", "description": "one or two English sentences"}}, ["summary"]),
    },
]
TOOL_NAMES = [t["name"] for t in TOOLS]


# ---- handlers -----------------------------------------------------------------------

def _keys(raw: list[str] | None) -> list[str]:
    out = []
    for k in raw or []:
        try:
            out.append(T.normalize_key(k))
        except DomainError:
            continue
    return list(dict.fromkeys(out))


def draft_missing(d: dict) -> list[str]:
    return [f for f in DRAFT_FIELDS if d.get(f) in (None, "")]


def draft_view(state: KBState) -> dict | None:
    if state.draft is None:
        return None
    d = state.draft
    with db.session() as s:
        maint = [p.name for p in on_shift(s, "maintenance")]
    return {
        **{k: d.get(k) for k in DRAFT_FIELDS},
        "related_ticket_key": d.get("related_ticket_key") if d.get("related_ticket_key") != "none" else None,
        "title": d.get("title") or (T.make_title(d) if d.get("machine_code") and d.get("symptom") else None),
        "missing": draft_missing(d),
        "photos": state.photos,
        "will_assign": maint,
    }


async def show_tickets(state: KBState, ticket_keys: list[str] | None = None, heading: str = "") -> dict:
    keys = _keys(ticket_keys)
    with db.session() as s:
        found = []
        for k in keys:
            try:
                found.append(T.ticket_summary(s, T.get_ticket(s, k)))
            except DomainError:
                pass
    await state.push({"type": "ui.tickets", "heading": heading or "Tickets", "tickets": found})
    return {"shown": [d["key"] for d in found], "missing": [k for k in keys if k not in [d["key"] for d in found]]}


async def focus_ticket(state: KBState, ticket_key: str) -> dict:
    with db.session() as s:
        d = T.ticket_detail(s, T.get_ticket(s, ticket_key))
    state.focused = d["key"]
    await state.push({"type": "ui.ticket", "ticket": d})
    return {
        "key": d["key"], "title": d["title"], "status": d["status"], "severity": d["severity"],
        "overdue": d["overdue"], "symptom": d["symptom"], "since": d["since_text"], "context": d["context"],
        "assignees": [a["name"] for a in d["assignees"]],
        "checks": [
            {"by": c["author"]["name"], "at": c["created_at"], "checked": c["what_checked"], "found": c["what_found"],
             "status": c["status_to"], "unclear": c["unclear"]}
            for c in d["checks"]
        ],
        "related": d["related_keys"],
    }  # fmt: skip


QUESTIONS = {
    "machine_code": "which machine it is",
    "symptom": "what exactly is wrong",
    "since": "since when it has been happening",
    "context": "what was going on when it started (e.g. after a tool change)",
    "machine_running": "whether the machine is still running",
    "severity": "how severe it is (critical, high, medium or low)",
}
TEXT_FIELDS = ("title", "symptom", "since", "context")
SEVERITY_WORDS = re.compile(
    r"critical|high|medium|low|urgent|serious|severe|emergency|minor|major|safety|stop|band|ruk|rok|"
    r"क्रिटिकल|हाई|मीडियम|लो|गंभीर|ज़्यादा|ज्यादा|कम|रुक|बंद|ख़तर|खतर",
    re.I,
)
UNSURE_WORDS = re.compile(
    r"pata nahi|nahi pata|nahin pata|don'?t know|not sure|no idea|maloom nahi|malum nahi|"
    r"पता नहीं|मालूम नहीं|नहीं पता|pata nahin",
    re.I,
)


def user_said_since_draft(state: KBState) -> str:
    return " ".join(line["text"] for line in state.transcript[state.draft_transcript_from:] if line["who"] == "user")


def next_step(state: KBState, possible: list[dict]) -> str:
    d = state.draft or {}
    if possible and not d.get("related_ticket_key"):
        p = possible[0]
        state.related_asked = True
        return (f"ask ONLY whether this is the same problem as {p['key']} ('{p['title']}', {p['status']}"
                f"{', overdue' if p['overdue'] else ''}); then call update_draft with related_ticket_key "
                f"'{p['key']}' if yes or 'none' if no. Ask in the user's language")  # fmt: skip
    missing = draft_missing(d)
    if missing:
        return f"ask ONLY {QUESTIONS[missing[0]]} (one short question, in the user's language)"
    if not state.photo_offered:
        return "call request_photo now"
    return "read back a one-sentence summary and ask whether to file it"


async def update_draft(state: KBState, **fields: Any) -> dict:
    if state.draft is None:
        state.draft = {}
        users = [i for i, line in enumerate(state.transcript) if line["who"] == "user"]
        state.draft_transcript_from = users[-1] if users else 0
    d = state.draft
    not_english = []
    said = user_said_since_draft(state)
    for k, v in fields.items():
        if v is None or v == "":
            continue
        # Never let KB guess: severity only if the user said one, "not given" only if they don't know.
        if k == "severity" and not SEVERITY_WORDS.search(said):
            continue
        if isinstance(v, str) and v.strip().lower() == "not given" and not UNSURE_WORDS.search(said):
            continue
        if k in TEXT_FIELDS and isinstance(v, str) and v.strip().lower() != "not given" and detect(v) == "hi":
            not_english.append(k)
            continue
        if k == "machine_code":
            v = str(v).upper().replace(" ", "").replace("-", "")
        if k == "related_ticket_key":
            if not state.related_asked:
                continue  # KB must ask "same problem?" before linking
            v = "none" if str(v).strip().lower() in ("none", "no", "") else T.normalize_key(str(v))
        if k == "severity":
            v = str(v).lower()
        d[k] = v
    possible = []
    if d.get("machine_code"):
        with db.session() as s:
            if not s.get(Machine, d["machine_code"]):
                bad = d.pop("machine_code")
                await state.push({"type": "ui.draft", "draft": draft_view(state)})
                return {"error": f"there is no machine {bad}; ask which machine (codes like 4B, 2A, 3C, 1D, 5A, 6B)"}
            if d.get("symptom"):
                for _, t in related_candidates(s, d["machine_code"], f"{d.get('symptom', '')} {d.get('title', '')}")[:1]:
                    possible.append({"key": t.key, "title": t.title, "status": t.status, "overdue": T.is_overdue(t)})
    view = draft_view(state)
    await state.push({"type": "ui.draft", "draft": view, "possible_related": possible})
    out: dict[str, Any] = {"missing": view["missing"], "next": next_step(state, possible)}
    if not_english:
        out["error"] = f"{', '.join(not_english)} must be in English: translate and call update_draft again"
    return out


async def request_photo(state: KBState, reason: str = "") -> dict:
    state.photo_offered = True
    await state.push({"type": "ui.camera", "reason": reason or "Add a photo"})
    return {"status": "camera is open on the phone; in the user's language say one short line inviting them to take a photo or tap skip, then wait"}


async def file_ticket(state: KBState, related_ticket_key: str | None = None) -> dict:
    if not state.draft:
        return {"error": "there is no draft to file"}
    d = state.draft
    related = related_ticket_key or d.get("related_ticket_key")
    if related and str(related).lower() == "none":
        related = None
    lines = state.transcript[state.draft_transcript_from:]
    lang = "hi" if any(line.get("lang") == "hi" for line in lines if line["who"] == "user") else "en"
    with db.session() as s:
        code = str(d.get("machine_code") or "").upper()
        snap = telemetry.snapshot(code) if code in telemetry.machines else None
        t = T.file_ticket(
            s, d, state.person_id, related_key=related, session_id=state.session_id,
            transcript=lines, language=lang, snapshot=snap,
        )  # fmt: skip
        summary = T.ticket_summary(s, t)
        related_summary = T.ticket_summary(s, T.get_ticket(s, related)) if related else None
    state.filed.append(t.key)
    state.touched.add(t.key)
    state.draft = None
    state.photos = []
    state.photo_offered = False
    state.related_asked = False
    hub.publish("ticket.created", {"ticket": summary, "by": state.person_id})
    if related_summary:
        hub.publish("ticket.updated", {"ticket": related_summary, "by": state.person_id})
    await state.push({"type": "ui.ticket_filed", "ticket": summary})
    return {
        "ticket_key": t.key,
        "assignees": [a["name"] for a in summary["assignees"]],
        "related": related,
        "note": "the filed card is already on screen; confirm in one short line (key + who it's assigned to)",
    }


async def discard_draft(state: KBState) -> dict:
    with db.session() as s:  # a discarded Draft's photos must not ride along on the next ticket
        for p in s.exec(select(Photo).where(Photo.session_id == state.session_id, Photo.ticket_id == None)).all():  # noqa: E711
            p.session_id = ""
            s.add(p)
        s.commit()
    state.draft = None
    state.photos = []
    state.photo_offered = False
    state.related_asked = False
    await state.push({"type": "ui.draft", "draft": None})
    return {"ok": True}


async def add_check_tool(
    state: KBState, ticket_key: str, what_checked: str = "", what_found: str = "", new_status: str | None = None,
    next_check_minutes: int | None = None, unclear: bool = False,
) -> dict:  # fmt: skip
    with db.session() as s:
        actor = get_person(s, state.person_id)
        t, c = add_check(s, ticket_key, actor, what_checked, what_found, new_status=new_status,
                         next_check_minutes=next_check_minutes, unclear=unclear)  # fmt: skip
        detail = T.ticket_detail(s, t)
        summary = T.ticket_summary(s, t)
        check = T.check_dict(s, c)
    state.touched.add(t.key)
    state.focused = t.key
    hub.publish("check.added", {"ticket_key": t.key, "check": check})
    hub.publish("ticket.updated", {"ticket": summary, "by": state.person_id})
    await state.push({"type": "ui.ticket", "ticket": detail, "highlight": "check"})
    return {"ok": True, "ticket_key": t.key, "status": t.status, "unclear": c.unclear,
            "next_check_at": check["next_check_at"]}  # fmt: skip


async def update_ticket_tool(state: KBState, ticket_key: str, title: str | None = None,
                             description: str | None = None, severity: str | None = None) -> dict:  # fmt: skip
    with db.session() as s:
        t = T.update_ticket(s, ticket_key, title=title, description=description, severity=severity)
        detail = T.ticket_detail(s, t)
        summary = T.ticket_summary(s, t)
    state.touched.add(t.key)
    hub.publish("ticket.updated", {"ticket": summary, "by": state.person_id})
    await state.push({"type": "ui.ticket", "ticket": detail})
    return {"ok": True, "ticket_key": t.key, "severity": t.severity, "title": t.title}


async def assign_ticket(state: KBState, ticket_key: str, add_names: list[str] | None = None,
                        remove_names: list[str] | None = None) -> dict:  # fmt: skip
    with db.session() as s:
        t = T.assign(s, ticket_key, add_names or [], remove_names or [])
        detail = T.ticket_detail(s, t)
        summary = T.ticket_summary(s, t)
    state.touched.add(t.key)
    hub.publish("ticket.updated", {"ticket": summary, "by": state.person_id, "assigned": True})
    await state.push({"type": "ui.ticket", "ticket": detail})
    return {"ok": True, "ticket_key": t.key, "assignees": [a["name"] for a in detail["assignees"]]}


async def end_shift_tool(state: KBState, summary: str = "") -> dict:
    if state.shift_session_id is None:
        return {"error": "no shift session"}
    with db.session() as s:
        ss = end_shift(s, state.shift_session_id, summary)
        out = shift_dict(ss, s.get(Person, ss.person_id))
    state.shift_ended = True
    hub.publish("shift.ended", {"shift_session": out})
    await state.push({"type": "ui.shift_ended", "summary": summary})
    closed = closed_this_shift(state)
    if closed:
        return {"ok": True, "note": "shift ended. In the user's language, first say by machine and problem who closed "
                f"their tickets ({'; '.join(closed)}), e.g. 'The 4B vibration you filed is closed: Imran replaced the "
                "spindle bearing.', then a short goodbye. Two short sentences max."}  # fmt: skip
    return {"ok": True, "note": "shift ended; say one short goodbye line"}


HANDLERS: dict[str, Callable[..., Awaitable[dict]]] = {
    "show_tickets": show_tickets,
    "focus_ticket": focus_ticket,
    "update_draft": update_draft,
    "request_photo": request_photo,
    "file_ticket": file_ticket,
    "discard_draft": discard_draft,
    "add_check": add_check_tool,
    "update_ticket": update_ticket_tool,
    "assign_ticket": assign_ticket,
    "end_shift": end_shift_tool,
}


async def run_tool(state: KBState, name: str, args: dict) -> dict:
    handler = HANDLERS.get(name)
    if not handler:
        return {"error": f"unknown tool {name}"}
    try:
        result = await handler(state, **(args or {}))
    except DomainError as e:
        result = {"error": str(e)}
        if "operators can't close" in str(e):
            await state.push({"type": "ui.notice", "kind": "warning", "message": "Operators can't close tickets"})
    except TypeError as e:
        logger.warning(f"tool {name} bad args {args}: {e}")
        result = {"error": f"bad arguments: {e}"}
    state.tool_log.append({"name": name, "args": args, "result": result})
    logger.info(f"tool {name}({args}) -> {result}")
    return result


# ---- handover -----------------------------------------------------------------------

def handover_tickets(state: KBState) -> list[str]:
    """Non-closed tickets this person reported, is assigned to, or Checked during this ShiftSession."""
    with db.session() as s:
        ss = s.get(ShiftSession, state.shift_session_id) if state.shift_session_id else None
        since = ss.started_at if ss else db.now()
        keys = set(state.touched)
        for t in s.exec(select(Ticket).where(Ticket.status != "closed")).all():
            if t.reporter_id == state.person_id and t.created_at >= since:
                keys.add(t.key)
        for a in s.exec(select(TicketAssignee).where(TicketAssignee.person_id == state.person_id)).all():
            t = s.get(Ticket, a.ticket_id)
            if t and t.status != "closed":
                keys.add(t.key)
        for c in s.exec(select(Check).where(Check.author_id == state.person_id, Check.created_at >= since)).all():
            keys.add(s.get(Ticket, c.ticket_id).key)
        return [k for k in sorted(keys) if T.get_ticket(s, k).status != "closed"]


def closed_this_shift(state: KBState) -> list[str]:
    """Tickets this person filed or touched this shift that someone has since closed."""
    with db.session() as s:
        ss = s.get(ShiftSession, state.shift_session_id) if state.shift_session_id else None
        since = ss.started_at if ss else db.now()
        out = []
        for t in s.exec(select(Ticket).where(Ticket.status == "closed", Ticket.closed_at >= since)).all():
            if t.key in state.touched or t.reporter_id == state.person_id:
                last = checks_of_key(s, t)
                who = last.author_id and s.get(Person, last.author_id)
                out.append(f"{t.key} ({t.machine_code} {t.title}) closed by {who.name if who else 'someone'}")
        return out


def checks_of_key(s, t: Ticket) -> Check:
    return s.exec(select(Check).where(Check.ticket_id == t.id).order_by(Check.created_at.desc())).first()

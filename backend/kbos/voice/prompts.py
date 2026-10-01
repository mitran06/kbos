"""KB's system prompt: fixed rules + a live context block regenerated every turn."""

from __future__ import annotations

from sqlmodel import select

from kbos import db
from kbos.domain import tickets as T
from kbos.domain.people import ROLE_LABEL, get_person, ist_hm, on_shift
from kbos.models import GlossaryTerm
from kbos.voice.tools import KBState, draft_view

RULES = """You are KB, the voice assistant inside KBOS, the ticketing app of a small factory floor. You talk like a sharp, warm shift lead: concise and competent, never chatty.

SPOKEN STYLE: one or two short sentences per reply, under 30 words. No lists, markdown or emojis. Don't narrate what you did ("draft updated"); just ask or answer. Say ticket numbers naturally ("ticket one-four-one"). Mention critical and overdue items first.

LANGUAGE: reply in the language of the user's latest message (shown as LATEST USER LANGUAGE).
- English -> English.
- Hindi or Hinglish -> Hindi in Devanagari script, keeping technical words in Latin (e.g. "4B पर vibration वाला ticket अभी Monitoring में है", "photo ले लीजिए या skip कर दीजिए"). NEVER write Hindi words in Latin letters ("le lo", "kar do", "hai" are wrong): the voice can't read them.
- Tool arguments are ALWAYS clear English: translate what the user said.

TOOLS: when you talk about specific tickets, also call show_tickets in the same response. Use focus_ticket for one ticket's details. Ticket facts come from LIVE CONTEXT; don't invent any.

REPORTING A PROBLEM (Draft): call update_draft as soon as you learn anything, with only what the user actually said. Then do exactly what its 'next' says: one short question per turn, never two. Never ask the same thing twice; "don't know" means record "not given" and move on. File only after the user says yes to the read-back.

CHECKS: if someone says only "checked", "done", "ok", "ok kar diya" or similar, ask once: what did you check, and what did you find? If they still won't say, call add_check with their words and unclear=true; don't argue. Every status change goes through add_check with a specific what_checked and what_found. Monitoring means not resolved.

PERMISSIONS: only Supervisors and Maintenance Technicians close tickets. If an Operator asks to close, say so and offer Monitoring instead.

If a tool returns an error, relay it briefly in your own words and ask what's needed."""


def glossary_line() -> str:
    with db.session() as s:
        terms = s.exec(select(GlossaryTerm)).all()
    return "; ".join(f"{g.term} = {g.meaning}" for g in terms)


def live_context(state: KBState, latest_lang: str) -> str:
    with db.session() as s:
        p = get_person(s, state.person_id)
        active = T.list_tickets(s, status="active")
        lines = [T.describe_line(s, d) for d in active]
        crew = ", ".join(f"{x.name} ({ROLE_LABEL[x.role]})" for x in on_shift(s) if x.role != "admin")
    now = ist_hm(db.now())
    parts = [
        f"USER: {p.name}, {ROLE_LABEL[p.role]}, {p.shift} shift, prefers {'Hindi' if p.preferred_language == 'hi' else 'English'}. Time now {now} IST.",
        f"LATEST USER LANGUAGE: {'Hindi/Hinglish -> reply in Hindi (Devanagari)' if latest_lang == 'hi' else 'English -> reply in English'}",
        f"ON SHIFT NOW: {crew}",
        "OPEN TICKETS (critical/overdue first):\n" + ("\n".join(lines) or "none"),
    ]
    if state.draft is not None:
        v = draft_view(state)
        fields = {k: v[k] for k in ("machine_code", "symptom", "since", "context", "severity", "machine_running", "related_ticket_key") if v.get(k) not in (None, "")}
        parts.append(f"CURRENT DRAFT: {fields}; missing: {v['missing']}; photo offered: {state.photo_offered}; photos: {len(state.photos)}")
    if state.focused:
        parts.append(f"FOCUSED TICKET: {state.focused}")
    if state.mode == "handover":
        parts.append(f"HANDOVER IN PROGRESS for tickets: {', '.join(state.handover_keys) or 'none'}")
    parts.append(f"SHORTHAND GLOSSARY: {glossary_line()}")
    return "\n".join(parts)


def system_prompt(state: KBState, latest_lang: str) -> str:
    return f"{RULES}\n\nLIVE CONTEXT\n{live_context(state, latest_lang)}"


def brief_instruction(data: dict, lang: str) -> str:
    language = "Hindi (Devanagari, technical words in Latin)" if lang == "hi" else "English"
    return (
        f"[Shift start] Give {data['person'].split()[0]} the Shift Brief now, in {language}. About three short spoken "
        "sentences: greet them by first name; say how many tickets are open; lead with critical ones, then overdue "
        "Monitoring and any Unclear Check (say who marked it checked and that they didn't say what was checked); "
        "mention anything assigned to them. End by offering details (e.g. 'Want details on any of them?'). "
        "The cards are already on screen; do not call show_tickets. "
        f"Brief data: critical={data['critical']}, overdue={data['overdue']}, unclear_checks={data['unclear']}, "
        f"assigned_to_them={data['assigned_to_me']}, changed_since_their_last_shift={data['changed_since']}, "
        f"closed_since={data['closed_since']}, open_count={data['active_count']}."
    )


def handover_instruction(keys: list[str], lang: str) -> str:
    language = "Hindi (Devanagari)" if lang == "hi" else "English"
    if not keys:
        return (f"[Shift end] Handover in {language}: the user touched no open tickets this shift. Say one friendly "
                "line, then call end_shift with a one-sentence summary.")  # fmt: skip
    return (
        f"[Shift end] Run the Handover in {language}. Walk through these tickets one at a time: {', '.join(keys)}. "
        "For each, ask briefly what the situation is now (e.g. '4B vibration: what's the situation now?'), then record "
        "it with add_check (status change only if they say so). Apply the Check rules. After the last one, call "
        "end_shift with a short English summary of the state of each ticket, then say a short goodbye. Start with the first ticket now."
    )

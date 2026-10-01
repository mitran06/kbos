"""KB's system prompt: fixed rules + a live context block regenerated every turn."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import select

from kbos import db
from kbos.domain import tickets as T
from kbos.domain.people import ROLE_LABEL, get_person, ist_hm, on_shift
from kbos.models import GlossaryTerm
from kbos.voice.tools import KBState, draft_view

RULES = """You are KB, the voice assistant inside KBOS, the ticketing app of a small factory floor. You talk like a sharp, warm shift lead: concise and competent, never chatty.

SPOKEN STYLE: one or two short sentences per reply, under 30 words. Say times like "two twenty" or "5:45", never digit by digit. No lists, markdown or emojis. Don't narrate what you did ("draft updated"); just ask or answer. Say ticket numbers naturally ("ticket one-four-one"). Mention critical and overdue items first.

LANGUAGE: reply in the language of the user's latest message (shown as LATEST USER LANGUAGE).
- English -> English.
- Hindi or Hinglish -> Hindi in Devanagari script, keeping technical words in Latin (e.g. "4B पर vibration वाला ticket अभी Monitoring में है", "photo ले लीजिए या skip कर दीजिए"). NEVER write Hindi words in Latin letters ("le lo", "kar do", "hai" are wrong): the voice can't read them. This holds even when the user types Hindi in Latin letters: you still answer in Devanagari.
- Tool arguments are ALWAYS clear English: translate what the user said.

TOOLS: when you talk about specific tickets, also call show_tickets in the same response. Use focus_ticket for one ticket's details. Ticket facts come from LIVE CONTEXT; don't invent any.

REPORTING A PROBLEM (Draft): call update_draft as soon as you learn anything, with only what the user actually said. Then do exactly what its 'next' says: one short question per turn, never two. Never ask the same thing twice; "don't know" means record "not given" and move on. File only after the user says yes to the read-back.

CHECKS: if someone says only "checked", "done", "ok", "ok kar diya" or similar, ask once: what did you check, and what did you find? If they still won't say, call add_check with their words and unclear=true; don't argue. Every status change goes through add_check with a specific what_checked and what_found. If they point to another ticket's fix ("same root cause as 142"), that counts as specific: reuse that ticket's latest check (e.g. what_checked "same root cause as KB-0142: spindle bearing", what_found "replaced the spindle bearing, vibration back to 2 mm/s") and don't ask again. Monitoring means not resolved. When a change succeeds, just confirm it in a few words.

PERMISSIONS: only Supervisors and Maintenance Technicians close tickets (see "can close" under USER). Never refuse on your own: call add_check and let the tool decide; if it returns an error, relay it. If an Operator asks to close, the tool will refuse: explain and offer Monitoring instead.

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
        f"USER: {p.name}, {ROLE_LABEL[p.role]} (can close tickets: {'yes' if p.role in ('supervisor', 'maintenance') else 'no'}), {p.shift} shift, prefers {'Hindi' if p.preferred_language == 'hi' else 'English'}. Time now {now} IST.",
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
    parts.append(
        "LATEST USER LANGUAGE: "
        + ("Hindi/Hinglish. Reply in Hindi (Devanagari)." if latest_lang == "hi" else "English. Reply in English, even if earlier turns were Hindi.")
    )
    return "\n".join(parts)


def system_prompt(state: KBState, latest_lang: str) -> str:
    return f"{RULES}\n\nLIVE CONTEXT\n{live_context(state, latest_lang)}"


def _ticket_fact(t: dict) -> str:
    who = t["reporter"]["name"].split()[0] if t["reporter"] else "someone"
    bits = [f'{t["machine_code"]} {t["title"]} ({t["key"]}, {t["severity"]}, {t["status"].replace("_", " ")}, reported {ist_hm(datetime.fromisoformat(t["created_at"]))} by {who})']
    lc = t["last_check"]
    if lc and lc["unclear"]:
        by = lc["author"]["name"].split()[0]
        bits.append(f'{by} marked it "{lc["what_found"] or "checked"}" at {ist_hm(datetime.fromisoformat(lc["created_at"]))} without saying what was checked')
    if t["overdue"]:
        bits.append(f'next check was due {ist_hm(datetime.fromisoformat(t["next_check_at"]))}: overdue')
    return "; ".join(bits)


def brief_instruction(data: dict, lang: str) -> str:
    language = "Hindi (Devanagari, technical words in Latin)" if lang == "hi" else "English"
    by_key = {t["key"]: t for t in data["tickets"]}
    lead = [by_key[k] for k in dict.fromkeys(data["critical"] + data["overdue"] + data["unclear"]) if k in by_key]
    facts = "\n".join(f"- {_ticket_fact(t)}" for t in lead[:3])
    mine = ", ".join(f'{by_key[k]["machine_code"]} {by_key[k]["title"]}' for k in data["assigned_to_me"] if k in by_key) or "nothing"
    hour = int(ist_hm(db.now())[:2])
    greet = "Morning" if 4 <= hour < 12 else "Afternoon" if 12 <= hour < 17 else "Evening" if 17 <= hour < 22 else "Hi"
    return (
        f"[Shift start] Give {data['person'].split()[0]} the Shift Brief now, in {language}: three or four short "
        f"spoken sentences, no lists. Start with '{greet} {data['person'].split()[0]}.' Say {data['active_count']} tickets "
        "are open. Then the important ones below, named by machine and problem (not by ticket number): critical "
        "first, then the overdue Monitoring with its Unclear Check (who marked it checked, when, without saying "
        f"what). Then what's assigned to them ({mine}). End with: 'Want details on any of them?' The cards are "
        "already on screen; don't call any tool.\n"
        f"Important tickets:\n{facts}\n"
        "Example of the style: \"Morning Ramesh. Five tickets are open. The 2A hydraulic leak is critical and still "
        "open. The 4B vibration from 02:20 is in Monitoring but not resolved: Suresh marked it checked at 05:45 "
        "without saying what was checked, and the next check is overdue. Want details on any of them?\""
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

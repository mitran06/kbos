"""Domain rules (PLAN §4) against the seeded demo world."""

from datetime import timedelta

import pytest
from sqlmodel import select

from kbos import db
from kbos.domain.brief import brief_data
from kbos.domain.checks import add_check, is_bare
from kbos.domain.people import current_shift, list_people, match_person
from kbos.domain.related import related_candidates
from kbos.domain.tickets import (
    assign,
    assignees_of,
    file_ticket,
    get_ticket,
    is_overdue,
    links_of,
    list_tickets,
    next_key,
    normalize_key,
    ticket_summary,
)
from kbos.models import Check, Person, Photo, Ticket, TicketAssignee

SEED_KEYS = {
    "KB-0119",
    "KB-0123",
    "KB-0127",
    "KB-0131",
    "KB-0134",
    "KB-0136",
    "KB-0138",
    "KB-0140",
    "KB-0141",
}
ACTIVE_KEYS = {"KB-0134", "KB-0136", "KB-0138", "KB-0140", "KB-0141"}


def close_to(a, b, tol=timedelta(seconds=5)) -> bool:
    return abs(a - b) <= tol


def names(s, t) -> set[str]:
    return {p.name.split()[0] for p in assignees_of(s, t)}


def add_ticket(s, key, machine, title, status="open", **kw) -> Ticket:
    t_now = db.now()
    t = Ticket(key=key, title=title, machine_code=machine, status=status, symptom=kw.pop("symptom", title),
               created_at=kw.pop("created_at", t_now), updated_at=t_now, **kw)  # fmt: skip
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


# -- status changes need a Check -----------------------------------------------------


@pytest.mark.parametrize(
    "checked,found",
    [
        ("", ""),
        ("checked", "ok"),
        ("the spindle bearing", ""),
        ("", "Checked"),
        ("done", "found it loose"),
    ],
)
def test_status_change_without_a_real_check_is_refused(s, people, checked, found):
    with pytest.raises(Exception, match="needs a check") as ei:
        add_check(
            s, "KB-0136", people["kavita"], checked, found, new_status="in_progress"
        )
    assert type(ei.value).__name__ == "DomainError"
    s.expire_all()
    t = get_ticket(s, "KB-0136")
    assert t.status == "open"
    assert s.exec(select(Check).where(Check.ticket_id == t.id)).all() == []


def test_bare_check_with_unclear_true_is_recorded(s, people):
    t, c = add_check(
        s,
        "0141",
        people["kavita"],
        "checked",
        "ok",
        new_status="monitoring",
        unclear=True,
    )
    assert c.id is not None and c.unclear is True
    assert c.status_to is None  # already monitoring: no status change
    assert c.author_id == people["kavita"].id
    assert t.status == "monitoring"


def test_check_with_status_change_records_from_and_to(s, people):
    t, c = add_check(s, "136", people["imran"], "light curtain receiver alignment", "receiver loose, re-aligned",
                     new_status="in progress")  # fmt: skip
    assert t.status == "in_progress"
    assert (c.status_from, c.status_to) == ("open", "in_progress")
    assert c.unclear is False
    assert t.updated_at == c.created_at


def test_check_without_status_change_keeps_status(s, people):
    t, c = add_check(
        s,
        "KB-0134",
        people["imran"],
        "belt tension",
        "still low, new belt arrives tomorrow",
    )
    assert t.status == "in_progress"
    assert c.status_to is None and c.status_from is None


def test_unknown_status_is_refused(s, people):
    with pytest.raises(Exception, match="status must be one of"):
        add_check(
            s, "KB-0136", people["kavita"], "x valve", "y found", new_status="parked"
        )


# -- close permissions ---------------------------------------------------------------


@pytest.mark.parametrize("word", ["closed", "close", "resolved", "done"])
def test_operator_cannot_close(s, people, word):
    with pytest.raises(Exception) as ei:
        add_check(s, "KB-0141", people["ramesh"], "spindle runout with a dial gauge", "0.01 mm, within spec",
                  new_status=word)  # fmt: skip
    msg = str(ei.value).lower()
    assert "operator" in msg and "monitoring" in msg
    s.expire_all()
    assert get_ticket(s, "KB-0141").status == "monitoring"


def test_operator_can_put_in_monitoring(s, people):
    t, _ = add_check(s, "KB-0136", people["ramesh"], "watched the light curtain for 10 min", "tripped once",
                     new_status="monitoring")  # fmt: skip
    assert t.status == "monitoring"
    assert t.monitoring_owner_id == people["ramesh"].id


@pytest.mark.parametrize("who", ["kavita", "imran", None])
def test_supervisor_maintenance_and_admin_can_close(s, people, who):
    actor = people[who] if who else None
    t, c = add_check(s, "KB-0141", actor, "spindle runout and tool holder seating",
                     "tool holder not seated after TC; reseated, vibration back to 1.8 mm/s", new_status="closed")  # fmt: skip
    assert t.status == "closed"
    assert t.closed_at is not None and close_to(t.closed_at, db.now())
    assert t.next_check_at is None
    assert (c.status_from, c.status_to) == ("monitoring", "closed")
    assert c.author_id == (actor.id if actor else None)
    assert not is_overdue(t)


def test_reopen_clears_closed_at(s, people):
    add_check(
        s,
        "KB-0127",
        people["kavita"],
        "chuck grip test",
        "parts slipping again",
        new_status="open",
    )
    s.expire_all()
    t = get_ticket(s, "KB-0127")
    assert t.status == "open" and t.closed_at is None


# -- unclear forcing -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["checked", "Checked.", "ok", "OK!", "done", "", "  ", "theek hai", "ok kar diya"],
)
def test_bare_words_are_bare(text):
    assert is_bare(text)


@pytest.mark.parametrize(
    "text",
    ["checked the auto-drain valve", "bearing temperature 71 C", "found it loose"],
)
def test_specific_text_is_not_bare(text):
    assert not is_bare(text)


@pytest.mark.parametrize(
    "checked,found",
    [("checked", "ok"), ("done", "done"), ("", "Checked"), ("checked", "")],
)
def test_bare_check_stays_unclear(s, people, checked, found):
    _, c = add_check(s, "KB-0134", people["imran"], checked, found, unclear=True)
    assert c.unclear is True


def test_specific_check_is_not_unclear(s, people):
    _, c = add_check(
        s,
        "KB-0134",
        people["imran"],
        "belt tension at the drive pulley",
        "re-tensioned to spec",
    )
    assert c.unclear is False


def test_bare_text_forces_unclear_even_when_mixed(s, people):
    # specific what_checked but a bare what_found is still unclear
    _, c = add_check(
        s,
        "KB-0134",
        people["imran"],
        "belt tension at the drive pulley",
        "ok",
        unclear=True,
    )
    assert c.unclear is True
    s.expire_all()
    assert ticket_summary(s, get_ticket(s, "KB-0134"))["unclear"] is True


# -- monitoring defaults and overdue ----------------------------------------------------


def test_monitoring_defaults_to_two_hours_owned_by_actor(s, people):
    t, c = add_check(s, "KB-0136", people["kavita"], "light curtain alignment", "slightly off, re-aligned",
                     new_status="monitoring")  # fmt: skip
    assert t.status == "monitoring"
    assert close_to(t.next_check_at, db.now() + timedelta(hours=2))
    assert c.next_check_at == t.next_check_at
    assert t.monitoring_owner_id == people["kavita"].id
    assert not is_overdue(t)


def test_monitoring_custom_next_check(s, people):
    t, _ = add_check(s, "KB-0136", people["imran"], "receiver lens", "dusty, cleaned it", new_status="monitoring",
                     next_check_minutes=30)  # fmt: skip
    assert close_to(t.next_check_at, db.now() + timedelta(minutes=30))
    assert t.monitoring_owner_id == people["imran"].id


def test_check_on_monitoring_ticket_can_push_next_check(s, people):
    t, c = add_check(s, "KB-0141", people["imran"], "vibration reading at the guard", "4.4 mm/s, unchanged",
                     next_check_minutes=60)  # fmt: skip
    assert t.status == "monitoring"
    assert close_to(t.next_check_at, db.now() + timedelta(hours=1))
    assert c.next_check_at == t.next_check_at
    assert not is_overdue(t)


def test_overdue_is_computed(s):
    t = get_ticket(s, "KB-0138")
    assert t.status == "monitoring" and not is_overdue(t)
    t.next_check_at = db.now() - timedelta(minutes=1)
    assert is_overdue(t)
    assert not is_overdue(t, at=db.now() - timedelta(minutes=2))
    t.status = "in_progress"
    assert not is_overdue(t)  # only Monitoring can be overdue
    t.status, t.next_check_at = "monitoring", None
    assert not is_overdue(t)


def test_leaving_monitoring_clears_next_check(s, people):
    t, _ = add_check(s, "KB-0141", people["imran"], "spindle bearing", "bearing noisy, replacing",
                     new_status="in_progress")  # fmt: skip
    assert t.next_check_at is None and not is_overdue(t)


def test_admin_monitoring_always_has_an_owner(s):
    t, _ = add_check(s, "KB-0136", None, "reviewed trip log", "one trip per hour, sensor suspected",
                     new_status="monitoring")  # fmt: skip
    assert t.monitoring_owner_id is not None


# -- related tickets -----------------------------------------------------------------


def test_vibration_on_4b_ranks_kb0141_first(s):
    ranked = related_candidates(s, "4b", "4B is vibrating badly after the TC")
    assert ranked and ranked[0][1].key == "KB-0141"
    shaking = related_candidates(s, "4B", "the machine is shaking")
    assert shaking[0][1].key == "KB-0141"


def test_related_excludes_old_closed_and_other_machines(s):
    old = add_ticket(s, "KB-0100", "4B", "Vibration at spindle", status="closed",
                     created_at=db.now() - timedelta(days=10), closed_at=db.now() - timedelta(days=8))  # fmt: skip
    recent = add_ticket(s, "KB-0101", "4B", "Vibration on tailstock", status="closed",
                        created_at=db.now() - timedelta(days=3), closed_at=db.now() - timedelta(days=2))  # fmt: skip
    other = add_ticket(s, "KB-0102", "5A", "Vibration on 5A spindle")
    keys = [t.key for _, t in related_candidates(s, "4B", "heavy vibration on 4B")]
    assert keys[0] == "KB-0141"  # open beats recently closed
    assert recent.key in keys
    assert old.key not in keys
    assert other.key not in keys
    assert "KB-0127" not in keys  # 4B but a chuck-jaw problem: no overlap


def test_related_exclude_id_and_no_overlap(s):
    t = get_ticket(s, "KB-0141")
    assert all(
        r.key != "KB-0141"
        for _, r in related_candidates(s, "4B", "vibration", exclude_id=t.id)
    )
    assert related_candidates(s, "4B", "paint scratched on the door") == []


# -- filing and auto-assignment ------------------------------------------------------------


def test_next_key_is_kb0142(s):
    assert next_key(s) == "KB-0142"


def test_file_ticket_assigns_links_and_attaches(s, people):
    s.add(Photo(session_id="sess-1", path="a.jpg", created_at=db.now()))
    s.add(Photo(session_id="sess-1", path="b.jpg", created_at=db.now()))
    s.add(Photo(session_id="other", path="c.jpg", created_at=db.now()))
    s.commit()
    t = file_ticket(s, {"machine_code": "4b", "symptom": "vibration getting worse", "severity": "high",
                        "since": "after lunch", "machine_running": True},
                    people["ramesh"].id, related_key="one four one", session_id="sess-1",
                    transcript=[{"who": "user", "text": "4B phir se vibrate kar raha hai", "lang": "hi"}],
                    language="hi")  # fmt: skip
    assert t.key == "KB-0142"
    assert t.status == "open" and t.machine_code == "4B" and t.severity == "high"
    assert t.title == "Vibration getting worse on 4B"
    assert t.context == "not given" and t.since_text == "after lunch"
    assert t.reporter_id == people["ramesh"].id
    assert names(s, t) == {"Imran"}
    assert [r.key for r in links_of(s, t)] == ["KB-0141"]
    assert "KB-0142" in [r.key for r in links_of(s, get_ticket(s, "KB-0141"))]
    attached = s.exec(select(Photo).where(Photo.ticket_id == t.id)).all()
    assert sorted(p.path for p in attached) == ["a.jpg", "b.jpg"]
    d = ticket_summary(s, t)
    assert d["photo_count"] == 2 and d["related_keys"] == ["KB-0141"]
    assert next_key(s) == "KB-0143"


def test_file_critical_adds_on_shift_supervisor(s, people):
    t = file_ticket(s, {"machine_code": "6B", "symptom": "wheel guard cracked", "severity": "CRITICAL"},
                    people["ramesh"].id)  # fmt: skip
    assert t.severity == "critical"
    assert names(s, t) == {"Imran", "Kavita"}


@pytest.mark.parametrize(
    "draft,msg",
    [
        ({"symptom": "noise"}, "needs a machine"),
        ({"machine_code": "9Z", "symptom": "noise"}, "needs a machine"),
        ({"machine_code": "4B"}, "needs a symptom"),
        ({"machine_code": "4B", "symptom": "not given"}, "needs a symptom"),
    ],
)
def test_file_ticket_requires_machine_and_symptom(s, people, draft, msg):
    with pytest.raises(Exception, match=msg):
        file_ticket(s, draft, people["ramesh"].id)


def test_file_ticket_bad_severity_falls_back_to_medium(s, people):
    t = file_ticket(
        s,
        {"machine_code": "3C", "symptom": "belt squeal", "severity": "urgent-ish"},
        people["ramesh"].id,
    )
    assert t.severity == "medium"


def test_file_ticket_auto_assigns_current_crew_day_and_night(fs):
    """The seeded current crew's Maintenance Technician is assigned at day and at night."""
    imran = fs.exec(select(Person).where(Person.name == "Imran Shaikh")).one()
    ramesh = fs.exec(select(Person).where(Person.name == "Ramesh Yadav")).one()
    t = file_ticket(
        fs,
        {
            "machine_code": "2A",
            "symptom": "oil leak getting worse",
            "severity": "critical",
        },
        ramesh.id,
    )
    assert names(fs, t) == {"Imran", "Kavita"}
    assert imran.shift == current_shift()


# -- keys ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "one four one",
        "0141",
        "141",
        "KB-0141",
        "kb 141",
        "kb-one-four-one",
        "Oh one four one",
    ],
)
def test_normalize_key(raw):
    assert normalize_key(raw) == "KB-0141"


@pytest.mark.parametrize("raw", ["", "abc", "the vibration"])
def test_normalize_key_rejects_non_numbers(raw):
    with pytest.raises(Exception, match="not a ticket number"):
        normalize_key(raw)


def test_get_ticket_unknown(s):
    with pytest.raises(Exception, match="there is no ticket KB-0999"):
        get_ticket(s, "999")


# -- assign -----------------------------------------------------------------------------


def test_assign_with_names(s):
    t = assign(s, "KB-0136", ["Arjun", "imran"], [])
    assert names(s, t) == {"Arjun", "Imran"}
    t = assign(s, "0136", ["Kavitha"], ["arjun"])  # fuzzy spelling
    assert names(s, t) == {"Imran", "Kavita"}


def test_assign_keeps_existing_and_dedupes(s):
    t = assign(s, "KB-0140", ["Arjun", "Imran"], [])  # Arjun already assigned
    assert names(s, t) == {"Arjun", "Suresh", "Imran"}
    rows = s.exec(select(TicketAssignee).where(TicketAssignee.ticket_id == t.id)).all()
    assert len(rows) == 3


def test_assign_unknown_name(s):
    with pytest.raises(Exception, match="nobody called Zubin"):
        assign(s, "KB-0136", ["Zubin"], [])
    with pytest.raises(Exception, match="nobody called"):
        assign(s, "KB-0136", ["Neha"], [])  # the Admin is not assignable


def test_assign_ambiguous_name(s):
    s.add(Person(name="Ramesh Kumar", initials="RK", role="maintenance", shift="day"))
    s.commit()
    with pytest.raises(Exception, match="ambiguous") as ei:
        assign(s, "KB-0136", ["Ramesh"], [])
    assert "Ramesh Yadav" in str(ei.value) and "Ramesh Kumar" in str(ei.value)
    s.expire_all()
    assert names(s, get_ticket(s, "KB-0136")) == set()  # nothing changed


def test_match_person_variants(s):
    assert [p.name for p in match_person(s, "IS")] == ["Imran Shaikh"]
    assert [p.name for p in match_person(s, "Patil")] == ["Suresh Patil"]
    assert [p.name for p in match_person(s, "Imraan")] == ["Imran Shaikh"]


# -- brief -------------------------------------------------------------------------------


def test_brief_leads_with_critical_then_the_case_study(s, people):
    b = brief_data(s, people["ramesh"].id)
    keys = [d["key"] for d in b["tickets"]]
    assert keys[:2] == ["KB-0140", "KB-0141"]
    assert set(keys) == ACTIVE_KEYS and len(keys) == len(ACTIVE_KEYS)
    assert b["critical"] == ["KB-0140"]
    assert b["overdue"] == ["KB-0141"]
    assert b["unclear"] == ["KB-0141"]
    assert b["active_count"] == 5
    assert b["assigned_to_me"] == []
    assert b["closed_since"] == []
    assert b["person"] == "Ramesh Yadav"
    t141 = b["tickets"][1]
    assert t141["overdue"] and t141["unclear"] and t141["last_check"]["unclear"]


def test_brief_assigned_to_me(s, people):
    b = brief_data(s, people["arjun"].id)
    assert set(b["assigned_to_me"]) == {"KB-0138", "KB-0140", "KB-0141"}
    assert brief_data(s, people["imran"].id)["assigned_to_me"] == ["KB-0134"]


def test_brief_unclear_only_since_last_shift(s, people):
    # A shift that ended after Suresh's unclear check: nothing unclear is new for this person.
    from kbos.models import ShiftSession

    s.add(ShiftSession(person_id=people["kavita"].id, started_at=db.now() - timedelta(hours=2),
                       ended_at=db.now() - timedelta(hours=1)))  # fmt: skip
    s.commit()
    b = brief_data(s, people["kavita"].id)
    assert b["unclear"] == []
    assert b["overdue"] == ["KB-0141"]  # still overdue, still called out
    assert [d["key"] for d in b["tickets"]][:2] == ["KB-0140", "KB-0141"]


# -- listing ------------------------------------------------------------------------------


def test_list_tickets_sorting_and_filters(s):
    active = [d["key"] for d in list_tickets(s, status="active")]
    assert active == ["KB-0140", "KB-0141", "KB-0136", "KB-0138", "KB-0134"]
    assert {d["key"] for d in list_tickets(s)} == SEED_KEYS
    assert [d["key"] for d in list_tickets(s, machine="4b")] == ["KB-0141", "KB-0127"]
    assert [d["key"] for d in list_tickets(s, q="vibration")] == ["KB-0141"]
    assert {d["key"] for d in list_tickets(s, status="closed")} == {
        "KB-0119",
        "KB-0123",
        "KB-0127",
        "KB-0131",
    }


# -- seed relative-time correctness ----------------------------------------------------------


def test_seed_case_study_times(fs, frozen_client):
    now = frozen_client.now
    assert db.now() == now
    t = get_ticket(fs, "KB-0141")
    assert t.created_at == now - timedelta(hours=5, minutes=40)
    assert t.status == "monitoring" and t.severity == "high"
    assert t.next_check_at == now - timedelta(minutes=15)
    assert is_overdue(t)
    assert t.context == "right after a tool change"
    assert t.telemetry_snapshot and t.telemetry_snapshot["current"][
        "vibration_mm_s"
    ] == pytest.approx(4.5, abs=0.2)
    assert t.transcript and all(m["lang"] == "en" for m in t.transcript)
    reporter, owner = (
        fs.get(Person, t.reporter_id),
        fs.get(Person, t.monitoring_owner_id),
    )
    assert reporter.name == "Priya Nair" and owner.name == "Suresh Patil"
    (c,) = fs.exec(select(Check).where(Check.ticket_id == t.id)).all()
    assert c.created_at == now - timedelta(hours=2, minutes=15)
    assert (c.what_checked, c.what_found, c.unclear) == ("", "Checked", True)
    assert (c.status_from, c.status_to) == ("open", "monitoring")
    assert c.next_check_at == now - timedelta(minutes=15)
    assert fs.get(Person, c.author_id).name == "Suresh Patil"


def test_seed_background_tickets(fs, frozen_client):
    now = frozen_client.now
    assert set(fs.exec(select(Ticket.key)).all()) == SEED_KEYS
    t138 = get_ticket(fs, "KB-0138")
    assert t138.status == "monitoring" and not is_overdue(t138)
    assert t138.next_check_at == now + timedelta(hours=2)
    t140 = get_ticket(fs, "KB-0140")
    assert t140.severity == "critical" and t140.status == "open"
    assert t140.created_at == now - timedelta(hours=3)
    assert get_ticket(fs, "KB-0127").closed_at == now - timedelta(days=3)
    assert names(fs, get_ticket(fs, "KB-0136")) == set()
    assert next_key(fs) == "KB-0142"


def test_seed_current_crew_on_shift(fs, frozen_client):
    cur = current_shift()
    assert cur == ("day" if frozen_client.now.hour == 2 else "night")
    on = {
        d["first_name"]
        for d in list_people(fs, include_admin=True)
        if d["on_shift_now"]
    }
    assert on == {"Ramesh", "Kavita", "Imran", "Neha"}
    shifts = {p.name.split()[0]: p.shift for p in fs.exec(select(Person)).all()}
    assert shifts["Priya"] == shifts["Suresh"] == shifts["Arjun"] != cur

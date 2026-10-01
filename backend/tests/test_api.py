"""REST (PLAN §5.1) and /ws broadcasts (§5.2) against the seeded demo world."""

from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from kbos import db
from kbos.domain.tickets import file_ticket
from kbos.models import Person
from kbos.realtime import hub
from kbos.telemetry import telemetry

from .conftest import png_bytes


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def person_id(client, first: str) -> int:
    return next(
        p["id"]
        for p in client.get("/api/people", params={"all": 1}).json()
        if p["first_name"] == first
    )


# -- people and shifts -----------------------------------------------------------------


def test_people_excludes_admin_and_lists_on_shift_first(client):
    people = client.get("/api/people").json()
    assert len(people) == 6
    assert all(p["role"] != "admin" for p in people)
    assert [p["first_name"] for p in people[:3]] == ["Ramesh", "Kavita", "Imran"]
    assert all(p["on_shift_now"] for p in people[:3])
    assert not any(p["on_shift_now"] for p in people[3:])
    assert {p["first_name"] for p in people[3:]} == {"Priya", "Suresh", "Arjun"}
    assert people[2]["role_label"] == "Maintenance Technician"

    everyone = client.get("/api/people", params={"all": 1}).json()
    assert len(everyone) == 7
    assert [p["name"] for p in everyone if p["role"] == "admin"] == ["Neha Kulkarni"]


def test_people_crew_on_shift_at_day_and_night(frozen_client):
    people = frozen_client.get("/api/people").json()
    on = [p["first_name"] for p in people if p["on_shift_now"]]
    assert on == ["Ramesh", "Kavita", "Imran"]


def test_shift_start_and_end(client):
    rid = person_id(client, "Ramesh")
    r = client.post("/api/shifts/start", json={"person_id": rid})
    assert r.status_code == 200
    body = r.json()
    ss = body["shift_session"]
    assert (
        ss["person_id"] == rid
        and ss["person_name"] == "Ramesh Yadav"
        and ss["ended_at"] is None
    )
    assert body["person"]["on_shift_now"] is True
    assert any(m["type"] == "shift.started" for m in hub.sent)

    # starting again closes the open one
    again = client.post("/api/shifts/start", json={"person_id": rid}).json()[
        "shift_session"
    ]
    assert again["id"] != ss["id"]
    shifts = {x["id"]: x for x in client.get("/api/shifts").json()}
    assert shifts[ss["id"]]["ended_at"] is not None

    r = client.post(
        f"/api/shifts/{again['id']}/end",
        json={"summary": "4B still vibrating, KB-0142 filed"},
    )
    assert r.status_code == 200
    ended = r.json()["shift_session"]
    assert ended["ended_at"] is not None
    assert ended["handover_summary"] == "4B still vibrating, KB-0142 filed"
    assert any(m["type"] == "shift.ended" for m in hub.sent)


def test_shift_errors(client):
    assert client.post("/api/shifts/start", json={"person_id": 9999}).status_code == 400
    assert client.post("/api/shifts/9999/end", json={}).status_code == 400


# -- tickets ---------------------------------------------------------------------------


def test_list_tickets_filters(client):
    active = client.get("/api/tickets", params={"status": "active"}).json()
    assert [d["key"] for d in active] == [
        "KB-0140",
        "KB-0141",
        "KB-0136",
        "KB-0138",
        "KB-0134",
    ]
    assert all(d["status"] != "closed" for d in active)
    d141 = active[1]
    assert d141["overdue"] is True and d141["unclear"] is True
    assert d141["last_check"]["author"]["name"] == "Suresh Patil"
    assert [a["name"] for a in d141["assignees"]] == ["Arjun Mehta"]

    assert [
        d["key"] for d in client.get("/api/tickets", params={"machine": "4B"}).json()
    ] == ["KB-0141", "KB-0127"]
    assert [
        d["key"]
        for d in client.get(
            "/api/tickets", params={"machine": "4b", "status": "active"}
        ).json()
    ] == ["KB-0141"]
    assert [
        d["key"] for d in client.get("/api/tickets", params={"q": "leak"}).json()
    ] == ["KB-0140"]
    assert [
        d["key"] for d in client.get("/api/tickets", params={"q": "VIBRATION"}).json()
    ] == ["KB-0141"]
    assert len(client.get("/api/tickets").json()) == 9
    assert len(client.get("/api/tickets", params={"status": "closed"}).json()) == 4


def test_list_tickets_by_assignee(client):
    arjun = person_id(client, "Arjun")
    keys = {
        d["key"] for d in client.get("/api/tickets", params={"assignee": arjun}).json()
    }
    assert keys == {"KB-0127", "KB-0123", "KB-0138", "KB-0140", "KB-0141"}


def test_list_tickets_since(client):
    since = (db.now() - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    keys = {
        d["key"] for d in client.get("/api/tickets", params={"since": since}).json()
    }
    assert keys == {"KB-0138", "KB-0140", "KB-0141"}


def test_ticket_detail_shape(client):
    r = client.get("/api/tickets/141")
    assert r.status_code == 200
    d = r.json()
    assert (
        d["key"] == "KB-0141"
        and d["machine_code"] == "4B"
        and d["machine_name"] == "CNC Lathe"
    )
    assert d["status"] == "monitoring" and d["overdue"] is True and d["unclear"] is True
    assert d["monitoring_owner"]["name"] == "Suresh Patil"
    assert d["reporter"]["name"] == "Priya Nair"
    assert len(d["checks"]) == 1
    c = d["checks"][0]
    assert (
        c["unclear"] is True
        and c["what_found"] == "Checked"
        and c["what_checked"] == ""
    )
    assert (c["status_from"], c["status_to"]) == ("open", "monitoring")
    assert c["author"]["name"] == "Suresh Patil"
    assert d["related"] == [] and d["related_keys"] == []
    assert d["photos"] == []
    assert len(d["transcript"]) == 5 and d["transcript"][0]["who"] == "user"
    assert d["telemetry_snapshot"]["machine_code"] == "4B"
    assert len(d["telemetry_snapshot"]["series"]) == 60
    for k in (
        "symptom",
        "since_text",
        "context",
        "machine_running",
        "source_language",
        "description",
    ):
        assert k in d
    created = ts(d["created_at"])
    assert abs(created - (db.now() - timedelta(hours=5, minutes=40))) < timedelta(
        seconds=5
    )


def test_ticket_detail_related_after_filing(client, s, people):
    file_ticket(
        s,
        {"machine_code": "4B", "symptom": "vibration again"},
        people["ramesh"].id,
        related_key="141",
    )
    d = client.get("/api/tickets/KB-0141").json()
    assert d["related_keys"] == ["KB-0142"]
    assert d["related"][0]["key"] == "KB-0142"
    assert client.get("/api/tickets/142").json()["related_keys"] == ["KB-0141"]


@pytest.mark.parametrize("key", ["999", "abc"])
def test_ticket_detail_404(client, key):
    assert client.get(f"/api/tickets/{key}").status_code == 404


def test_patch_status_needs_a_check(client):
    r = client.patch("/api/tickets/KB-0136", json={"status": "in_progress"})
    assert r.status_code == 400
    assert "check" in r.json()["detail"]
    assert client.get("/api/tickets/136").json()["status"] == "open"

    r = client.patch("/api/tickets/KB-0136", json={"status": "in_progress", "check": {"what_checked": "checked",
                                                                                      "what_found": "ok"}})  # fmt: skip
    assert r.status_code == 400 and "needs a check" in r.json()["detail"]


def test_patch_status_with_check(client):
    r = client.patch("/api/tickets/KB-0141", json={
        "status": "closed",
        "check": {"what_checked": "tool holder seating", "what_found": "not seated after TC; reseated, 1.8 mm/s"},
    })  # fmt: skip
    assert r.status_code == 200
    d = r.json()
    assert (
        d["status"] == "closed" and d["closed_at"] is not None and d["overdue"] is False
    )
    detail = client.get("/api/tickets/141").json()
    assert len(detail["checks"]) == 2
    last = detail["checks"][-1]
    assert (
        last["author"]["name"] == "Admin"
        and last["status_to"] == "closed"
        and last["unclear"] is False
    )


def test_patch_fields_and_assignees(client):
    imran, kavita = person_id(client, "Imran"), person_id(client, "Kavita")
    r = client.patch("/api/tickets/136", json={"title": "Light curtain trips on 2A", "severity": "critical",
                                               "assignee_ids": [imran, kavita, imran]})  # fmt: skip
    assert r.status_code == 200
    d = r.json()
    assert d["title"] == "Light curtain trips on 2A" and d["severity"] == "critical"
    assert sorted(a["name"] for a in d["assignees"]) == [
        "Imran Shaikh",
        "Kavita Sharma",
    ]
    assert d["status"] == "open"  # no status change, no Check needed
    assert (
        client.patch("/api/tickets/136", json={"severity": "apocalyptic"}).status_code
        == 400
    )
    assert client.patch("/api/tickets/999", json={"title": "x"}).status_code == 400


def test_patch_unknown_assignee_is_400(client):
    r = client.patch("/api/tickets/136", json={"assignee_ids": [9999]})
    assert r.status_code == 400


def test_post_check(client):
    r = client.post("/api/tickets/141/checks", json={"what_checked": "vibration at the guard with the meter",
                                                     "what_found": "4.4 mm/s, same as before"})  # fmt: skip
    assert r.status_code == 200
    assert r.json()["key"] == "KB-0141" and r.json()["status"] == "monitoring"
    checks = client.get("/api/tickets/141").json()["checks"]
    assert len(checks) == 2 and checks[-1]["what_found"] == "4.4 mm/s, same as before"

    r = client.post(
        "/api/tickets/141/checks", json={"what_checked": "", "what_found": "ok"}
    )
    assert r.status_code == 400 and "needs a check" in r.json()["detail"]
    r = client.post(
        "/api/tickets/141/checks",
        json={"what_checked": "", "what_found": "ok", "unclear": True},
    )
    assert r.status_code == 200
    assert client.get("/api/tickets/141").json()["checks"][-1]["unclear"] is True

    r = client.post("/api/tickets/136/checks", json={"what_checked": "trip log", "what_found": "sensor dirty, cleaned",
                                                     "new_status": "monitoring", "next_check_minutes": 45})  # fmt: skip
    d = r.json()
    assert d["status"] == "monitoring"
    assert abs(ts(d["next_check_at"]) - (db.now() + timedelta(minutes=45))) < timedelta(
        seconds=5
    )
    assert (
        client.post(
            "/api/tickets/999/checks", json={"what_checked": "a b", "what_found": "c d"}
        ).status_code
        == 400
    )


# -- uploads ---------------------------------------------------------------------------


def test_upload_png_and_serve(client):
    r = client.post(
        "/api/uploads",
        files={"file": ("p.png", png_bytes(), "image/png")},
        data={"session_id": "sx"},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["photo_id"], int)
    assert body["url"].startswith("/uploads/") and body["url"].endswith(".jpg")
    got = client.get(body["url"])
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/jpeg"
    assert got.content[:2] == b"\xff\xd8"


def test_upload_attaches_on_filing(client, s, people):
    pid = client.post("/api/uploads", files={"file": ("p.png", png_bytes(), "image/png")},
                      data={"session_id": "voice-42"}).json()["photo_id"]  # fmt: skip
    file_ticket(
        s,
        {"machine_code": "4B", "symptom": "chips stuck in guard"},
        people["ramesh"].id,
        session_id="voice-42",
    )
    d = client.get("/api/tickets/142").json()
    assert [p["id"] for p in d["photos"]] == [pid]
    assert d["photo_count"] == 1


def test_upload_resizes_large_image(client):
    url = client.post(
        "/api/uploads",
        files={"file": ("big.png", png_bytes((3000, 1000)), "image/png")},
    ).json()["url"]
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(client.get(url).content))
    assert max(img.size) == 1600


def test_upload_rejects_non_image(client):
    r = client.post(
        "/api/uploads", files={"file": ("x.txt", b"not an image", "text/plain")}
    )
    assert r.status_code == 400


# -- metrics, glossary, machines ----------------------------------------------------------


def test_metrics_for_seed(client):
    m = client.get("/api/metrics").json()
    assert m == {
        "open": 5,
        "critical": 1,
        "overdue_monitoring": 1,
        "unclear_checks": 1,
        "mean_time_to_close_h": 8.5,  # (24 + 2 + 5 + 3) / 4
        "closed_7d": 4,
    }


def test_glossary_get_and_put(client):
    g = client.get("/api/glossary").json()
    assert {"term": "TC", "meaning": "tool change"} in g
    assert len(g) == 11
    r = client.put("/api/glossary", json={"terms": [{"term": " TC ", "meaning": " tool change "},
                                                    {"term": "OT", "meaning": "overtime"},
                                                    {"term": "  ", "meaning": "dropped"}]})  # fmt: skip
    assert r.status_code == 200
    expect = [
        {"term": "OT", "meaning": "overtime"},
        {"term": "TC", "meaning": "tool change"},
    ]
    assert sorted(r.json(), key=lambda x: x["term"]) == expect
    assert sorted(client.get("/api/glossary").json(), key=lambda x: x["term"]) == expect
    assert any(m["type"] == "glossary.updated" for m in hub.sent)


def test_machines_list(client):
    ms = {m["code"]: m for m in client.get("/api/machines").json()}
    assert set(ms) == {"4B", "2A", "3C", "1D", "5A", "6B"}
    assert ms["4B"]["open_tickets"] == ["KB-0141"]
    assert sorted(ms["2A"]["open_tickets"]) == ["KB-0136", "KB-0140"]
    assert ms["4B"]["telemetry"]["vibration_band"] == "warning"
    assert ms["4B"]["target_per_shift"] == 120
    assert client.get("/api/machines/4b/telemetry", params={"minutes": 5}).json()
    assert client.get("/api/machines/9Z/telemetry").status_code == 404


# -- demo controls -------------------------------------------------------------------------


def test_demo_inject_and_clear(client):
    assert client.post("/api/demo/inject", json={"machine_code": "4b"}).json() == {
        "ok": True
    }
    m = telemetry.machines["4B"]
    assert m.ramp is not None and m.ramp.to_vib == pytest.approx(9.5)
    assert telemetry.current("4B")["injected"] is True
    assert client.post("/api/demo/clear", json={"machine_code": "4B"}).json() == {
        "ok": True
    }
    assert m.ramp.to_vib == pytest.approx(m.vib_base)
    assert telemetry.current("4B")["injected"] is False
    types = [x["type"] for x in hub.sent]
    assert "demo.injected" in types and "demo.cleared" in types


def test_demo_unknown_machine_404(client):
    assert (
        client.post("/api/demo/inject", json={"machine_code": "9Z"}).status_code == 404
    )
    assert (
        client.post("/api/demo/clear", json={"machine_code": "9Z"}).status_code == 404
    )


def test_demo_reset_reseeds(client, s, people):
    file_ticket(
        s, {"machine_code": "4B", "symptom": "vibration again"}, people["ramesh"].id
    )
    client.put("/api/glossary", json={"terms": []})
    photo = client.post(
        "/api/uploads", files={"file": ("p.png", png_bytes(), "image/png")}
    ).json()["url"]
    assert client.get("/api/tickets/142").status_code == 200

    assert client.post("/api/demo/reset").json() == {"ok": True}
    assert client.get("/api/tickets/142").status_code == 404
    assert len(client.get("/api/tickets").json()) == 9
    assert len(client.get("/api/glossary").json()) == 11
    assert client.get(photo).status_code == 404
    assert client.get("/api/metrics").json()["open"] == 5
    with db.session() as fresh:
        assert len(fresh.exec(select(Person)).all()) == 7
    assert hub.sent[-1]["type"] == "demo.reset"


def test_health(client):
    h = client.get("/api/health").json()
    assert h["ok"] is True and h["db"]["tickets"] == 9
    assert h["shift_now"] in ("day", "night")


# -- /ws -------------------------------------------------------------------------------------


def read_until(ws, types: set[str], limit: int = 15) -> dict[str, dict]:
    """Read messages (skipping telemetry) until every type in `types` was seen."""
    seen: dict[str, dict] = {}
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] in types:
            seen.setdefault(msg["type"], msg)
        if types <= seen.keys():
            break
    return seen


def test_ws_broadcasts_check(client):
    with client.websocket_connect("/ws") as ws:
        assert (
            ws.receive_json()["type"] == "telemetry"
        )  # we are registered with the hub now
        r = client.post("/api/tickets/141/checks", json={"what_checked": "spindle bearing temperature",
                                                         "what_found": "71 C, warm but steady"})  # fmt: skip
        assert r.status_code == 200
        seen = read_until(ws, {"check.added", "ticket.updated"})
    assert set(seen) == {"check.added", "ticket.updated"}
    added = seen["check.added"]
    assert added["data"]["ticket_key"] == "KB-0141"
    assert added["data"]["check"]["what_found"] == "71 C, warm but steady"
    assert added["at"].endswith("Z")
    updated = seen["ticket.updated"]["data"]
    assert updated["ticket"]["key"] == "KB-0141" and updated["by"] == "admin"
    assert (
        updated["ticket"]["last_check"]["what_checked"] == "spindle bearing temperature"
    )


def test_ws_broadcasts_patch_and_telemetry(client):
    with client.websocket_connect("/ws") as ws:
        tel = ws.receive_json()
        assert tel["type"] == "telemetry" and set(tel["data"]) == {
            "4B",
            "2A",
            "3C",
            "1D",
            "5A",
            "6B",
        }
        assert set(tel["data"]["4B"]) == {"v", "c", "l", "o", "t"}
        client.patch("/api/tickets/136", json={"severity": "critical"})
        seen = read_until(ws, {"ticket.updated"})
    assert seen["ticket.updated"]["data"]["ticket"]["severity"] == "critical"


def test_mutations_are_stored_in_event_feed(client):
    client.post(
        "/api/tickets/141/checks",
        json={"what_checked": "guard bolts", "what_found": "all tight"},
    )
    types = [e["type"] for e in client.get("/api/events").json()]
    assert types[:2] == ["ticket.updated", "check.added"]
    assert "telemetry" not in types

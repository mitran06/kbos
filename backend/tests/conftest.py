import dataclasses
import io
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

import kbos.app as app_mod
from kbos import db
from kbos.app import create_app
from kbos.models import Person
from kbos.realtime import hub

# Fixed wall clocks for deterministic seeds (IST = UTC + 5:30).
DAY = datetime(2026, 10, 2, 2, 35, tzinfo=UTC)  # 08:05 IST, day crew logging in
NIGHT = datetime(2026, 10, 1, 20, 0, tzinfo=UTC)  # 01:30 IST, night crew on


@pytest.fixture(autouse=True)
def _tmp_uploads(tmp_path, monkeypatch):
    """Keep uploads (and /api/demo/reset's *.jpg wipe) away from backend/uploads."""
    monkeypatch.setattr(
        app_mod,
        "settings",
        dataclasses.replace(app_mod.settings, uploads_dir=tmp_path / "uploads"),
    )


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "t.db", probe_keys=False)
    hub.sent.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def s(client):
    with db.session() as session:
        yield session


@pytest.fixture(params=[DAY, NIGHT], ids=["day", "night"])
def frozen_client(request, tmp_path, monkeypatch):
    """App seeded with db.now frozen at a day or a night wall-clock time."""
    monkeypatch.setattr(db, "now", lambda: request.param)
    app = create_app(tmp_path / "frozen.db", probe_keys=False)
    with TestClient(app) as c:
        c.now = request.param
        yield c


@pytest.fixture
def fs(frozen_client):
    with db.session() as session:
        yield session


@pytest.fixture
def people(s):
    """first name (lowercase) -> Person"""
    return {p.name.split()[0].lower(): p for p in s.exec(select(Person)).all()}


def png_bytes(size=(8, 6), color=(200, 30, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()

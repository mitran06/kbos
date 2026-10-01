import pytest
from fastapi.testclient import TestClient

from kbos import db
from kbos.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "t.db", probe_keys=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def s(client):
    with db.session() as session:
        yield session

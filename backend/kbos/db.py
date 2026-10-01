"""SQLite engine (WAL) and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from kbos import models  # noqa: F401  (registers tables)

_engine: Engine | None = None


def now() -> datetime:
    """Aware UTC 'now'. Everything is stored and compared in UTC."""
    return datetime.now(UTC)


def init_engine(path: Path | str) -> Engine:
    global _engine
    url = "sqlite://" if str(path) == ":memory:" else f"sqlite:///{path}"
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if str(path) == ":memory:":
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)

    @event.listens_for(_engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SQLModel.metadata.create_all(_engine)
    return _engine


def engine() -> Engine:
    assert _engine is not None, "init_engine() first"
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    with Session(engine(), expire_on_commit=False) as s:
        yield s


def reset_schema() -> None:
    SQLModel.metadata.drop_all(engine())
    SQLModel.metadata.create_all(engine())

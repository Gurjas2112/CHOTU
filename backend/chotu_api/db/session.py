"""Engine + session factory for DATABASE_URL."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def make_engine(url: str) -> Engine:
    if not url:
        raise ValueError("CHOTU_STORE=sql needs DATABASE_URL, e.g. "
                         "postgresql+psycopg://chotu:chotu@localhost:5432/chotu")
    if url.startswith("sqlite") and ":memory:" in url:
        # one shared in-memory database for every session/thread (tests)
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)

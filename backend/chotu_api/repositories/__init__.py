"""Pick the store from Settings.store."""
from __future__ import annotations

from ..config import Settings
from .base import Repository
from .sample import SampleRepository


def build_repository(settings: Settings) -> Repository:
    if settings.store == "sample":
        return SampleRepository(settings.sample_dir)
    if settings.store == "sql":
        from ..db.session import make_engine, make_session_factory
        from .sql import SqlRepository

        return SqlRepository(make_session_factory(make_engine(settings.database_url)))
    raise ValueError(f"CHOTU_STORE must be 'sample' or 'sql', got {settings.store!r}")


__all__ = ["Repository", "SampleRepository", "build_repository"]

import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

from chotu_api.config import Settings  # noqa: E402
from chotu_api.db.seed import seed  # noqa: E402
from chotu_api.db.session import make_engine  # noqa: E402
from chotu_api.main import create_app  # noqa: E402

SQLITE_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture(params=["sample", "sql"])
def client(request, monkeypatch):
    """The same API tests run against both stores. 'sql' seeds an in-memory SQLite
    database from sample_data, i.e. exactly the path PostgreSQL takes in production."""
    if request.param == "sql":
        engine = make_engine(SQLITE_URL)
        seed(engine, Settings().sample_dir)
        # reuse the seeded engine instead of opening a second (empty) in-memory db
        monkeypatch.setattr("chotu_api.db.session.make_engine", lambda url: engine)
        st = Settings(store="sql", database_url=SQLITE_URL, replay_speed=50.0)
    else:
        st = Settings(replay_speed=50.0)
    with TestClient(create_app(st)) as c:
        yield c


@pytest.fixture
def secured_client():
    with TestClient(create_app(Settings(api_key="s3cret", replay_speed=50.0))) as c:
        yield c

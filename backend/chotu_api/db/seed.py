"""Create the tables and load sample_data/*.json into DATABASE_URL.

    DATABASE_URL=postgresql+psycopg://chotu:chotu@localhost:5432/chotu python -m chotu_api.db.seed
    python -m chotu_api.db.seed --reset      # drop + recreate first

Idempotent: rows whose primary key already exists are skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from ..config import Settings
from .models import TABLES, Base
from .session import make_engine, make_session_factory


def seed(engine, sample_dir: str, reset: bool = False) -> dict:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    counts = {}
    with session_factory.begin() as s:
        for fname, model in TABLES:
            with open(os.path.join(sample_dir, fname), encoding="utf-8") as f:
                rows = json.load(f)
            added = 0
            for r in rows:
                if s.get(model, r["id"]) is None:
                    s.add(model(**r))
                    added += 1
            s.flush()
            counts[model.__tablename__] = added
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="drop all CHOTU tables first")
    args = ap.parse_args(argv)
    st = Settings.from_env()
    try:
        engine = make_engine(st.database_url)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    for table, n in seed(engine, st.sample_dir, args.reset).items():
        print(f"{table:10s} +{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Runtime settings, read once from environment variables (see backend/.env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAMPLE_DIR = os.path.join(os.path.dirname(_HERE), "sample_data")


@dataclass(frozen=True)
class Settings:
    # "sample" = in-memory store loaded from sample_data/*.json (default, no database)
    # "sql"    = SQLAlchemy store on DATABASE_URL (PostgreSQL in production, SQLite for tests)
    store: str = "sample"
    database_url: str = ""
    sample_dir: str = DEFAULT_SAMPLE_DIR
    # "demo"      = replay sample_data/telemetry_replay.json, no robot needed (default)
    # "rosbridge" = connect to each robot's rosbridge (robots.json "endpoint")
    robot_link: str = "demo"
    replay_speed: float = 1.0
    # empty = auth disabled (local demo); otherwise clients send "X-API-Key"
    api_key: str = ""
    cors_origins: tuple = field(default_factory=lambda: ("*",))

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        return cls(
            store=e("CHOTU_STORE", "sample"),
            database_url=e("DATABASE_URL", ""),
            sample_dir=e("CHOTU_SAMPLE_DIR", DEFAULT_SAMPLE_DIR),
            robot_link=e("CHOTU_ROBOT_LINK", "demo"),
            replay_speed=float(e("CHOTU_REPLAY_SPEED", "1.0")),
            api_key=e("CHOTU_API_KEY", ""),
            cors_origins=tuple(o.strip() for o in e("CHOTU_CORS_ORIGINS", "*").split(",") if o.strip()),
        )

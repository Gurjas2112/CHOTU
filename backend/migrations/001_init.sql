-- CHOTU fleet backend, schema v1 (PostgreSQL 14+).
-- Same tables as chotu_api/db/models.py; backend/tests/test_api.py checks they match.
--   psql "$DATABASE_URL" -f backend/migrations/001_init.sql
-- (or let `python -m chotu_api.db.seed` create them through SQLAlchemy)

CREATE TABLE IF NOT EXISTS rooms (
    id          VARCHAR(64)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    width_m     DOUBLE PRECISION NOT NULL,
    height_m    DOUBLE PRECISION NOT NULL,
    dock        JSONB        NOT NULL,          -- {"x":..,"y":..,"theta":..} metres / rad
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS robots (
    id          VARCHAR(64)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    room_id     VARCHAR(64)  NOT NULL,
    firmware    VARCHAR(32)  NOT NULL,
    software    VARCHAR(32)  NOT NULL,
    endpoint    VARCHAR(256) NOT NULL,          -- rosbridge ws://<pi>:9090
    PRIMARY KEY (id),
    FOREIGN KEY (room_id) REFERENCES rooms (id)
);

CREATE TABLE IF NOT EXISTS missions (
    id                    VARCHAR(64) NOT NULL,
    robot_id              VARCHAR(64) NOT NULL,
    room_id               VARCHAR(64) NOT NULL,
    started_at            VARCHAR(32) NOT NULL, -- ISO-8601 UTC, sorts lexically
    ended_at              VARCHAR(32) NOT NULL,
    trigger               VARCHAR(16) NOT NULL, -- app | schedule
    source                VARCHAR(16) NOT NULL, -- digital_twin | gazebo | robot
    sim_seed              INTEGER,
    docked                BOOLEAN     NOT NULL,
    duration_s            DOUBLE PRECISION NOT NULL,
    coverage              DOUBLE PRECISION NOT NULL,
    debris_g              DOUBLE PRECISION NOT NULL,
    debris_spawned_g      DOUBLE PRECISION,
    energy_wh             DOUBLE PRECISION NOT NULL,
    avg_power_w           DOUBLE PRECISION NOT NULL,
    eco_energy_saving_pct DOUBLE PRECISION NOT NULL,
    collisions            INTEGER     NOT NULL,
    cable_incidents       INTEGER     NOT NULL,
    recoveries            INTEGER     NOT NULL,
    dock_error_m          DOUBLE PRECISION NOT NULL,
    efficiency_by_type    JSONB       NOT NULL,
    rubric                JSONB       NOT NULL, -- AtomQuest criteria -> points
    score                 DOUBLE PRECISION NOT NULL,
    no_go_zones           INTEGER     NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (robot_id) REFERENCES robots (id),
    FOREIGN KEY (room_id) REFERENCES rooms (id)
);
CREATE INDEX IF NOT EXISTS ix_missions_robot_id ON missions (robot_id);
CREATE INDEX IF NOT EXISTS ix_missions_started_at ON missions (started_at);

CREATE TABLE IF NOT EXISTS schedules (
    id          VARCHAR(64) NOT NULL,
    robot_id    VARCHAR(64) NOT NULL,
    time        VARCHAR(5)  NOT NULL,           -- HH:MM local time
    days        JSONB       NOT NULL,           -- [1..7], 1 = Monday
    label       VARCHAR(64) NOT NULL,
    enabled     BOOLEAN     NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (robot_id) REFERENCES robots (id)
);
CREATE INDEX IF NOT EXISTS ix_schedules_robot_id ON schedules (robot_id);

CREATE TABLE IF NOT EXISTS zones (
    id          VARCHAR(64) NOT NULL,
    robot_id    VARCHAR(64) NOT NULL,
    label       VARCHAR(64) NOT NULL,
    x0          DOUBLE PRECISION NOT NULL,      -- metres, room frame
    y0          DOUBLE PRECISION NOT NULL,
    x1          DOUBLE PRECISION NOT NULL,
    y1          DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (robot_id) REFERENCES robots (id)
);
CREATE INDEX IF NOT EXISTS ix_zones_robot_id ON zones (robot_id);

CREATE TABLE IF NOT EXISTS alerts (
    id          VARCHAR(64)  NOT NULL,
    robot_id    VARCHAR(64)  NOT NULL,
    mission_id  VARCHAR(64),
    level       VARCHAR(16)  NOT NULL,          -- info | warning | critical
    code        VARCHAR(32)  NOT NULL,
    title       VARCHAR(128) NOT NULL,
    body        VARCHAR(512) NOT NULL,
    created_at  VARCHAR(32)  NOT NULL,
    resolved    BOOLEAN      NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (robot_id) REFERENCES robots (id),
    FOREIGN KEY (mission_id) REFERENCES missions (id)
);
CREATE INDEX IF NOT EXISTS ix_alerts_robot_id ON alerts (robot_id);
CREATE INDEX IF NOT EXISTS ix_alerts_created_at ON alerts (created_at);

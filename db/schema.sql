-- WSU-SEN 309 Embedded Software and Data Systems Lab
-- Practical 2  |  Storage entities, keys and integrity constraints (STARTER: complete the TODOs)
-- (c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
--
-- Load with:  python tools/sql.py data/sen309.db db/schema.sql
-- SQLite only enforces foreign keys when PRAGMA foreign_keys = ON (tools/sql.py and host/db.py set it).

PRAGMA foreign_keys = ON;

-- A device that is allowed to send data. Registered by hand before its records are accepted.
CREATE TABLE device (
    device_id   TEXT PRIMARY KEY CHECK (device_id GLOB 'SN[0-9][0-9]'),
    label       TEXT NOT NULL CHECK (length(trim(label)) > 0),
    location    TEXT,
    added_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One power-up of a device. The device numbers its readings from 0 after every boot,
-- so a reading is identified by (device, boot, seq), here (session_id, seq).
-- TODO P2-A1: add the constraints marked below. Run python tools/check_constraints.py db/schema.sql
CREATE TABLE boot_session (
    session_id         INTEGER PRIMARY KEY,
    device_id          TEXT    NOT NULL,          -- TODO: must refer to a registered device; refuse to delete that device
    boot               INTEGER NOT NULL,          -- TODO: a whole number, 0 or more
    fw                 TEXT,                      -- NULL if the H line was never received
    period_ms          INTEGER,                   -- TODO: NULL, or between 200 and 60000
    reported_count     INTEGER CHECK (reported_count IS NULL OR reported_count >= 0),   -- from the E line
    reported_last_seq  INTEGER CHECK (reported_last_seq IS NULL OR reported_last_seq >= -1),
    first_seen         TEXT    NOT NULL DEFAULT (datetime('now'))
    -- TODO: one session per (device_id, boot)
);

-- One reading.
-- TODO P2-A2: choose the primary key and write every constraint the readings need:
--   a reading belongs to an existing session (deleting a session deletes its readings);
--   seq and t_ms are whole numbers, 0 or more; temp_c is a real number from -40.0 to 125.0;
--   light is a whole number from 0 to 1023; state is RUN or ALM; no value may be missing.
--   SQLite stores whatever type it is given unless you check typeof(column) yourself.
CREATE TABLE reading (
    session_id   INTEGER,
    seq          INTEGER,
    t_ms         INTEGER,
    temp_c       REAL,
    light        INTEGER,
    state        TEXT,
    run_id       INTEGER REFERENCES ingest_run (run_id)
);

-- One execution of the ingest program, so every stored or rejected line can be traced to a run.
CREATE TABLE ingest_run (
    run_id       INTEGER PRIMARY KEY,
    source       TEXT    NOT NULL,
    started_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    status       TEXT    NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'DONE', 'INCOMPLETE')),
    lines_read   INTEGER NOT NULL DEFAULT 0 CHECK (lines_read >= 0),
    inserted     INTEGER NOT NULL DEFAULT 0 CHECK (inserted >= 0),
    duplicates   INTEGER NOT NULL DEFAULT 0 CHECK (duplicates >= 0),
    rejected     INTEGER NOT NULL DEFAULT 0 CHECK (rejected >= 0)
);

-- Every line that was not stored, with the reason. Nothing is thrown away silently.
CREATE TABLE rejected_line (
    reject_id    INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES ingest_run (run_id),
    line_no      INTEGER NOT NULL CHECK (line_no >= 1),
    raw          TEXT    NOT NULL,
    reason       TEXT    NOT NULL CHECK (reason IN ('TRUNCATED', 'CHECKSUM', 'FORMAT', 'RANGE', 'UNKNOWN_DEVICE', 'CONFLICT')),
    detail       TEXT
);

CREATE INDEX idx_rejected_run ON rejected_line (run_id, reason);

-- TODO P2-B1 (extension): a trigger named reading_is_append_only that refuses every UPDATE on reading
--   with the message 'readings are append-only'.

-- TODO P2-B2 (extension): a view named v_session_summary with one row per boot session:
--   session_id, device_id, boot, stored (number of readings), first_seq, last_seq,
--   span (last_seq - first_seq + 1, or 0), missing_inside (span - stored), reported_count, reported_last_seq.
--   Sessions with no readings must still appear (use a LEFT JOIN).

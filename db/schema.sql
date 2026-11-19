-- WSU-SEN 309 Embedded Software and Data Systems Lab
-- Practical 2  |  Storage entities, keys and integrity constraints
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
-- TODO P2-A1:
CREATE TABLE boot_session (
    session_id         INTEGER PRIMARY KEY,
    device_id          TEXT    NOT NULL REFERENCES device (device_id) ON DELETE RESTRICT,
    boot               INTEGER NOT NULL CHECK (typeof(boot) = 'integer' AND boot >= 0),
    fw                 TEXT,
    period_ms          INTEGER CHECK (period_ms IS NULL OR (typeof(period_ms) = 'integer' AND period_ms BETWEEN 200 AND 60000)),
    reported_count     INTEGER CHECK (reported_count IS NULL OR reported_count >= 0),
    reported_last_seq  INTEGER CHECK (reported_last_seq IS NULL OR reported_last_seq >= -1),
    first_seen         TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (device_id, boot)
);

-- One reading.
-- TODO P2-A2:
CREATE TABLE reading (
    session_id   INTEGER NOT NULL REFERENCES boot_session (session_id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL CHECK (typeof(seq) = 'integer' AND seq >= 0),
    t_ms         INTEGER NOT NULL CHECK (typeof(t_ms) = 'integer' AND t_ms >= 0),
    temp_c       REAL    NOT NULL CHECK (typeof(temp_c) = 'real' AND temp_c BETWEEN -40.0 AND 125.0),
    light        INTEGER NOT NULL CHECK (typeof(light) = 'integer' AND light BETWEEN 0 AND 1023),
    state        TEXT    NOT NULL CHECK (state IN ('RUN', 'ALM')),
    run_id       INTEGER REFERENCES ingest_run (run_id),
    PRIMARY KEY (session_id, seq)
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

-- TODO P2-B1 (extension):
CREATE TRIGGER reading_is_append_only
BEFORE UPDATE ON reading
BEGIN
    SELECT RAISE(ABORT, 'readings are append-only');
END;

-- TODO P2-B2 (extension):
CREATE VIEW v_session_summary AS
SELECT
    bs.session_id,
    bs.device_id,
    bs.boot,
    COUNT(r.seq) AS stored,
    MIN(r.seq) AS first_seq,
    MAX(r.seq) AS last_seq,
    COALESCE(MAX(r.seq) - MIN(r.seq) + 1, 0) AS span,
    COALESCE(MAX(r.seq) - MIN(r.seq) + 1, 0) - COUNT(r.seq) AS missing_inside,
    bs.reported_count,
    bs.reported_last_seq
FROM boot_session bs
LEFT JOIN reading r ON r.session_id = bs.session_id
GROUP BY bs.session_id, bs.device_id, bs.boot, bs.reported_count, bs.reported_last_seq;
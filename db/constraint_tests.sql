-- WSU-SEN 309  |  Practical 2  |  Constraint tests
-- (c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
--
-- Run with:  python tools/check_constraints.py db/schema.sql
-- The runner builds a fresh in-memory database from your schema and db/seed.sql, runs the SETUP
-- block, then runs each test on its own and undoes it, so the tests do not affect each other.
-- Write your prediction (ACCEPTED or REJECTED) in the workbook BEFORE you run them.

-- SETUP
INSERT INTO boot_session (session_id, device_id, boot, fw, period_ms) VALUES (1, 'SN01', 1, '1.0', 1000);
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 0, 3, 24.6, 307, 'RUN');

-- T01 A valid reading for a known session
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 1, 1003, 24.6, 307, 'RUN');

-- T02 The same reading (session 1, seq 0) a second time
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 0, 3, 24.6, 307, 'RUN');

-- T03 A reading for a session that does not exist
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (99, 0, 3, 24.6, 307, 'RUN');

-- T04 A temperature of 150.0 C
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 2, 2003, 150.0, 307, 'RUN');

-- T05 A light value of -1
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 2, 2003, 24.6, -1, 'RUN');

-- T06 A light value written as the text '512'
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 2, 2003, 24.6, '512', 'RUN');

-- T07 A light value written as the text 'high'
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 2, 2003, 24.6, 'high', 'RUN');

-- T08 A state of 'OK'
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 2, 2003, 24.6, 307, 'OK');

-- T09 A reading with no temperature
INSERT INTO reading (session_id, seq, t_ms, light, state) VALUES (1, 2, 2003, 307, 'RUN');

-- T10 A temperature written as the whole number 25
INSERT INTO reading (session_id, seq, t_ms, temp_c, light, state) VALUES (1, 2, 2003, 25, 307, 'RUN');

-- T11 A boot session for an unregistered device SN99
INSERT INTO boot_session (device_id, boot) VALUES ('SN99', 1);

-- T12 A second session for SN01 boot 1
INSERT INTO boot_session (device_id, boot) VALUES ('SN01', 1);

-- T13 A device with the id 'XX1'
INSERT INTO device (device_id, label) VALUES ('XX1', 'Bad id');

-- T14 A session with a sampling period of 50 ms
INSERT INTO boot_session (device_id, boot, period_ms) VALUES ('SN02', 1, 50);

-- T15 Delete device SN01, which has a session
DELETE FROM device WHERE device_id = 'SN01';

-- T16 Change the light value of a stored reading
UPDATE reading SET light = 0 WHERE session_id = 1 AND seq = 0;
-- T17 Deleting a boot session cascades to delete its readings
DELETE FROM boot_session WHERE session_id = 1;

-- T18 A rejected_line row with an invalid reason code
INSERT INTO ingest_run (run_id, source) VALUES (1, 'test.txt');
INSERT INTO rejected_line (run_id, line_no, raw, reason) VALUES (1, 1, 'bad', 'BAD_DATA');
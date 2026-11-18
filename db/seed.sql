-- WSU-SEN 309  |  Practical 2  |  Devices allowed to send data
-- (c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
-- Load after the schema:  python tools/sql.py data/sen309.db db/seed.sql
INSERT INTO device (device_id, label, location) VALUES
    ('SN01', 'Bench logger 1 (Wokwi or fixture default)', 'Lab A'),
    ('SN02', 'Bench logger 2', 'Lab A'),
    ('SN03', 'Server room logger', 'Data centre');

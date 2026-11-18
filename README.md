# WSU-SEN 309: Embedded Software and Data Systems Lab (course files)

Faculty of Computing, Wellspring University · Version 1.1 (November 2026)

These are the files for the four WSU-SEN 309 practicals. Use them with the Practical Workbook.
Together they make one pipeline: **sensor → firmware → serial records → Python ingest → SQLite → reconciliation and recovery tests**.
No hardware is needed: the firmware runs in the free Wokwi simulator, and `fixture/device_sim.py` is a software copy of the same device.

## Getting the files

Download them as a ZIP (green **Code** button, then **Download ZIP**) or clone with Git:

```bash
git clone <this repository's URL>
cd wsu-sen309-course-files
python tools/check_setup.py        # must end with ALL CHECKS PASSED
```

## What is here

| Path | Used in | Contents |
|---|---|---|
| `firmware/sen309_logger/` | Practical 1 | Starter firmware (`TODO 1` to `TODO 5`) and `diagram.json` for Wokwi (Uno, temperature sensor, light sensor, alarm LED). |
| `fixture/` | All | `device_sim.py`: the device in software, with fault injection; `protocol.py`: framing and checksum helpers. |
| `db/` | Practical 2 | Starter `schema.sql` (TODOs), `seed.sql` (registered devices), `constraint_tests.sql` (16 tests). |
| `host/` | Practicals 3 and 4 | `records.py` (parser), `ingest.py` (into SQLite), `reconcile.py` (gap and count checks). Starters with TODOs. |
| `tests/` | Practicals 3 and 4 | `test_records.py` and `test_ingest.py` (acceptance tests, do not edit); `test_recovery.py` (you write the tests). |
| `tools/` | All | `check_setup.py`, `new_db.py`, `sql.py` (run SQL without the sqlite3 program), `check_constraints.py`. |
| `data/` | All | Sample captures: clean, faulty, cut, reboot, and a recording of the real firmware. |

## Everyday commands

```bash
python fixture/device_sim.py --count 60 --out data/my_run.txt          # make a capture
python tools/new_db.py                                                  # fresh data/sen309.db
python -m host.ingest --db data/sen309.db --source data/my_run.txt      # ingest it
python -m host.reconcile --db data/sen309.db                            # check it
python -m unittest -v tests.test_records                                # run tests
```

Databases (`*.db`) and your own captures (`data/my_*.txt`) are ignored by Git.

## Copyright

Copyright © 2026 A. S. Olayinka and S. A. Oyedotun. All rights reserved. Registered WSU-SEN 309 students may use these files for their course work. See `NOTICE.txt`.

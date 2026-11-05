#!/usr/bin/env python3
"""Idempotently add a PVDAQ-style single-axis tracker plant for the browser smoke test.

The plants API deliberately refuses the tracker marker (only the PVDAQ importer / seed may set it), so the
marker is written straight through the ORM here, the same way the importer does. The plant is labelled as a
smoke fixture (source SIMULATED, name starts with 'SMOKE'); it is not real data.

    python scripts/seed_smoke_tracker.py            # uses SOLARDOCTOR_DB_URL
"""
from __future__ import annotations

from solardoctor.db.session import get_session, init_db
from solardoctor.physics.models import Plant
from solardoctor.physics.tracker import with_marker

NAME = "SMOKE PVDAQ-style tracker"


def main() -> int:
    init_db()
    db = get_session()
    try:
        if db.query(Plant).filter(Plant.name == NAME).first():
            print(f"'{NAME}' already present")
            return 0
        db.add(Plant(
            name=NAME, location=with_marker("Golden, CO (smoke fixture, not real data)"),
            lat=39.74, lon=-105.18, tz="America/Denver", tilt=0.0, azimuth=180.0,
            dc_kw=100.0, ac_kw=90.0, source="SIMULATED",
        ))
        db.commit()
        print(f"created '{NAME}'")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

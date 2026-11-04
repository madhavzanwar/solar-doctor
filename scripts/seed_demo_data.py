#!/usr/bin/env python3
"""
Idempotent demo seed script for the Axalon solar inspection platform.

Usage:
    python scripts/seed_demo_data.py
    # or, if DB is at a non-default location:
    DB_URL=sqlite:///path/to/axalon.db python scripts/seed_demo_data.py

Idempotency guarantee:
    Deletes the three demo inspections (and their detections), then the demo
    park, before recreating everything from scratch.  Safe to run multiple
    times.
"""

import json
import os
import random
import sys
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so `axalon` can be imported when the
# script is executed from any working directory.
#
# Must be APPENDED, not inserted at position 0: the repo root contains a
# `platform/` package that would otherwise shadow the stdlib `platform` module
# for every downstream import (SQLAlchemy calls platform.python_implementation()
# at import time and crashes). Appending leaves the stdlib earlier in the path.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

try:
    from axalon.db.session import init_db, session_scope
    from axalon.db.models import Park, Inspection, Detection
    # Canonical class/severity definitions — never redefine these locally.
    from ml.src.utils import CANONICAL_CLASSES, CLASS2ID, SEVERITY_MAP
except ImportError as exc:
    sys.exit(
        f"[seed_demo_data] Cannot import axalon package: {exc}\n"
        f"Make sure you are running from the repository root or that "
        f"{_REPO_ROOT} is importable."
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARK_ID = "SOLAR_PARK_DEMO"
INSPECTION_IDS = ["DEMO-INSP-001", "DEMO-INSP-002", "DEMO-INSP-003"]

TODAY = date(2026, 5, 23)
INSPECTION_DATES = [
    TODAY,                      # DEMO-INSP-001
    TODAY - timedelta(days=15), # DEMO-INSP-002
    TODAY - timedelta(days=30), # DEMO-INSP-003
]

ROWS = 6
COLS = 8

# Severity → candidate class names, inverted from the canonical SEVERITY_MAP.
# Sorted so a seeded RNG produces identical output across runs regardless of
# dict insertion order upstream.
_SEVERITY_CLASSES: dict[str, list[str]] = {}
for _cls, _sev in SEVERITY_MAP.items():
    _SEVERITY_CLASSES.setdefault(_sev, []).append(_cls)
for _sev in _SEVERITY_CLASSES:
    _SEVERITY_CLASSES[_sev].sort()

# Approximate distribution weights: 10% CRITICAL, 15% HIGH, 50% MEDIUM, 25% LOW
_SEVERITY_WEIGHTS = [("CRITICAL", 0.10), ("HIGH", 0.15), ("MEDIUM", 0.50), ("LOW", 0.25)]
_SEVERITY_POOL = []
for sev, weight in _SEVERITY_WEIGHTS:
    _SEVERITY_POOL.extend([sev] * int(weight * 100))

PANELS_PER_INSPECTION = 20   # roughly 20 distinct panels per inspection
MAX_DETECTIONS_PER_PANEL = 3  # 1–3 detections per selected panel

# ---------------------------------------------------------------------------
# Helper: pick a class consistent with a given severity
# ---------------------------------------------------------------------------

def _pick_class_for_severity(rng: random.Random, severity: str) -> str:
    return rng.choice(_SEVERITY_CLASSES[severity])


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

def seed(db_url: str = "sqlite:///axalon.db") -> None:
    init_db(db_url)

    with session_scope() as session:
        # ------------------------------------------------------------------
        # 1. Idempotent teardown — remove old demo data in dependency order
        # ------------------------------------------------------------------
        session.query(Detection).filter(
            Detection.inspection_id.in_(INSPECTION_IDS)
        ).delete(synchronize_session=False)

        session.query(Inspection).filter(
            Inspection.id.in_(INSPECTION_IDS)
        ).delete(synchronize_session=False)

        session.query(Park).filter(Park.id == PARK_ID).delete(
            synchronize_session=False
        )

        session.flush()

        # ------------------------------------------------------------------
        # 2. Create Park
        # ------------------------------------------------------------------
        park = Park(
            id=PARK_ID,
            name="Solar Park Demo",
            mode="auto",
            rows=ROWS,
            cols=COLS,
            total_panels=ROWS * COLS,  # 48
        )
        session.add(park)
        session.flush()

        # ------------------------------------------------------------------
        # 3. Create Inspections + Detections
        # ------------------------------------------------------------------
        rng = random.Random(42)
        total_detections = 0

        all_panels = [
            (r, c) for r in range(1, ROWS + 1) for c in range(1, COLS + 1)
        ]

        for insp_id, insp_date in zip(INSPECTION_IDS, INSPECTION_DATES):
            # Build detection rows first so we can compute summary
            detection_rows = []
            severity_counts: dict[str, int] = {
                "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0
            }

            selected_panels = rng.sample(all_panels, PANELS_PER_INSPECTION)

            for (row, col) in selected_panels:
                num_detections = rng.randint(1, MAX_DETECTIONS_PER_PANEL)
                panel_id = f"R{row}-C{col}"
                image_id = f"img_{row:02d}_{col:02d}"
                lat = 0.0 + (row - 1) * 0.001
                lon = 0.0 + (col - 1) * 0.001
                gps_json = json.dumps({"lat": lat, "lon": lon})

                for _ in range(num_detections):
                    severity = rng.choice(_SEVERITY_POOL)
                    cls_name = _pick_class_for_severity(rng, severity)
                    cls_id = CLASS2ID[cls_name]
                    confidence = round(rng.uniform(0.30, 0.99), 4)

                    detection_rows.append(
                        Detection(
                            inspection_id=insp_id,
                            fault_id=None,
                            image_id=image_id,
                            panel_id=panel_id,
                            class_=cls_name,
                            class_id=cls_id,
                            severity=severity,
                            confidence=confidence,
                            bbox=None,
                            gps=gps_json,
                        )
                    )
                    severity_counts[severity] += 1

            summary_json = json.dumps(severity_counts)
            insp_total = sum(severity_counts.values())
            total_detections += insp_total

            inspection = Inspection(
                id=insp_id,
                park_id=PARK_ID,
                flight_date=insp_date.isoformat(),
                total_images=200,
                total_detections=insp_total,
                summary=summary_json,
            )
            session.add(inspection)
            session.flush()  # ensure FK exists before adding detections

            session.bulk_save_objects(detection_rows)

        # commit happens automatically on session_scope exit
        print(
            f"Park: {PARK_ID} | Inspections: {len(INSPECTION_IDS)} | "
            f"Detections: {total_detections}"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db_url = os.environ.get("DB_URL", "sqlite:///axalon.db")
    seed(db_url)

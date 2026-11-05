#!/usr/bin/env python3
"""Seed SolarDoctor demo data (idempotent). Every seeded row is labelled source="SIMULATED".

    make seed
    SOLARDOCTOR_DB_URL=sqlite:////tmp/demo.db python scripts/seed.py [--reset] [--offline] [--end YYYY-MM-DD]

Creates 1 admin + 1 technician (passwords from SOLARDOCTOR_SEED_ADMIN_PASSWORD /
SOLARDOCTOR_SEED_TECH_PASSWORD, else generated and printed once), three plants with 30 days of
15-minute telemetry, alerts, faults and Park<->Plant links.  See docs/solardoctor/SEED_PLAN.md.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT / "backend", REPO_ROOT):  # appended: repo root has a platform/ dir that must not shadow stdlib
    if str(p) not in sys.path:
        sys.path.append(str(p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (noise and synthetic clouds)")
    ap.add_argument("--end", help="last UTC day of the window (default: latest complete NASA POWER day)")
    ap.add_argument("--shift-to-now", action="store_true",
                    help="move the NASA weather forward by whole days so the window ends yesterday "
                         "(labelled NASA_POWER_TIME_SHIFTED; solar geometry is recomputed for the shown dates)")
    ap.add_argument("--offline", action="store_true", help="skip NASA POWER; use the labelled synthetic cloud model")
    ap.add_argument("--reset", action="store_true", help="delete SIMULATED rows first (never users or PVDAQ data)")
    ap.add_argument("--force", action="store_true", help="allow running when SOLARDOCTOR_ENV=production")
    ap.add_argument("--cache-dir", default=str(REPO_ROOT / "data" / "cache"))
    args = ap.parse_args(argv)

    if os.getenv("SOLARDOCTOR_ENV", "").lower() == "production" and not args.force:
        print("Refusing to seed demo data with SOLARDOCTOR_ENV=production (use --force).", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from solardoctor.db.session import get_session, init_db
    from solardoctor.seed.builder import SeedError, run_seed

    init_db()
    db = get_session()
    try:
        rep = run_seed(db, days=args.days, seed=args.seed, cache_dir=Path(args.cache_dir),
                       allow_network=not args.offline, reset=args.reset, window_end=args.end,
                       shift_to_now=args.shift_to_now,
                       manifest_path=Path(args.cache_dir) / "seed_manifest.json")
    except SeedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    import datetime as _dt
    age = (_dt.datetime.now(_dt.timezone.utc).date() - rep.window_end.date()).days
    print(f"[SIMULATED] window start {rep.window_start} ({rep.window_note})")
    print(f"[SIMULATED] telemetry ends {rep.window_end:%Y-%m-%d}: the data is ~{age} day(s) old"
          + (f" (weather time-shifted +{rep.shift_days} days)" if rep.shift_days else ""))
    if age > 1:
        print("  Note: the diagnose / 'last 24 h' demo needs fresh telemetry. Either re-seed with --shift-to-now, or run the API with\n"
              "  SOLARDOCTOR_DIAGNOSIS_MAX_TELEMETRY_AGE_H=<hours> and call diagnose with allow_simulated=true.")
    for name, info in rep.plants.items():
        extra = ""
        if info.get("status") == "created":
            extra = f"  irradiance={info['irradiance_source']}  telemetry_rows={info['telemetry_rows']}  alerts={len(info['alerts'])}"
        print(f"  plant {name!r} id={info['id']}: {info['status']}{extra}")
    for email, (role, pw) in rep.created_users.items():
        if pw is None:
            print(f"  user {email} ({role}): already existed, unchanged")
        elif pw == "(from environment)":
            print(f"  user {email} ({role}): created, password from environment")
        else:
            print(f"  user {email} ({role}): created, GENERATED PASSWORD (shown once): {pw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Import a PVDAQ (DOE Solar Data Prize) system as a plant with source="PVDAQ".  REAL data, not simulated.

Online (needs outbound HTTPS to s3://oedi-data-lake, anonymous; pip install pvdaq_access):
    python scripts/import_pvdaq.py --system-id 9068 --start 2024-06-01 --end 2024-06-30

Offline (local files you already downloaded; no network):
    python scripts/import_pvdaq.py --ac-csv 9068_ac_power_data_20240101_20250430.csv \\
        --irr-csv 9068_irradiance_data_20240101_20250430.csv --metadata 9068_system_metadata.json \\
        --start 2024-06-01 --end 2024-06-30

Files are cached under data/cache/pvdaq_<system-id>/.  On network failure the script exits non-zero
with a message; there is no synthetic fallback.  Dataset licence/attribution
terms (OEDI PVDAQ, DOE/NREL) must be checked on data.openei.org and recorded in THIRD_PARTY_NOTICES.md before the
data is shown to users; this script has not verified them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT / "backend", REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.append(str(p))


def main(argv=None) -> int:
    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system-id", type=int, default=9068)
    ap.add_argument("--start", default="2024-06-01", help="first UTC day (YYYY-MM-DD)")
    ap.add_argument("--end", default="2024-06-30", help="last UTC day, inclusive")
    ap.add_argument("--ac-csv", type=Path, help="offline: <id>_ac_power_data*.csv")
    ap.add_argument("--irr-csv", type=Path, help="offline: <id>_irradiance_data*.csv")
    ap.add_argument("--metadata", type=Path, help="offline: <id>_system_metadata.json")
    ap.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "data" / "cache")
    args = ap.parse_args(argv)

    from solardoctor.seed import pvdaq

    start, end = pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC")
    offline = [args.ac_csv, args.irr_csv, args.metadata]
    try:
        if any(offline):
            if not all(offline):
                ap.error("offline mode needs --ac-csv, --irr-csv and --metadata together")
            files = dict(ac=args.ac_csv, irr=args.irr_csv, meta=args.metadata)
        else:
            files = pvdaq.download_prize_files(args.system_id, args.cache_dir / f"pvdaq_{args.system_id}", start, end)
        mapped = pvdaq.map_pvdaq(files["ac"], files["irr"], files["meta"], start, end)
    except pvdaq.PvdaqUnavailable as exc:
        print(f"ERROR: {exc}\nNo data was imported (there is no synthetic fallback for PVDAQ).", file=sys.stderr)
        return 1

    from solardoctor.db.session import get_session, init_db
    init_db()
    db = get_session()
    try:
        res = pvdaq.write_mapped(db, mapped)
    finally:
        db.close()
    for n in mapped.meta_notes:
        print("  note:", n)
    print(f"[PVDAQ] plant {res['name']!r} id={res['plant_id']}: {res['rows']} telemetry rows, {res['start']} .. {res['end']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

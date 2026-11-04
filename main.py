"""
main.py — CLI entry point for the Axalon Solar Inspection Platform.

Usage examples:

    # Inspect a single thermal+RGB pair
    python main.py inspect \\
        --thermal path/to/thermal_001.jpg \\
        --rgb path/to/rgb_001.jpg \\
        --park-id SOLAR_PARK_01

    # Batch inspect a full flight folder
    python main.py batch \\
        --folder path/to/flight_mission/ \\
        --park-id SOLAR_PARK_01 \\
        --altitude 45

    # Start the REST API server
    python main.py api
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── CLI parser ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axalon",
        description="Axalon Systems — Solar Anomaly Detection Platform",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # inspect
    p_inspect = sub.add_parser("inspect", help="Inspect a single thermal+RGB image pair")
    p_inspect.add_argument("--thermal", required=True, help="Path to thermal IR image")
    p_inspect.add_argument("--rgb", default=None, help="Path to RGB image (optional)")
    p_inspect.add_argument("--park-id", default="unknown", help="Solar park identifier")
    p_inspect.add_argument("--altitude", type=float, default=40.0, help="Drone altitude in meters")
    p_inspect.add_argument("--output", default="output", help="Output directory")
    p_inspect.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold")
    p_inspect.add_argument("--device", default="0", help="Device: '0' for GPU, 'cpu' for CPU")

    # batch
    p_batch = sub.add_parser("batch", help="Inspect a full flight mission folder")
    p_batch.add_argument("--folder", required=True, help="Flight folder (thermal/ + rgb/ subfolders)")
    p_batch.add_argument("--park-id", default="unknown", help="Solar park identifier")
    p_batch.add_argument("--altitude", type=float, default=40.0, help="Drone altitude in meters")
    p_batch.add_argument("--output", default="output", help="Output directory")
    p_batch.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold")
    p_batch.add_argument("--device", default="0", help="Device: '0' for GPU, 'cpu' for CPU")

    # api
    p_api = sub.add_parser("api", help="Start the FastAPI REST server")
    p_api.add_argument("--host", default="0.0.0.0")
    p_api.add_argument("--port", type=int, default=8000)
    p_api.add_argument("--workers", type=int, default=1)

    return parser


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_inspect(args):
    from axalon.pipeline.orchestrator import InspectionOrchestrator
    from axalon.reporting.report import generate_json_report, generate_excel_report
    from axalon.reporting.geojson_writer import write_geojson

    print(f"Inspecting: {args.thermal}")
    orch = InspectionOrchestrator(
        conf=args.conf,
        device=args.device,
        output_dir=args.output,
    )
    result = orch.inspect_pair(
        thermal_path=args.thermal,
        rgb_path=args.rgb,
        park_id=args.park_id,
        altitude_m=args.altitude,
    )

    out_dir = Path(args.output) / result["job_id"]
    generate_json_report(result, out_dir / "inspection_report.json")

    print(f"\nResults saved to: {out_dir}")
    print(f"Total detections: {result['total_detections']}")
    for sev, count in result["summary"].items():
        print(f"  {sev}: {count}")

    if result.get("annotated_thermal"):
        print(f"Annotated thermal: {result['annotated_thermal']}")


def cmd_batch(args):
    from axalon.pipeline.orchestrator import InspectionOrchestrator
    from axalon.reporting.report import (
        generate_excel_report,
        generate_json_report,
        generate_pdf_report,
    )
    from axalon.reporting.geojson_writer import write_geojson

    print(f"Batch inspecting folder: {args.folder}")
    orch = InspectionOrchestrator(
        conf=args.conf,
        device=args.device,
        output_dir=args.output,
    )

    from tqdm import tqdm
    pbar = tqdm(total=0, desc="Processing")

    def progress_cb(processed, total):
        pbar.total = total
        pbar.n = processed
        pbar.refresh()

    result = orch.inspect_folder(
        folder=args.folder,
        park_id=args.park_id,
        altitude_m=args.altitude,
        progress_callback=progress_cb,
    )
    pbar.close()

    out_dir = Path(args.output) / result["batch_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    generate_json_report(result, out_dir / "inspection_report.json")
    generate_excel_report(result, out_dir / "inspection_report.xlsx")
    write_geojson(result, out_dir / "park_anomaly_map.geojson")
    try:
        generate_pdf_report(result, out_dir / "inspection_report.pdf")
    except Exception as exc:
        print(f"PDF report skipped: {exc}")

    print(f"\nBatch complete. Reports saved to: {out_dir}")
    print(f"Total images: {result['total_images']}")
    print(f"Total detections: {result['total_detections']}")
    for sev, count in result["summary"].items():
        print(f"  {sev}: {count}")


def cmd_api(args):
    import uvicorn
    print(f"Starting API server on http://{args.host}:{args.port}")
    uvicorn.run(
        "axalon.api.app:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "inspect": cmd_inspect,
        "batch":   cmd_batch,
        "api":     cmd_api,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()

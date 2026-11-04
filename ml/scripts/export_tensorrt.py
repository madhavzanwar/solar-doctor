"""
Export YOLO11m to TensorRT engine for Jetson Orin Nano.

Run this ON THE JETSON, not on a desktop GPU.
Usage:
    python ml/scripts/export_tensorrt.py \
        --weights ml/checkpoints/best.pt \
        --out     ml/checkpoints/best.engine
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="ml/checkpoints/best.pt")
    parser.add_argument("--out", default="ml/checkpoints/best.engine")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--half", action="store_true", default=True,
                        help="FP16 — halves memory, 2x speed on Jetson")
    parser.add_argument("--batch", type=int, default=1,
                        help="Batch size for engine — use 1 for sequential inference")
    args = parser.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.weights)
    model.export(
        format="engine",
        imgsz=args.imgsz,
        half=args.half,
        batch=args.batch,
        device=0,
        workspace=4,       # GB of TensorRT workspace
        verbose=True,
    )
    # Ultralytics saves as best.engine in same dir as best.pt
    engine_src = Path(args.weights).with_suffix(".engine")
    engine_dst = Path(args.out)
    if engine_src != engine_dst and engine_src.exists():
        engine_src.rename(engine_dst)
    print(f"TensorRT engine saved: {engine_dst}")
    print(f"Size: {engine_dst.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

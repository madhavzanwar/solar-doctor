"""Export a bundle to ONNX (opset 17) and check onnxruntime parity against PyTorch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

TOL = 1e-4


def load_bundle(bundle: Path):
    from safetensors.torch import load_file
    from solardoctor.vision.model_def import build_model
    cfg = json.loads((Path(bundle) / "config.json").read_text())
    model = build_model(cfg, pretrained=False)
    model.load_state_dict(load_file(str(Path(bundle) / "model.safetensors")))
    return model.eval(), cfg


def export_onnx(model, img_size: int, out: Path, real_inputs: torch.Tensor | None = None, n_random: int = 8,
                report: Path | None = None) -> dict:
    """Writes `out`, returns (and optionally saves) the parity record; raises if max |diff| > 1e-4."""
    import onnxruntime as ort
    model = model.cpu().eval()
    dummy = torch.randn(1, 3, img_size, img_size)
    torch.onnx.export(model, dummy, str(out), opset_version=17, input_names=["pixel_values"],
                      output_names=["logits"], dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
                      dynamo=False)
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    g = torch.Generator().manual_seed(0)
    sets = {"random": torch.randn(n_random, 3, img_size, img_size, generator=g)}
    if real_inputs is not None:
        sets["real"] = real_inputs
    rec = {"opset": 17, "tolerance": TOL, "max_abs_diff": {}}
    for k, x in sets.items():
        with torch.no_grad():
            ref = model(x).numpy()
        got = sess.run(["logits"], {"pixel_values": x.numpy()})[0]
        rec["max_abs_diff"][k] = float(np.abs(ref - got).max())
    rec["passed"] = max(rec["max_abs_diff"].values()) <= TOL
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(json.dumps(rec, indent=2))
    if not rec["passed"]:
        raise AssertionError(f"ONNX parity failed: {rec}")
    return rec


def main() -> None:
    import pandas as pd
    from ml.rgb.dataset import RGBPanelDataset

    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--manifest", default="ml/rgb/data/manifest.csv")
    ap.add_argument("--raw-dir", default="ml/rgb/data/raw")
    ap.add_argument("--n-real", type=int, default=8)
    ap.add_argument("--report", default="ml/rgb/reports/onnx_parity.json")
    a = ap.parse_args()
    model, cfg = load_bundle(Path(a.bundle))
    rows = pd.read_csv(a.manifest)
    rows = rows[rows.split == "test"].head(a.n_real).reset_index(drop=True)
    ds = RGBPanelDataset(rows, Path(a.raw_dir), cfg, train=False)
    real = torch.stack([ds[i][0] for i in range(len(ds))])
    rec = export_onnx(model, cfg["img_size"], Path(a.bundle) / "model.onnx", real, report=Path(a.report))
    print(rec)


if __name__ == "__main__":
    main()

"""Aggregate run JSONs into reports/bakeoff.json + BAKEOFF.md. Every number comes from a JSON file; missing = "not run"."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from solardoctor.vision.model_def import CLASSES

HERE = Path(__file__).parent


def _read(p: Path):
    return json.loads(p.read_text()) if Path(p).exists() else None


def _ms(vals: list[float]):
    return {"mean": float(np.mean(vals)), "std": float(np.std(vals)), "n": len(vals)} if vals else None


def build(runs: Path, reports: Path) -> dict:
    configs = {}
    for d in sorted(p for p in Path(runs).iterdir() if p.is_dir()) if Path(runs).exists() else []:
        folds = [json.loads(f.read_text()) for f in sorted((d / "cv").glob("fold*.json"))]
        final = _read(d / "final.json")
        if not folds and not final:
            continue
        configs[d.name] = {
            "val_macro_f1": _ms([f["val"]["macro_f1"] for f in folds]),
            "val_accuracy": _ms([f["val"]["accuracy"] for f in folds]),
            "test_macro_f1_over_folds": _ms([f["test"]["macro_f1"] for f in folds]),
            "params": final["params"] if final else None,
            "size_mb": final["size_mb"] if final else None,
            "cpu_p95_ms": final["latency"]["default"]["p95_ms"] if final else None,
            "cpu_p95_ms_1thread": final["latency"]["threads1"]["p95_ms"] if final else None,
            "final": final}
    ranked = [c for c in configs if configs[c]["val_macro_f1"]]
    inf = float("inf")
    ranked.sort(key=lambda c: (-round(configs[c]["val_macro_f1"]["mean"], 4),
                               configs[c]["cpu_p95_ms"] if configs[c]["cpu_p95_ms"] is not None else inf,
                               configs[c]["size_mb"] if configs[c]["size_mb"] is not None else inf))
    return {"configs": configs, "winner": ranked[0] if ranked else None,
            "ood": _read(reports / "ood.json"), "xai": _read(reports / "xai_faithfulness.json"),
            "onnx": _read(reports / "onnx_parity.json")}


def _f(x, d=4, pct=False):
    if x is None:
        return "not run"
    return f"{x * 100:.2f} %" if pct else f"{x:.{d}f}"


def _pm(m, d=4):
    return "not run" if not m else f"{m['mean']:.{d}f} ± {m['std']:.{d}f}"


METHOD = """## Method

- Source data: Hugging Face dataset `metalmerge/solar-panel-inspection` @ 1b62720 (a 789-image mirror/subset of Kaggle
  "Solar Panel Images Clean and Faulty"; licence unknown on both: trained privately, never redistributed).
- Exact duplicates removed by sha256; near-duplicates grouped (pHash or dHash Hamming <= 6 incl. flip/rotation variants, or DINOv2-small cosine >= 0.95; transitive).
- Group-aware stratified split 70/15/15 (train/val/test) so a duplicate group never spans splits; 5-fold
  StratifiedGroupKFold over train+val. The test split is never used for selection.
- Same splits and seeds (seed + fold) for every config; epoch selection and model selection by validation macro-F1.
- Class imbalance: class-weighted cross-entropy. Temperature scaling is fitted on the validation split only, the same split used for epoch
  selection (so calibration on val is slightly optimistic; the reported test ECE/NLL are held-out).
- B0_gray100 is a PyTorch reproduction of the original Keras VGG16 (100x100 grayscale).
"""

CONTEXT = """## Comparison context

All numbers above are measured on the deduplicated mirror (metalmerge/solar-panel-inspection, 789 images, 724 after
exact-duplicate removal) with leak-free grouped splits. They are not comparable one-to-one with figures published on the
original Kaggle set: our original slides 91.46 % accuracy and HybridSolarNet (arXiv 2601.02928) 92.37 %. Those are
reported by their authors, were not reproduced here, and can include near-duplicate leakage across splits.
"""


def render(d: dict) -> str:
    L = ["# SolarDoctor RGB classifier bake-off", "", METHOD, "## Model comparison (5-fold CV, mean ± std)", "",
         "| config | val macro-F1 (epoch selected on this fold, optimistic) | held-out test macro-F1 (mean ± std of the 5 "
         "fold models) | val accuracy | params | size MB | CPU p95 ms |",
         "|---|---|---|---|---|---|---|"]
    for n, c in d["configs"].items():
        L.append(f"| {n}{' (winner)' if n == d['winner'] else ''} | {_pm(c['val_macro_f1'])} | "
                 f"{_pm(c['test_macro_f1_over_folds'])} | {_pm(c['val_accuracy'])} | "
                 f"{'not run' if c['params'] is None else format(c['params'], ',')} | {_f(c['size_mb'], 1)} | "
                 f"{_f(c['cpu_p95_ms'], 1)} |")
    if not d["configs"]:
        L.append("| not run | | | | | | |")
    missing = [n for n, c in d["configs"].items() if not c["final"] or not c["val_macro_f1"]]
    if missing:
        L += ["", "Not finished / not run (no complete result): " + ", ".join(missing)]
    L += ["", "The CV val column is optimistic: each fold's epoch is selected on that same fold. The held-out test "
          "column is the unbiased estimate.", "",
          f"Winner (val macro-F1 mean; ties: latency, then size): **{d['winner'] or 'not run'}**", ""]
    fin = d["configs"][d["winner"]]["final"] if d["winner"] else None
    L.append("## Winner: held-out test metrics")
    if not fin:
        L += ["", "not run", ""]
    else:
        raw, cal = fin["test_raw"], fin["test_calibrated"]
        L += ["", f"Model version: `{fin['model_version']}`; temperature {_f(fin['temperature'])}", "",
              "| metric | raw | calibrated |", "|---|---|---|",
              f"| macro-F1 | {_f(raw['macro_f1'])} | {_f(cal['macro_f1'])} |",
              f"| accuracy | {_f(raw['accuracy'])} | {_f(cal['accuracy'])} |",
              f"| NLL | {_f(raw['nll'])} | {_f(cal['nll'])} |",
              f"| ECE (15 bins) | {_f(raw['ece'])} | {_f(cal['ece'])} |", "",
              "| class | recall | F1 |", "|---|---|---|"]
        L += [f"| {c} | {_f(r)} | {_f(f)} |" for c, r, f in
              zip(CLASSES, cal["per_class_recall"], cal["per_class_f1"])]
        L += ["", "Confusion matrix (rows = true, cols = predicted):", "", "```"]
        L += [" ".join(f"{v:4d}" for v in row) for row in cal["confusion_matrix"]] + ["```", ""]
    L += ["## OOD guard (AUROC, OOD = positive)", ""]
    if d["ood"]:
        L += ["Selection protocol: the 100 COCO images are split 50/50 (seed 42) into OOD-dev and OOD-test. Method "
              "(best AUROC) and threshold (95th percentile of in-distribution scores) were chosen on the **val** split "
              "+ OOD-dev only. Numbers below are on the **test** split + OOD-test at each method's frozen threshold.", "",
              "| method | AUROC | threshold | TPR | FPR |", "|---|---|---|---|---|"]
        L += [f"| {m}{' (chosen)' if m == d['ood']['best'] else ''} | {_f(v['auroc'])} | {_f(v['threshold'])} | "
              f"{_f(v['tpr'])} | {_f(v['fpr'])} |" for m, v in d["ood"]["test"]["methods"].items()]
    else:
        L.append("not run")
    L += ["", "## XAI faithfulness (deletion: lower is better; insertion: higher is better)", ""]
    if d["xai"]:
        L += ["| method | deletion AUC | insertion AUC | test images |", "|---|---|---|---|"]
        L += [f"| {m} | {_pm(d['xai'][m]['deletion'])} | {_pm(d['xai'][m]['insertion'])} | {d['xai'][m]['n']} |"
              for m in ("gradcam", "lime")]
    else:
        L.append("not run")
    L += ["", "## ONNX parity", ""]
    o = d["onnx"]
    L.append("not run" if not o else f"max abs logit diff {o['max_abs_diff']} (tolerance {o['tolerance']}): "
             f"{'PASS' if o['passed'] else 'FAIL'}")
    return "\n".join(L) + "\n\n" + CONTEXT


def main() -> None:
    reports = HERE / "reports"
    d = build(HERE / "runs", reports)
    reports.mkdir(exist_ok=True)
    (reports / "bakeoff.json").write_text(json.dumps(d, indent=2))
    (reports / "BAKEOFF.md").write_text(render(d), encoding="utf-8")
    print(f"wrote {reports / 'BAKEOFF.md'}")


if __name__ == "__main__":
    main()

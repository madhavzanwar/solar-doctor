"""Fast CPU tests for ml/rgb training, calibration, faithfulness, ONNX, OOD selection and report (no network)."""
import json

import numpy as np
import pytest
import torch
from torch.utils.data import TensorDataset

timm = pytest.importorskip("timm")
pytest.importorskip("onnxruntime")

from ml.rgb import calibrate, configs, report  # noqa: E402
from ml.rgb.export_onnx import export_onnx, load_bundle  # noqa: E402
from ml.rgb.faithfulness import deletion_insertion_auc  # noqa: E402
from ml.rgb.ood_eval import evaluate_ood  # noqa: E402
from ml.rgb.train import finalize, metrics, run_one  # noqa: E402
from solardoctor.vision.model_def import CLASSES, build_model  # noqa: E402

BUNDLE = {"arch": "timm", "backbone_id": "resnet18", "img_size": 32, "grayscale": False,
          "mean": [0.5] * 3, "std": [0.5] * 3, "gradcam_target_layer": "layer4", "gradcam_reshape": None}
HP = {**configs._HP, "epochs": 2, "batch_size": 16, "warmup_epochs": 1, "amp": False, "ema": 0.9}


def toy_ds(n=48, seed=0):
    g = torch.Generator().manual_seed(seed)
    y = torch.arange(n) % 6
    x = torch.randn(n, 3, 32, 32, generator=g) * 0.1
    x[torch.arange(n), :, 0, 0] = y.float()[:, None]  # trivially learnable signal
    return TensorDataset(x, y)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    tr, va, te = toy_ds(48, 0), toy_ds(24, 1), toy_ds(24, 2)
    model, res = run_one(BUNDLE, HP, tr, va, te, np.ones(6), "cpu", 0, pretrained=False)
    root = tmp_path_factory.mktemp("ckpt")
    final = finalize("toy", BUNDLE, model, res, root / "run", root / "ckpt")
    return model, final


def test_bundle_roundtrip(trained, tmp_path):
    model, final = trained
    from pathlib import Path
    cfg = json.loads((Path(final["bundle"]) / "config.json").read_text())
    assert cfg["classes"] == list(CLASSES) and cfg["temperature"] == final["temperature"] and cfg["metrics"]
    reloaded, _ = load_bundle(Path(final["bundle"]))
    x = torch.randn(3, 3, 32, 32)
    assert torch.allclose(model.eval()(x), reloaded(x), atol=1e-6)
    assert (Path(final["bundle"]) / "model.safetensors").exists() and final["latency"]["threads1"]["p95_ms"] > 0


def test_onnx_parity(trained, tmp_path):
    model, _ = trained
    rec = export_onnx(model, 32, tmp_path / "m.onnx", real_inputs=torch.randn(2, 3, 32, 32),
                      report=tmp_path / "p.json")
    assert rec["passed"] and (tmp_path / "p.json").exists()


def test_temperature_recovers_known_value():
    rng = np.random.default_rng(0)
    z = rng.normal(size=(20000, 6)) * 2
    p = calibrate.softmax(z)
    y = np.array([rng.choice(6, p=r) for r in p])
    assert abs(calibrate.fit_temperature(z * 2.0, y) - 2.0) < 0.1  # logits inflated by 2 -> T = 2


def test_ece_calibrated_near_zero():
    rng = np.random.default_rng(1)
    p = calibrate.softmax(rng.normal(size=(30000, 6)) * 2)
    y = np.array([rng.choice(6, p=r) for r in p])
    assert calibrate.ece(p, y) < 0.02
    assert calibrate.ece(np.eye(6)[np.zeros(100, int)], np.ones(100, int)) == pytest.approx(1.0)


def test_faithfulness_toy_model():
    # class prob = mean of channel 0 in the top-left quadrant -> that quadrant is the truly salient region
    def predict(x):
        p = x[:, 0, :8, :8].mean((1, 2)).clamp(0, 1)
        return torch.stack([1 - p, p], 1)

    x = torch.zeros(1, 3, 16, 16); x[:, 0, :8, :8] = 1.0
    good = np.zeros((16, 16)); good[:8, :8] = 1
    bad = 1 - good
    g, b = deletion_insertion_auc(predict, x, good, 1), deletion_insertion_auc(predict, x, bad, 1)
    assert g["deletion"] < b["deletion"] and g["insertion"] > b["insertion"]


def test_metrics_shape():
    m = metrics(np.eye(6)[[0, 1, 2, 3, 4, 5]], np.arange(6))
    assert m["macro_f1"] == 1.0 and np.trace(m["confusion_matrix"]) == 6


def test_ood_selection_with_fake_scorers():
    rng = np.random.default_rng(0)
    ins = {"a": rng.normal(0, 1, 200), "b": rng.normal(0, 1, 200)}
    ood = {"a": rng.normal(5, 1, 100), "b": rng.normal(0, 1, 100)}
    r = evaluate_ood(ins, ood)
    assert r["best"] == "a" and r["methods"]["a"]["auroc"] > 0.99 and r["methods"]["a"]["fpr"] <= 0.06


def test_gradcam_layers_exist():
    for name, e in configs.CONFIGS.items():
        b = e["bundle"]
        if b["arch"] in ("timm", "torchvision"):
            names = {n for n, _ in build_model(b).named_modules()}
            assert b["gradcam_target_layer"] in names, name


def test_report_renders_and_marks_missing(tmp_path):
    runs, reports = tmp_path / "runs", tmp_path / "reports"
    for cfg, f1 in (("B1", 0.9), ("B2", 0.95)):
        (runs / cfg / "cv").mkdir(parents=True)
        for k in range(5):
            m = metrics(np.eye(6)[np.arange(6)], np.arange(6))
            m["macro_f1"] = f1 + 0.01 * k
            (runs / cfg / "cv" / f"fold{k}.json").write_text(json.dumps({"val": m, "test": m}))
    d = report.build(runs, reports)
    assert d["winner"] == "B2"
    md = report.render(d)
    assert md.count("not run") >= 4 and "91.46" in md and "not comparable" in md

from __future__ import annotations

import hashlib
import statistics
import time

import pytest

from solardoctor.vision import VisionModelUnavailable, get_classifier
from solardoctor.vision.model_def import CLASSES


def test_predict_contract(clf, png):
    r = clf.predict(png)
    assert sum(r["probs"].values()) == pytest.approx(1.0, abs=1e-5)
    assert list(r["probs"]) == list(CLASSES)
    probs = [t["prob"] for t in r["top3"]]
    assert len(probs) == 3 and probs == sorted(probs, reverse=True)
    assert r["confidence"] == max(r["probs"].values()) == r["top3"][0]["prob"]
    assert r["predicted_class"] == r["top3"][0]["class"] == max(r["probs"], key=r["probs"].get)
    assert r["model_version"] == "rgb-test-0001"
    assert r["image_sha256"] == hashlib.sha256(png).hexdigest()
    assert r["latency_ms"] > 0
    assert (r["ood_method"], r["ood_score"], r["is_ood"]) == ("none", None, False)


def test_temperature_changes_confidence(bundle_env, png):
    bundle_env(temperature=1.0)
    c1 = get_classifier().predict(png)["confidence"]
    bundle_env(temperature=5.0)
    c5 = get_classifier().predict(png)["confidence"]
    assert c5 < c1


def test_low_confidence_needs_field_check(bundle_env, png):
    bundle_env(temperature=1000.0)  # near-uniform probs
    r = get_classifier().predict(png)
    assert r["needs_field_check"] and r["field_check_reason"] == "low_confidence" and not r["is_ood"]
    assert r["predicted_class"] in CLASSES  # still the argmax


def test_confident_prediction_has_no_flag(bundle_env, png):
    bundle_env(conf_threshold=0.0)
    r = get_classifier().predict(png)
    assert not r["needs_field_check"] and r["field_check_reason"] is None


def test_ood_threshold_and_precedence(bundle_env, png):
    import torch
    from safetensors.torch import save_file
    from solardoctor.vision.model_def import build_autoencoder

    d = bundle_env(temperature=1000.0, ood={"method": "autoencoder", "threshold": -1.0})
    save_file(build_autoencoder(100).state_dict(), str(d / "autoencoder.safetensors"))
    r = get_classifier().predict(png)
    assert r["ood_method"] == "autoencoder" and r["ood_score"] >= 0 and r["is_ood"]
    # low confidence too, but OOD wins
    assert r["needs_field_check"] and r["field_check_reason"] == "out_of_distribution"

    from solardoctor.vision.classifier import reset_classifier
    import json
    cfg = json.loads((d / "config.json").read_text())
    cfg["ood"]["threshold"] = 1e6
    (d / "config.json").write_text(json.dumps(cfg))
    reset_classifier()
    assert not get_classifier().predict(png)["is_ood"]


def test_undecodable_bytes(clf):
    with pytest.raises(ValueError):
        clf.predict(b"definitely not an image")


def test_info_sha256_matches_file(clf):
    info = clf.info()
    import os
    path = os.path.join(os.environ["SOLARDOCTOR_RGB_MODEL_DIR"], "model.safetensors")
    with open(path, "rb") as f:
        assert info["sha256"] == hashlib.sha256(f.read()).hexdigest()
    assert info["classes"] == list(CLASSES) and info["ood"] == {"method": "none", "threshold": 0.0}
    assert info["source"].startswith("local:") and info["conf_threshold"] == 0.6


def test_unavailable_without_dir_or_revision(monkeypatch):
    from solardoctor.vision.classifier import reset_classifier
    for k in ("SOLARDOCTOR_RGB_MODEL_DIR", "SOLARDOCTOR_RGB_MODEL_REVISION"):
        monkeypatch.delenv(k, raising=False)
    reset_classifier()
    with pytest.raises(VisionModelUnavailable):
        get_classifier()


def test_unavailable_on_bad_bundle(tmp_path, monkeypatch):
    from solardoctor.vision.classifier import reset_classifier
    monkeypatch.setenv("SOLARDOCTOR_RGB_MODEL_DIR", str(tmp_path))
    reset_classifier()
    with pytest.raises(VisionModelUnavailable):
        get_classifier()


def test_hf_revision_is_pinned(tmp_path, monkeypatch):
    import huggingface_hub
    from solardoctor.vision.classifier import reset_classifier
    from .conftest import make_bundle

    bundle = make_bundle(tmp_path / "snap")
    calls = []
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda **kw: calls.append(kw) or str(bundle))
    monkeypatch.delenv("SOLARDOCTOR_RGB_MODEL_DIR", raising=False)
    monkeypatch.setenv("SOLARDOCTOR_RGB_MODEL_REVISION", "abc123")
    reset_classifier()
    try:
        clf = get_classifier()
    finally:
        reset_classifier()
    assert calls == [{"repo_id": "solar-doctor/solar-doctor-rgb-defect", "revision": "abc123"}]
    assert clf.info()["source"] == "hf:solar-doctor/solar-doctor-rgb-defect@abc123"


def test_hf_download_failure_is_unavailable(monkeypatch):
    import huggingface_hub
    from solardoctor.vision.classifier import reset_classifier

    def boom(**kw):
        raise OSError("offline")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", boom)
    monkeypatch.delenv("SOLARDOCTOR_RGB_MODEL_DIR", raising=False)
    monkeypatch.setenv("SOLARDOCTOR_RGB_MODEL_REVISION", "abc123")
    reset_classifier()
    with pytest.raises(VisionModelUnavailable, match="offline"):
        get_classifier()


def test_cpu_latency_informational(clf, png, capsys):
    clf.predict(png)
    times = []
    for _ in range(20):
        t = time.perf_counter()
        clf.predict(png)
        times.append((time.perf_counter() - t) * 1000)
    p95 = statistics.quantiles(times, n=20)[-1]
    with capsys.disabled():
        print(f"\n[info] tiny-model CPU predict p95 = {p95:.1f} ms (real p95 target measured on trained model)")

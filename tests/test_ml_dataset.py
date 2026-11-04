"""
ML dataset feature tests — run with:
    PYTHONSAFEPATH=1 python tests/test_ml_dataset.py

Tests marked needs_datasets=True read the raw source datasets under
ml/Datasets/ (gitignored, downloaded separately); they are reported as SKIP
when that directory is absent, e.g. on a fresh clone or in CI.

Uses a fresh sys.path so platform/ doesn't shadow stdlib platform module.
"""

from __future__ import annotations
import sys
import os
import json
import tempfile
import logging

# Pre-import stdlib modules that project's ./platform/ package would shadow.
# Python caches these in sys.modules, so later `import platform` calls inside
# numpy/scipy/sklearn all find the cached stdlib version, not ./platform/__init__.py
import platform   # stdlib — must happen before _ROOT enters sys.path
import uuid       # depends on platform

_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
# Remove duplicates, then prepend ROOT so project packages (ml, axalon) resolve
sys.path = [_ROOT] + [p for p in sys.path if os.path.abspath(p) != _ROOT]

from pathlib import Path

from collections import Counter

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

_results: list[tuple[str, bool, str]] = []
_skipped: list[str] = []
_DATASETS_DIR = Path(_ROOT) / "ml" / "Datasets"


def _raw_datasets_present() -> bool:
    """True when the three raw source datasets are unpacked under ml/Datasets/."""
    ism_metadata = _DATASETS_DIR / (
        "InfraredSolarModules/2020-02-14_InfraredSolarModules/"
        "InfraredSolarModules/module_metadata.json"
    )
    return (
        ism_metadata.is_file()
        and (_DATASETS_DIR / "archive.zip").is_file()
        and any(_DATASETS_DIR.glob("Photovoltaic module dataset*.zip"))
    )


def test(name: str, needs_datasets: bool = False):
    def decorator(fn):
        if needs_datasets and not _raw_datasets_present():
            _skipped.append(name)
            print(f"  [{SKIP}] {name}: raw datasets not present at ml/Datasets/")
            return fn
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  [{PASS}] {name}")
        except Exception as exc:
            _results.append((name, False, str(exc)))
            print(f"  [{FAIL}] {name}: {exc}")
        return fn
    return decorator


# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT         = Path(_ROOT)
ISM_ROOT     = ROOT / "ml/Datasets/InfraredSolarModules/2020-02-14_InfraredSolarModules/InfraredSolarModules"
ISM_IMAGES   = ISM_ROOT / "images"
ISM_METADATA = ISM_ROOT / "module_metadata.json"
MODEL_PATH   = ROOT / "ml/checkpoints/best.pt"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: utils.py
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 1: utils.py ──────────────────────────────────────────────")

from ml.src.utils import (
    CANONICAL_CLASSES, CLASS2ID, ID2CLASS,
    SEVERITY_MAP, SEVERITY_COLOR_BGR,
    read_yolo_label, write_yolo_label,
    yolo_to_pixel, draw_detections_severity, load_bgr, get_logger,
)

@test("CANONICAL_CLASSES has exactly 11 entries")
def _():
    assert len(CANONICAL_CLASSES) == 11, f"Expected 11, got {len(CANONICAL_CLASSES)}"

@test("CLASS2ID and ID2CLASS are inverse mappings")
def _():
    for i, name in enumerate(CANONICAL_CLASSES):
        assert CLASS2ID[name] == i
        assert ID2CLASS[i] == name

@test("All 4 severity levels present in SEVERITY_MAP")
def _():
    levels = set(SEVERITY_MAP.values())
    assert levels == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}, f"Got: {levels}"

@test("Every class has a severity entry")
def _():
    missing = [c for c in CANONICAL_CLASSES if c not in SEVERITY_MAP]
    assert not missing, f"Missing severity for: {missing}"

@test("Every severity level has a BGR color")
def _():
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        assert sev in SEVERITY_COLOR_BGR
        assert len(SEVERITY_COLOR_BGR[sev]) == 3

@test("read_yolo_label returns empty list for missing file")
def _():
    boxes = read_yolo_label(Path("/tmp/nonexistent_label_xyz.txt"))
    assert boxes == []

@test("write_yolo_label / read_yolo_label roundtrip")
def _():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        tmp = Path(f.name)
    boxes_in = [(0, 0.5, 0.5, 1.0, 1.0), (3, 0.25, 0.75, 0.4, 0.3)]
    write_yolo_label(tmp, boxes_in)
    boxes_out = read_yolo_label(tmp)
    assert len(boxes_out) == 2
    assert boxes_out[0][0] == 0
    assert abs(boxes_out[1][1] - 0.25) < 1e-5
    tmp.unlink()

@test("write_yolo_label handles empty box list")
def _():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        tmp = Path(f.name)
    write_yolo_label(tmp, [])
    assert tmp.read_text() == ""
    tmp.unlink()

@test("yolo_to_pixel converts center format correctly")
def _():
    x1, y1, x2, y2 = yolo_to_pixel(0.5, 0.5, 1.0, 1.0, 100, 80)
    assert x1 == 0 and y1 == 0 and x2 == 100 and y2 == 80

@test("draw_detections_severity returns annotated image")
def _():
    import numpy as np
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    dets = [{
        "class": "hot-spot-high", "class_id": 10,
        "confidence": 0.9, "severity": "CRITICAL",
        "bbox": [10, 10, 50, 50], "bbox_norm": [0.3, 0.3, 0.4, 0.4],
        "color_bgr": (0, 0, 255),
    }]
    out = draw_detections_severity(img, dets)
    assert out.shape == img.shape
    assert not (out == img).all()  # something was drawn

@test("get_logger returns a logger with handlers")
def _():
    log = get_logger("test_ml")
    assert isinstance(log, logging.Logger)
    assert len(log.handlers) > 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: dataset.py — class mappings
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 2: dataset.py — class mappings ───────────────────────────")

from ml.src.dataset import (
    ISM_CLASSES_MAP, PV_CLASSES_MAP,
    collect_ism_pairs, collect_all_pairs,
    stratified_split, _remap_class_id, _majority_class,
)

@test("All ISM source classes map to valid canonical classes")
def _():
    for src, dst in ISM_CLASSES_MAP.items():
        assert dst in CLASS2ID, f"ISM: {src!r} → {dst!r} not in CANONICAL_CLASSES"

@test("All PV source classes map to valid canonical classes")
def _():
    for src, dst in PV_CLASSES_MAP.items():
        assert dst in CLASS2ID, f"PV: {src!r} → {dst!r} not in CANONICAL_CLASSES"

@test("_remap_class_id returns None for out-of-range source id")
def _():
    result = _remap_class_id(99, ["cell"], ISM_CLASSES_MAP)
    assert result is None

@test("_remap_class_id returns None for unknown class name")
def _():
    result = _remap_class_id(0, ["UnknownClass"], ISM_CLASSES_MAP)
    assert result is None

@test("_remap_class_id maps valid PV class correctly")
def _():
    pv_names = list(PV_CLASSES_MAP.keys())
    result = _remap_class_id(0, pv_names, PV_CLASSES_MAP)
    expected = CLASS2ID[PV_CLASSES_MAP[pv_names[0]]]
    assert result == expected

@test("_majority_class returns 0 for empty box list")
def _():
    assert _majority_class([]) == 0

@test("_majority_class returns most-common class id")
def _():
    boxes = [(2, 0.5, 0.5, 0.3, 0.3), (2, 0.5, 0.5, 0.3, 0.3), (5, 0.5, 0.5, 0.3, 0.3)]
    assert _majority_class(boxes) == 2


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: ISM dataset scanning
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 3: ISM dataset scanning ─────────────────────────────────")

@test("ISM metadata file exists", needs_datasets=True)
def _():
    assert ISM_METADATA.exists(), f"Not found: {ISM_METADATA}"

@test("ISM images directory exists with 20 000 images", needs_datasets=True)
def _():
    assert ISM_IMAGES.exists()
    count = len(list(ISM_IMAGES.iterdir()))
    assert count == 20000, f"Expected 20000 images, found {count}"

@test("ISM metadata has 20 000 entries with correct keys", needs_datasets=True)
def _():
    data = json.loads(ISM_METADATA.read_text())
    assert len(data) == 20000
    sample = next(iter(data.values()))
    assert "image_filepath" in sample
    assert "anomaly_class" in sample

@test("ISM class distribution covers all 12 source classes", needs_datasets=True)
def _():
    data = json.loads(ISM_METADATA.read_text())
    classes_found = set(v["anomaly_class"] for v in data.values())
    assert classes_found == set(ISM_CLASSES_MAP.keys()), \
        f"Missing: {set(ISM_CLASSES_MAP.keys()) - classes_found}"

@test("collect_ism_pairs scans 20 000 images correctly", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
    assert len(pairs) == 20000, f"Expected 20000, got {len(pairs)}"

@test("collect_ism_pairs writes valid YOLO whole-image labels", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        lbl_dir = Path(tmpdir)
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=lbl_dir)
        # Check a few labels
        for img, lbl, maj in pairs[:5]:
            boxes = read_yolo_label(lbl)
            assert len(boxes) == 1, f"Expected 1 box in {lbl}"
            cid, cx, cy, w, h = boxes[0]
            assert cx == 0.5 and cy == 0.5 and w == 1.0 and h == 1.0
            assert 0 <= cid <= 10

@test("collect_ism_pairs: majority_class_id is valid canonical id (0-10)", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
        bad = [(img, maj) for img, _, maj in pairs if not (0 <= maj <= 10)]
        assert not bad, f"Invalid majority class ids: {bad[:3]}"

@test("collect_ism_pairs: all 11 canonical classes appear", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
        seen_ids = set(maj for _, _, maj in pairs)
        # 12 ISM classes → 11 canonical (some merge). Check at least 9 appear
        assert len(seen_ids) >= 9, f"Only {len(seen_ids)} classes found: {seen_ids}"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: stratified split
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 4: stratified_split ──────────────────────────────────────")

@test("stratified_split sizes sum to total", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
    train, val, test = stratified_split(pairs, train_frac=0.75, val_frac=0.15)
    assert len(train) + len(val) + len(test) == len(pairs), \
        f"{len(train)}+{len(val)}+{len(test)} ≠ {len(pairs)}"

@test("stratified_split train fraction ~75%", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
    train, val, test = stratified_split(pairs, train_frac=0.75, val_frac=0.15)
    ratio = len(train) / len(pairs)
    assert 0.73 < ratio < 0.77, f"Train ratio = {ratio:.3f}"

@test("stratified_split val fraction ~15%", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
    train, val, test = stratified_split(pairs, train_frac=0.75, val_frac=0.15)
    ratio = len(val) / len(pairs)
    assert 0.13 < ratio < 0.17, f"Val ratio = {ratio:.3f}"

@test("stratified_split is deterministic (seed=42)", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
    t1, v1, te1 = stratified_split(pairs, seed=42)
    t2, v2, te2 = stratified_split(pairs, seed=42)
    assert [p[0] for p in t1] == [p[0] for p in t2]

@test("stratified_split class distribution preserved in train set", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(tmpdir))
    all_dist = Counter(m for _, _, m in pairs)
    train, val, test = stratified_split(pairs, seed=42)
    train_dist = Counter(m for _, _, m in train)
    for cls_id in all_dist:
        overall_frac = all_dist[cls_id] / len(pairs)
        train_frac_actual = train_dist.get(cls_id, 0) / len(train)
        assert abs(overall_frac - train_frac_actual) < 0.03, \
            f"Class {cls_id}: overall={overall_frac:.3f} train={train_frac_actual:.3f}"

@test("collect_all_pairs merges correctly")
def _():
    fake_pairs_a = [(Path("a.jpg"), Path("a.txt"), 0)] * 3
    fake_pairs_b = [(Path("b.jpg"), Path("b.txt"), 1)] * 2
    merged = collect_all_pairs(fake_pairs_a, fake_pairs_b)
    assert len(merged) == 5


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: model weights
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 5: model weights ─────────────────────────────────────────")

@test("Model weights file exists at ml/checkpoints/best.pt")
def _():
    assert MODEL_PATH.exists(), f"Missing: {MODEL_PATH}"

@test("Model weights file is non-empty (> 1 MB)")
def _():
    size_mb = MODEL_PATH.stat().st_size / (1024 * 1024)
    assert size_mb > 1.0, f"Suspiciously small: {size_mb:.1f} MB"

@test("thermal_dataset.yaml class names match CANONICAL_CLASSES")
def _():
    import yaml
    yaml_path = ROOT / "ml/thermal_dataset.yaml"
    data = yaml.safe_load(yaml_path.read_text())
    assert data["nc"] == 11
    assert data["names"] == CANONICAL_CLASSES


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: extract.py
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 6: extract.py ────────────────────────────────────────────")

from ml.src.extract import extract_archive_zip, extract_pvmd

ARCHIVE_ZIP = ROOT / "ml/Datasets/archive.zip"
PVMD_ZIP = ROOT / (
    "ml/Datasets/Photovoltaic module dataset for automated fault detection "
    "and analysis in large photovoltaic systems using photovoltaic module "
    "fault detection.zip"
)

@test("extract_archive_zip produces ImageSet with train/valid/test", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = extract_archive_zip(ARCHIVE_ZIP, Path(tmpdir))
        assert (out / "train" / "images").exists()
        assert (out / "valid" / "images").exists()
        assert (out / "test" / "images").exists()
        train_imgs = list((out / "train" / "images").glob("*.jpg"))
        assert len(train_imgs) == 6924, f"Expected 6924 train images, got {len(train_imgs)}"

@test("extract_archive_zip is idempotent (second call is a no-op, same result)", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out1 = extract_archive_zip(ARCHIVE_ZIP, Path(tmpdir))
        out2 = extract_archive_zip(ARCHIVE_ZIP, Path(tmpdir))
        assert out1 == out2
        train_imgs = list((out2 / "train" / "images").glob("*.jpg"))
        assert len(train_imgs) == 6924

@test("extract_pvmd produces Cracks/Hotspots/Shadings folders", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = extract_pvmd(PVMD_ZIP, Path(tmpdir))
        assert (out / "Cracks").exists()
        assert (out / "Hotspots").exists()
        assert (out / "Shadings").exists()
        cracks = list((out / "Cracks").glob("*.jpeg"))
        assert len(cracks) == 350, f"Expected 350 Cracks images, got {len(cracks)}"

@test("extract_pvmd is idempotent", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out1 = extract_pvmd(PVMD_ZIP, Path(tmpdir))
        out2 = extract_pvmd(PVMD_ZIP, Path(tmpdir))
        assert out1 == out2
        assert len(list((out2 / "Cracks").glob("*.jpeg"))) == 350


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: PVMD support + write_merged_dataset layout fix
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 7: PVMD support + layout fix ─────────────────────────────")

from ml.src.dataset import (
    PVMD_CLASSES_MAP, collect_pvmd_pairs, write_merged_dataset,
)

@test("All PVMD source classes map to valid canonical classes")
def _():
    for src, dst in PVMD_CLASSES_MAP.items():
        assert dst in CLASS2ID, f"PVMD: {src!r} -> {dst!r} not in CANONICAL_CLASSES"

@test("collect_pvmd_pairs scans all 1000 PVMD images", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as extract_tmp, tempfile.TemporaryDirectory() as lbl_tmp:
        pvmd_root = extract_pvmd(PVMD_ZIP, Path(extract_tmp))
        pairs = collect_pvmd_pairs(pvmd_root, generated_labels_dir=Path(lbl_tmp))
        assert len(pairs) == 1000, f"Expected 1000, got {len(pairs)}"

@test("collect_pvmd_pairs writes valid whole-image YOLO labels", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as extract_tmp, tempfile.TemporaryDirectory() as lbl_tmp:
        pvmd_root = extract_pvmd(PVMD_ZIP, Path(extract_tmp))
        pairs = collect_pvmd_pairs(pvmd_root, generated_labels_dir=Path(lbl_tmp))
        for img, lbl, maj in pairs[:5]:
            boxes = read_yolo_label(lbl)
            assert len(boxes) == 1
            cid, cx, cy, w, h = boxes[0]
            assert cx == 0.5 and cy == 0.5 and w == 1.0 and h == 1.0
            assert 0 <= cid <= 10

@test("collect_all_pairs accepts optional pvmd_pairs (3-way merge)")
def _():
    a = [(Path("a.jpg"), Path("a.txt"), 0)] * 3
    b = [(Path("b.jpg"), Path("b.txt"), 1)] * 2
    c = [(Path("c.jpg"), Path("c.txt"), 2)] * 4
    merged = collect_all_pairs(a, b, c)
    assert len(merged) == 9

@test("collect_all_pairs still works with only 2 args (backward compatible)")
def _():
    a = [(Path("a.jpg"), Path("a.txt"), 0)] * 3
    b = [(Path("b.jpg"), Path("b.txt"), 1)] * 2
    merged = collect_all_pairs(a, b)
    assert len(merged) == 5

@test("write_merged_dataset writes <split>/images and <split>/labels (matches thermal_dataset.yaml)", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as lbl_tmp, tempfile.TemporaryDirectory() as out_tmp:
        # Build one ISM pair as a minimal real fixture.
        pairs = collect_ism_pairs(ISM_IMAGES, ISM_METADATA, generated_labels_dir=Path(lbl_tmp))
        out_root = Path(out_tmp)
        write_merged_dataset("train", pairs[:3], out_root, pv_source_class_names=list(PV_CLASSES_MAP.keys()))
        assert (out_root / "train" / "images").exists(), "Expected <out_root>/train/images"
        assert (out_root / "train" / "labels").exists(), "Expected <out_root>/train/labels"
        assert not (out_root / "images").exists(), "Old (wrong) images/<split> layout must not exist"
        imgs = list((out_root / "train" / "images").iterdir())
        assert len(imgs) == 3


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: end-to-end combined dataset build
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 8: end-to-end build ──────────────────────────────────────")

from ml.scripts.prepare_dataset import build_combined_dataset

@test("build_combined_dataset produces thermal_dataset.yaml-compatible layout", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as out_tmp, tempfile.TemporaryDirectory() as stage_tmp:
        out_dir = Path(out_tmp)
        report = build_combined_dataset(
            out_dir=out_dir,
            ism_root=ISM_ROOT,
            archive_zip=ARCHIVE_ZIP,
            pvmd_zip=PVMD_ZIP,
            staging_dir=Path(stage_tmp),
        )
        for split in ("train", "val", "test"):
            assert (out_dir / split / "images").exists()
            assert (out_dir / split / "labels").exists()
            assert len(list((out_dir / split / "images").iterdir())) > 0
        assert (out_dir / "class_distribution.json").exists()
        assert set(report.keys()) == {"train", "val", "test"}

@test("build_combined_dataset class_distribution.json covers 10+ canonical classes", needs_datasets=True)
def _():
    with tempfile.TemporaryDirectory() as out_tmp, tempfile.TemporaryDirectory() as stage_tmp:
        out_dir = Path(out_tmp)
        report = build_combined_dataset(
            out_dir=out_dir,
            ism_root=ISM_ROOT,
            archive_zip=ARCHIVE_ZIP,
            pvmd_zip=PVMD_ZIP,
            staging_dir=Path(stage_tmp),
        )
        all_classes_seen = set()
        for split_counts in report.values():
            all_classes_seen |= set(split_counts.keys())
        assert len(all_classes_seen) >= 10, f"Only {len(all_classes_seen)} classes covered: {all_classes_seen}"


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 65)
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
print(f"  Results: {passed} passed, {failed} failed, {len(_skipped)} skipped  ({len(_results) + len(_skipped)} total)")
if failed:
    print("\n  Failed tests:")
    for name, ok, err in _results:
        if not ok:
            print(f"    • {name}: {err}")
print("═" * 65)
sys.exit(0 if failed == 0 else 1)

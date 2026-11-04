# Thermal Model Retraining & Architecture Bake-Off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real, honestly-labeled combined training dataset from the three raw sources in `ml/Datasets/`, then train and compare YOLO11x, RT-DETR-x, and Co-DETR on it to pick the best model for `ml/checkpoints/best.pt`.

**Architecture:** Extend the existing (already tested) `ml/src/dataset.py` merge pipeline with a third data source (PVMD) and a directory-layout fix, wire it into an end-to-end script producing `ml/data/combined/`, then run three independent training pipelines (two via Ultralytics, one via MMDetection) on GCP Compute Engine, and select a winner via a CRITICAL-class-weighted comparison script.

**Tech Stack:** Python 3.12, Ultralytics 8.4 (YOLO11x, RT-DETR-x), MMDetection (Co-DETR), scikit-learn (stratified split, already a dependency), GCP Compute Engine (spot GPU VM).

## Global Constraints

- Canonical class list, IDs, and severity map live ONLY in `ml/src/utils.py` — never redefine `CANONICAL_CLASSES`, `CLASS2ID`, or `SEVERITY_MAP` elsewhere.
- `ml/thermal_dataset.yaml` defines the on-disk dataset contract: `ml/data/combined/{train,val,test}/{images,labels}` — the pipeline output must match this exactly (split-then-modality nesting).
- Tests for `ml/` code follow the existing repo convention: a plain script with a `@test(name)` decorator and `sys.exit(0 if failed==0 else 1)` at the bottom (see `tests/test_ml_dataset.py`), run directly via `PYTHONSAFEPATH=1 python3 tests/test_ml_dataset.py` — NOT pytest (the file isn't pytest-collectible; it calls `sys.exit()` at import time). Extend that file; do not create a parallel pytest suite for ML code.
- `PYTHONSAFEPATH=1` (or the existing `--import-mode=importlib` pytest config) is required for any Python invocation from the repo root, because `platform/` (this repo's directory) shadows the stdlib `platform` module otherwise.
- Heavy ML dependencies (`ultralytics`, `torch`, `mmdet`) must be imported lazily inside functions, never at module top-level, so scripts remain importable/testable without GPU/heavy deps installed (see `ml/eval/evaluate.py` for the existing pattern).
- No CRITICAL-class (`string`, `bypass-diode`, `hot-spot-high` per `SEVERITY_MAP`) regression beyond 0.05 absolute AP50 drop is acceptable when promoting a new model (reuse `ml/eval/compare.py`'s `REGRESSION_THRESHOLD`).

---

## Context: what already exists (read this before starting)

`ml/src/dataset.py` is a **working, tested** dataset-merge module (35/35 tests passing in `tests/test_ml_dataset.py`) that already handles two of the three sources:

- `ISM_CLASSES_MAP` + `collect_ism_pairs()` — InfraredSolarModules (20k classification crops) → weak whole-image YOLO boxes, remapped to canonical classes. Note: `"No-Anomaly"` is mapped to `"module"` (kept as a positive nominal-module detection target, not discarded) and `"Cracking"` is mapped to `"hot-spot-low"` (physical cracking manifests thermally as a localized low-severity hot spot) — these are deliberate existing choices; do not change them without discussing with the user first.
- `PV_CLASSES_MAP` + `collect_pv_pairs()` — the Roboflow `archive.zip` / `ImageSet` dataset (8 classes, real bboxes) → remapped to canonical classes. Note this mapping already routes `"StringReversedPolarity"` → `"short-circuit"` (30 examples) and `"StringOpenCircuit"` → `"string"` (717 examples) — **`short-circuit` is NOT a zero-coverage class**, contrary to what the design spec's dataset table says. The spec's coverage table is superseded by this existing code; treat `short-circuit` as thin-but-present coverage (~30 images), not absent.
- `stratified_split()` and `collect_all_pairs()` — generic merge/split helpers, source-agnostic.
- `write_merged_dataset()` — **has a directory-layout bug**: it writes to `out_root/images/<split>/` and `out_root/labels/<split>/`, but `ml/thermal_dataset.yaml` expects `out_root/<split>/images/` and `out_root/<split>/labels/`. This must be fixed (Task 2) before the pipeline can produce a dataset `ml/thermal_dataset.yaml` can actually read.

What's still missing, in build order:
1. Extraction helpers for `archive.zip` and the PVMD `.rar` (InfraredSolarModules is already pre-extracted on disk).
2. PVMD support in `ml/src/dataset.py` (third class-mapping + collector) and the directory-layout fix.
3. An end-to-end runner script producing `ml/data/combined/` + a class-distribution report.
4. Ultralytics configs/trainer for YOLO11x and RT-DETR-x.
5. MMDetection YOLO→COCO conversion + Co-DETR config.
6. GCP Compute Engine provisioning scripts.
7. A bake-off winner-selection script.

---

### Task 1: Dataset extraction helpers

**Files:**
- Create: `ml/src/extract.py`
- Test: extend `tests/test_ml_dataset.py` (new "Section 6: extraction" block, appended before the SUMMARY section)

**Interfaces:**
- Produces: `extract_archive_zip(zip_path: Path, dest_dir: Path) -> Path` — returns the extracted `ImageSet` root (containing `train/`, `valid/`, `test/` subdirs).
- Produces: `extract_pvmd(outer_zip_path: Path, dest_dir: Path) -> Path` — returns the extracted PVMD root (containing `Cracks/`, `Hotspots/`, `Shadings/` subdirs).
- Both are idempotent: if `dest_dir` already contains the expected top-level entries, skip re-extraction and return immediately.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ml_dataset.py`, just before the `# SUMMARY` section:

```python
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

@test("extract_archive_zip produces ImageSet with train/valid/test")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = extract_archive_zip(ARCHIVE_ZIP, Path(tmpdir))
        assert (out / "train" / "images").exists()
        assert (out / "valid" / "images").exists()
        assert (out / "test" / "images").exists()
        train_imgs = list((out / "train" / "images").glob("*.jpg"))
        assert len(train_imgs) == 6924, f"Expected 6924 train images, got {len(train_imgs)}"

@test("extract_archive_zip is idempotent (second call is a no-op, same result)")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out1 = extract_archive_zip(ARCHIVE_ZIP, Path(tmpdir))
        out2 = extract_archive_zip(ARCHIVE_ZIP, Path(tmpdir))
        assert out1 == out2
        train_imgs = list((out2 / "train" / "images").glob("*.jpg"))
        assert len(train_imgs) == 6924

@test("extract_pvmd produces Cracks/Hotspots/Shadings folders")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = extract_pvmd(PVMD_ZIP, Path(tmpdir))
        assert (out / "Cracks").exists()
        assert (out / "Hotspots").exists()
        assert (out / "Shadings").exists()
        cracks = list((out / "Cracks").glob("*.jpeg"))
        assert len(cracks) == 351, f"Expected 351 Cracks images, got {len(cracks)}"

@test("extract_pvmd is idempotent")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        out1 = extract_pvmd(PVMD_ZIP, Path(tmpdir))
        out2 = extract_pvmd(PVMD_ZIP, Path(tmpdir))
        assert out1 == out2
        assert len(list((out2 / "Cracks").glob("*.jpeg"))) == 351
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONSAFEPATH=1 python3 tests/test_ml_dataset.py 2>&1 | tail -20`
Expected: `ModuleNotFoundError: No module named 'ml.src.extract'` (or FAIL entries for the new Section 6 tests), while all pre-existing Section 1-5 tests still show PASS.

- [ ] **Step 3: Write minimal implementation**

Create `ml/src/extract.py`:

```python
"""
extract.py — idempotent extraction helpers for the raw dataset archives in
ml/Datasets/.

InfraredSolarModules is already pre-extracted on disk (see
ml/Datasets/InfraredSolarModules/2020-02-14_InfraredSolarModules/) so it needs
no helper here. archive.zip and the PVMD dataset (a .zip containing a .rar)
still need extraction before ml.src.dataset can scan them.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

from ml.src.utils import get_logger

logger = get_logger(__name__)


def extract_archive_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract the Roboflow archive.zip (ImageSet/train|valid|test/images|labels).

    Returns the `ImageSet` root directory. Idempotent: skips extraction if
    dest_dir/ImageSet/train/images already exists and is non-empty.
    """
    out_root = dest_dir / "ImageSet"
    marker = out_root / "train" / "images"
    if marker.exists() and any(marker.iterdir()):
        logger.info("archive.zip already extracted at %s — skipping", out_root)
        return out_root

    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    logger.info("Extracted archive.zip to %s", out_root)
    return out_root


def extract_pvmd(outer_zip_path: Path, dest_dir: Path) -> Path:
    """Extract the PVMD dataset: outer .zip -> inner .rar -> Cracks/Hotspots/Shadings.

    Returns the PVMD root directory (containing the three class folders).
    Idempotent: skips extraction if dest_dir/Cracks already exists and is
    non-empty. Requires the `unrar` CLI to be installed.
    """
    marker = dest_dir / "Cracks"
    if marker.exists() and any(marker.iterdir()):
        logger.info("PVMD already extracted at %s — skipping", dest_dir)
        return dest_dir

    dest_dir.mkdir(parents=True, exist_ok=True)
    staging = dest_dir / "_staging"
    staging.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(outer_zip_path) as zf:
        rar_names = [n for n in zf.namelist() if n.lower().endswith(".rar")]
        if not rar_names:
            raise FileNotFoundError(f"No .rar file found inside {outer_zip_path}")
        zf.extract(rar_names[0], staging)
        rar_path = staging / rar_names[0]

    subprocess.run(
        ["unrar", "x", "-o+", str(rar_path), str(staging)],
        check=True,
        capture_output=True,
    )

    # unrar preserves the "PVMD dataset/<Class>/*" layout inside staging.
    extracted_root = next(staging.rglob("Cracks")).parent
    for class_dir in extracted_root.iterdir():
        if class_dir.is_dir():
            target = dest_dir / class_dir.name
            if not target.exists():
                class_dir.rename(target)

    logger.info("Extracted PVMD to %s", dest_dir)
    return dest_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONSAFEPATH=1 python3 tests/test_ml_dataset.py 2>&1 | tail -20`
Expected: all Section 6 tests PASS, total count increases from 35 to 39, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add ml/src/extract.py tests/test_ml_dataset.py
git commit -m "feat(ml): add idempotent extraction helpers for archive.zip and PVMD dataset"
```

---

### Task 2: PVMD dataset support + directory-layout fix in `ml/src/dataset.py`

**Files:**
- Modify: `ml/src/dataset.py`
- Test: extend `tests/test_ml_dataset.py` ("Section 7: PVMD + merge fixes")

**Interfaces:**
- Consumes: `extract_pvmd()` from Task 1 (test fixture only; the function itself takes a plain directory path, no coupling to Task 1's extraction).
- Produces: `PVMD_CLASSES_MAP: dict[str, str]`, `collect_pvmd_pairs(pvmd_root: Path, classes_map: dict[str,str] = PVMD_CLASSES_MAP, generated_labels_dir: Path | None = None) -> list[tuple[Path, Path, int]]` (same 3-tuple shape as `collect_ism_pairs`/`collect_pv_pairs`).
- Modifies: `collect_all_pairs(ism_pairs, pv_pairs, pvmd_pairs=None)` — third argument optional and defaulting to `None` so existing 2-arg call sites (including the existing test) keep working.
- Modifies: `write_merged_dataset()` — output layout becomes `out_root/<split_name>/images/` and `out_root/<split_name>/labels/` (was `out_root/images/<split_name>/` and `out_root/labels/<split_name>/`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ml_dataset.py` after the Section 6 block added in Task 1:

```python
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

@test("collect_pvmd_pairs scans all 1003 PVMD images")
def _():
    with tempfile.TemporaryDirectory() as extract_tmp, tempfile.TemporaryDirectory() as lbl_tmp:
        pvmd_root = extract_pvmd(PVMD_ZIP, Path(extract_tmp))
        pairs = collect_pvmd_pairs(pvmd_root, generated_labels_dir=Path(lbl_tmp))
        assert len(pairs) == 1003, f"Expected 1003, got {len(pairs)}"

@test("collect_pvmd_pairs writes valid whole-image YOLO labels")
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

@test("write_merged_dataset writes <split>/images and <split>/labels (matches thermal_dataset.yaml)")
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONSAFEPATH=1 python3 tests/test_ml_dataset.py 2>&1 | tail -30`
Expected: `ImportError: cannot import name 'PVMD_CLASSES_MAP'` and/or the layout test FAILs against the current `images/<split>` structure.

- [ ] **Step 3: Write minimal implementation**

In `ml/src/dataset.py`, add after `PV_CLASSES_MAP`:

```python
# ── PVMD class name → canonical class name ──────────────────────────────────
# PVMD dataset is folder-per-class classification data (Cracks/Hotspots/Shadings),
# same weak-label treatment as ISM. Mapped for consistency with ISM's existing
# conventions: cracking -> hot-spot-low (matches ISM's "Cracking" mapping),
# generic "Hotspots" (no single/multi distinction given) -> hot-spot-low as the
# conservative default, shading -> vegetation-shading.
PVMD_CLASSES_MAP: dict[str, str] = {
    "Cracks":   "hot-spot-low",
    "Hotspots": "hot-spot-low",
    "Shadings": "vegetation-shading",
}
```

Add after `collect_ism_pairs`:

```python
# ── PVMD dataset scanning ─────────────────────────────────────────────────────

def collect_pvmd_pairs(
    pvmd_root: Path,
    classes_map: dict[str, str] = PVMD_CLASSES_MAP,
    generated_labels_dir: Path | None = None,
) -> list[tuple[Path, Path, int]]:
    """Scan PVMD folder-per-class dataset, return (img_path, lbl_path, majority_class_id).

    Same whole-image weak-label strategy as collect_ism_pairs: each crop gets
    a single synthesised YOLO box (cx=0.5, cy=0.5, w=1.0, h=1.0).
    """
    if generated_labels_dir is None:
        generated_labels_dir = pvmd_root.parent / "pvmd_labels"
    generated_labels_dir.mkdir(parents=True, exist_ok=True)

    pairs: list[tuple[Path, Path, int]] = []
    skipped = 0

    for class_name, canonical_name in classes_map.items():
        class_dir = pvmd_root / class_name
        if not class_dir.exists():
            logger.warning("PVMD: class dir %s not found — skipping", class_dir)
            continue

        canonical_id = CLASS2ID.get(canonical_name)
        if canonical_id is None:
            logger.warning("PVMD: canonical name %r not in CLASS2ID — skipping", canonical_name)
            continue

        for img_path in sorted(class_dir.iterdir()):
            if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                skipped += 1
                continue
            lbl_path = generated_labels_dir / (img_path.stem + ".txt")
            write_yolo_label(lbl_path, [(canonical_id, 0.5, 0.5, 1.0, 1.0)])
            pairs.append((img_path, lbl_path, canonical_id))

    if skipped:
        logger.info("PVMD: skipped %d non-image entries", skipped)
    logger.info("PVMD: collected %d pairs", len(pairs))
    return pairs
```

Replace `collect_all_pairs`:

```python
def collect_all_pairs(
    ism_pairs: list[tuple[Path, Path, int]],
    pv_pairs: list[tuple[Path, Path, int]],
    pvmd_pairs: list[tuple[Path, Path, int]] | None = None,
) -> list[tuple[Path, Path, int]]:
    """Merge ISM, PV, and (optionally) PVMD pairs into a single flat list."""
    pvmd_pairs = pvmd_pairs or []
    merged = ism_pairs + pv_pairs + pvmd_pairs
    logger.info(
        "Total pairs: %d (ISM=%d, PV=%d, PVMD=%d)",
        len(merged), len(ism_pairs), len(pv_pairs), len(pvmd_pairs),
    )
    return merged
```

In `write_merged_dataset`, change the output paths:

```python
    imgs_out  = out_root / split_name / "images"
    lbls_out  = out_root / split_name / "labels"
```

(replacing the existing `out_root / "images" / split_name` / `out_root / "labels" / split_name` lines — everything else in the function body is unchanged).

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONSAFEPATH=1 python3 tests/test_ml_dataset.py 2>&1 | tail -30`
Expected: all Section 7 tests PASS, total count increases to 44, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add ml/src/dataset.py tests/test_ml_dataset.py
git commit -m "feat(ml): add PVMD dataset support and fix write_merged_dataset directory layout"
```

---

### Task 3: End-to-end combined-dataset builder + class-distribution report

**Files:**
- Modify: `ml/scripts/prepare_dataset.py` (full rewrite — the existing content references a nonexistent PV-Hawk dataset and a Roboflow path/class-name scheme that doesn't match any real source; replace it entirely)
- Test: extend `tests/test_ml_dataset.py` ("Section 8: end-to-end build")

**Interfaces:**
- Consumes: `extract_archive_zip`, `extract_pvmd` (Task 1); `collect_ism_pairs`, `collect_pv_pairs`, `collect_pvmd_pairs`, `collect_all_pairs`, `stratified_split`, `write_merged_dataset` (Task 2).
- Produces: `build_combined_dataset(out_dir: Path, ism_root: Path, archive_zip: Path, pvmd_zip: Path, staging_dir: Path, seed: int = 42) -> dict` — returns a class-distribution report dict `{"train": {...counts...}, "val": {...}, "test": {...}}` and also writes it to `out_dir / "class_distribution.json"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ml_dataset.py`:

```python
# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: end-to-end combined dataset build
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Section 8: end-to-end build ──────────────────────────────────────")

from ml.scripts.prepare_dataset import build_combined_dataset

@test("build_combined_dataset produces thermal_dataset.yaml-compatible layout")
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

@test("build_combined_dataset class_distribution.json covers 10+ canonical classes")
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONSAFEPATH=1 python3 tests/test_ml_dataset.py 2>&1 | tail -20`
Expected: `ImportError: cannot import name 'build_combined_dataset'` (the current `prepare_dataset.py` has a `main()`/CLI, not this function).

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `ml/scripts/prepare_dataset.py`:

```python
"""
prepare_dataset.py — build ml/data/combined/ from the three raw datasets in
ml/Datasets/, matching the layout ml/thermal_dataset.yaml expects
(<split>/images/, <split>/labels/).

Usage:
    python3 -m ml.scripts.prepare_dataset \
        --out ml/data/combined \
        --staging ml/data/_staging

Sources merged (see ml/src/dataset.py for class-mapping tables):
    - InfraredSolarModules (already extracted on disk, classification -> weak bbox)
    - archive.zip / ImageSet (Roboflow, real bboxes)
    - PVMD dataset (.zip containing a .rar, classification -> weak bbox)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ml.src.dataset import (
    PV_CLASSES_MAP,
    collect_all_pairs,
    collect_ism_pairs,
    collect_pv_pairs,
    collect_pvmd_pairs,
    stratified_split,
    write_merged_dataset,
)
from ml.src.extract import extract_archive_zip, extract_pvmd
from ml.src.utils import CANONICAL_CLASSES, ID2CLASS, get_logger, read_yolo_label

logger = get_logger(__name__)


def _class_distribution(out_dir: Path) -> dict[str, dict[str, int]]:
    """Count canonical class occurrences per split by reading written labels."""
    report: dict[str, dict[str, int]] = {}
    for split in ("train", "val", "test"):
        counts: Counter[str] = Counter()
        labels_dir = out_dir / split / "labels"
        if not labels_dir.exists():
            report[split] = {}
            continue
        for lbl_path in labels_dir.glob("*.txt"):
            for cid, *_ in read_yolo_label(lbl_path):
                counts[ID2CLASS.get(cid, f"unknown-{cid}")] += 1
        report[split] = dict(counts)
    return report


def build_combined_dataset(
    out_dir: Path,
    ism_root: Path,
    archive_zip: Path,
    pvmd_zip: Path,
    staging_dir: Path,
    seed: int = 42,
) -> dict[str, dict[str, int]]:
    """Merge all three sources into out_dir, return + persist a class-distribution report."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    ism_images = ism_root / "images"
    ism_metadata = ism_root / "module_metadata.json"
    ism_pairs = collect_ism_pairs(ism_images, ism_metadata)

    archive_root = extract_archive_zip(archive_zip, staging_dir / "archive")
    pv_source_names = list(PV_CLASSES_MAP.keys())
    pv_pairs = collect_pv_pairs(archive_root, pv_source_names)

    pvmd_root = extract_pvmd(pvmd_zip, staging_dir / "pvmd")
    pvmd_pairs = collect_pvmd_pairs(pvmd_root)

    all_pairs = collect_all_pairs(ism_pairs, pv_pairs, pvmd_pairs)
    train, val, test = stratified_split(all_pairs, seed=seed)

    for split_name, pairs in (("train", train), ("val", val), ("test", test)):
        write_merged_dataset(split_name, pairs, out_dir, pv_source_class_names=pv_source_names)

    report = _class_distribution(out_dir)
    (out_dir / "class_distribution.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="ml/data/combined")
    parser.add_argument("--staging", default="ml/data/_staging")
    parser.add_argument(
        "--ism-root",
        default="ml/Datasets/InfraredSolarModules/2020-02-14_InfraredSolarModules/InfraredSolarModules",
    )
    parser.add_argument("--archive-zip", default="ml/Datasets/archive.zip")
    parser.add_argument(
        "--pvmd-zip",
        default=(
            "ml/Datasets/Photovoltaic module dataset for automated fault detection "
            "and analysis in large photovoltaic systems using photovoltaic module "
            "fault detection.zip"
        ),
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = build_combined_dataset(
        out_dir=Path(args.out),
        ism_root=Path(args.ism_root),
        archive_zip=Path(args.archive_zip),
        pvmd_zip=Path(args.pvmd_zip),
        staging_dir=Path(args.staging),
        seed=args.seed,
    )

    print("\nClass distribution per split:")
    for split, counts in report.items():
        print(f"  {split}:")
        for cls in CANONICAL_CLASSES:
            print(f"    {cls:<20} {counts.get(cls, 0)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONSAFEPATH=1 python3 tests/test_ml_dataset.py 2>&1 | tail -20`
Expected: all Section 8 tests PASS, total count increases to 46, 0 failed. (This runs the real, full merge across all three sources — expect this step to take a few minutes given ISM's 20k images.)

- [ ] **Step 5: Commit**

```bash
git add ml/scripts/prepare_dataset.py tests/test_ml_dataset.py
git commit -m "feat(ml): rewrite prepare_dataset.py as end-to-end 3-source dataset builder"
```

- [ ] **Step 6: Actually build the real combined dataset**

Run: `PYTHONSAFEPATH=1 python3 -m ml.scripts.prepare_dataset`
Expected: `ml/data/combined/{train,val,test}/{images,labels}` populated, plus `ml/data/combined/class_distribution.json` printed and written. Inspect the printed per-class counts and confirm `short-circuit` shows a small nonzero count (~20-30, from the `StringReversedPolarity` mapping) rather than zero.

---

### Task 4: Ultralytics bake-off candidates (YOLO11x, RT-DETR-x)

**Files:**
- Create: `ml/configs/thermal_yolo11x.yaml`
- Create: `ml/configs/thermal_rtdetr_x.yaml`
- Create: `ml/scripts/train_ultralytics.py`
- Test: `tests/test_train_ultralytics.py` (new file — this one mocks a heavy dependency and is import-light, so it's fine as a small standalone script following the same `@test` convention)

**Interfaces:**
- Consumes: `ml/thermal_dataset.yaml` (dataset), the two new config YAMLs.
- Produces: `load_training_config(path: Path) -> dict`, `build_model(architecture: str)` (lazy-imports `ultralytics.YOLO` or `ultralytics.RTDETR` based on `architecture in {"yolo11x", "rtdetr-x"}`), `run_training(config_path: Path) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_train_ultralytics.py`:

```python
"""
train_ultralytics.py tests — run with:
    PYTHONSAFEPATH=1 python3 tests/test_train_ultralytics.py
"""
from __future__ import annotations
import sys
import os
from unittest.mock import patch, MagicMock

import platform
import uuid

_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path = [_ROOT] + [p for p in sys.path if os.path.abspath(p) != _ROOT]

from pathlib import Path
import yaml

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  [{PASS}] {name}")
        except Exception as exc:
            _results.append((name, False, str(exc)))
            print(f"  [{FAIL}] {name}: {exc}")
        return fn
    return decorator


from ml.scripts.train_ultralytics import load_training_config, build_model, run_training

ROOT = Path(_ROOT)


@test("load_training_config reads yolo11x config")
def _():
    cfg = load_training_config(ROOT / "ml/configs/thermal_yolo11x.yaml")
    assert cfg["model"] == "yolo11x.pt"
    assert cfg["dataset_yaml"] == "ml/thermal_dataset.yaml"


@test("load_training_config reads rtdetr config")
def _():
    cfg = load_training_config(ROOT / "ml/configs/thermal_rtdetr_x.yaml")
    assert cfg["model"] == "rtdetr-x.pt"


@test("build_model('yolo11x.pt') lazily imports ultralytics.YOLO")
def _():
    with patch("ultralytics.YOLO") as mock_yolo:
        mock_yolo.return_value = MagicMock()
        build_model("yolo11x.pt")
        mock_yolo.assert_called_once_with("yolo11x.pt")


@test("build_model('rtdetr-x.pt') lazily imports ultralytics.RTDETR")
def _():
    with patch("ultralytics.RTDETR") as mock_rtdetr:
        mock_rtdetr.return_value = MagicMock()
        build_model("rtdetr-x.pt")
        mock_rtdetr.assert_called_once_with("rtdetr-x.pt")


@test("run_training calls model.train() with config's hyperparameters")
def _():
    cfg_path = ROOT / "ml/configs/thermal_yolo11x.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    with patch("ml.scripts.train_ultralytics.build_model") as mock_build:
        mock_model = MagicMock()
        mock_build.return_value = mock_model
        run_training(cfg_path)
        mock_model.train.assert_called_once()
        kwargs = mock_model.train.call_args.kwargs
        assert kwargs["data"] == cfg["dataset_yaml"]
        assert kwargs["epochs"] == cfg["epochs"]
        assert kwargs["imgsz"] == cfg["imgsz"]


print("\n" + "═" * 65)
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
print(f"  Results: {passed} passed, {failed} failed  ({len(_results)} total)")
if failed:
    for name, ok, err in _results:
        if not ok:
            print(f"    - {name}: {err}")
sys.exit(0 if failed == 0 else 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONSAFEPATH=1 python3 tests/test_train_ultralytics.py 2>&1 | tail -20`
Expected: `ModuleNotFoundError: No module named 'ml.scripts.train_ultralytics'` and missing config file errors.

- [ ] **Step 3: Write minimal implementation**

Create `ml/configs/thermal_yolo11x.yaml` (copy of `ml/configs/thermal.yaml` with the model swapped):

```yaml
# ── YOLO11x Thermal Solar Training Config (bake-off candidate 1) ────────────
dataset_yaml: ml/thermal_dataset.yaml
imgsz: 640

model: yolo11x.pt

epochs: 150
batch: 16
device: 0
lr0: 0.001
lrf: 0.0001
cos_lr: true
warmup_epochs: 5
warmup_momentum: 0.8
patience: 20
optimizer: AdamW
weight_decay: 0.0005

hsv_h: 0.0
hsv_s: 0.0
hsv_v: 0.4
degrees: 5.0
scale: 0.3
fliplr: 0.5
flipud: 0.0
mosaic: 1.0
mixup: 0.15
copy_paste: 0.1
close_mosaic: 15

project: ml/runs/thermal
name: yolo11x_solar
save_period: 10
plots: true
```

Create `ml/configs/thermal_rtdetr_x.yaml` (same hyperparameters, RT-DETR doesn't use YOLO-style mosaic/copy-paste augmentation the same way, so those are dropped):

```yaml
# ── RT-DETR-x Thermal Solar Training Config (bake-off candidate 2) ──────────
dataset_yaml: ml/thermal_dataset.yaml
imgsz: 640

model: rtdetr-x.pt

epochs: 150
batch: 16
device: 0
lr0: 0.0001
lrf: 0.0001
cos_lr: true
warmup_epochs: 5
warmup_momentum: 0.8
patience: 20
optimizer: AdamW
weight_decay: 0.0001

hsv_h: 0.0
hsv_s: 0.0
hsv_v: 0.4
degrees: 5.0
scale: 0.3
fliplr: 0.5
flipud: 0.0

project: ml/runs/thermal
name: rtdetr_x_solar
save_period: 10
plots: true
```

Create `ml/scripts/train_ultralytics.py`:

```python
"""
train_ultralytics.py — shared Ultralytics trainer for the YOLO11x and RT-DETR-x
bake-off candidates.

Usage:
    python3 -m ml.scripts.train_ultralytics --config ml/configs/thermal_yolo11x.yaml
    python3 -m ml.scripts.train_ultralytics --config ml/configs/thermal_rtdetr_x.yaml
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from ml.src.utils import get_logger

logger = get_logger(__name__)

_NON_TRAIN_KEYS = {"dataset_yaml", "model"}


def load_training_config(path: Path) -> dict:
    """Load a thermal_*.yaml training config."""
    return yaml.safe_load(Path(path).read_text())


def build_model(model_name: str):
    """Lazily construct the right Ultralytics model class for `model_name`."""
    if model_name.startswith("rtdetr"):
        from ultralytics import RTDETR
        return RTDETR(model_name)
    from ultralytics import YOLO
    return YOLO(model_name)


def run_training(config_path: Path) -> None:
    """Train the model described by `config_path` and log the result location."""
    cfg = load_training_config(config_path)
    model = build_model(cfg["model"])

    train_kwargs = {k: v for k, v in cfg.items() if k not in _NON_TRAIN_KEYS}
    train_kwargs["data"] = cfg["dataset_yaml"]

    logger.info("Starting training with config %s", config_path)
    model.train(**train_kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    run_training(Path(args.config))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONSAFEPATH=1 python3 tests/test_train_ultralytics.py 2>&1 | tail -20`
Expected: 5 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add ml/configs/thermal_yolo11x.yaml ml/configs/thermal_rtdetr_x.yaml ml/scripts/train_ultralytics.py tests/test_train_ultralytics.py
git commit -m "feat(ml): add YOLO11x and RT-DETR-x bake-off training configs and shared trainer"
```

---

### Task 5: Co-DETR candidate — YOLO-to-COCO conversion + MMDetection config

**Files:**
- Create: `ml/scripts/yolo_to_coco.py`
- Create: `ml/configs/co_detr_thermal.py`
- Test: `tests/test_yolo_to_coco.py`

**Interfaces:**
- Consumes: `ml/data/combined/{split}/{images,labels}` (Task 3 output), `CANONICAL_CLASSES` from `ml.src.utils`.
- Produces: `yolo_split_to_coco(images_dir: Path, labels_dir: Path, class_names: list[str]) -> dict` (an in-memory COCO-format dict), `convert_all_splits(combined_root: Path, out_root: Path) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_yolo_to_coco.py`:

```python
"""
yolo_to_coco.py tests — run with:
    PYTHONSAFEPATH=1 python3 tests/test_yolo_to_coco.py
"""
from __future__ import annotations
import sys
import os
import tempfile

import platform
import uuid

_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path = [_ROOT] + [p for p in sys.path if os.path.abspath(p) != _ROOT]

from pathlib import Path
import numpy as np
import cv2

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  [{PASS}] {name}")
        except Exception as exc:
            _results.append((name, False, str(exc)))
            print(f"  [{FAIL}] {name}: {exc}")
        return fn
    return decorator


from ml.scripts.yolo_to_coco import yolo_split_to_coco
from ml.src.utils import CANONICAL_CLASSES


def _make_fixture_split(tmpdir: Path) -> tuple[Path, Path]:
    images_dir = tmpdir / "images"
    labels_dir = tmpdir / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()

    img = np.zeros((100, 200, 3), dtype=np.uint8)
    cv2.imwrite(str(images_dir / "a.jpg"), img)
    (labels_dir / "a.txt").write_text("3 0.5 0.5 0.4 0.2\n4 0.25 0.25 0.1 0.1\n")

    cv2.imwrite(str(images_dir / "b.jpg"), img)
    (labels_dir / "b.txt").write_text("")  # image with no boxes

    return images_dir, labels_dir


@test("yolo_split_to_coco produces correct top-level COCO keys")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        assert set(coco.keys()) == {"images", "annotations", "categories"}


@test("yolo_split_to_coco produces one image entry per source image")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        assert len(coco["images"]) == 2


@test("yolo_split_to_coco converts normalized YOLO box to pixel xywh")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        anns = [a for a in coco["annotations"] if a["category_id"] == 3]
        assert len(anns) == 1
        x, y, w, h = anns[0]["bbox"]
        # image is 200x100; box cx=0.5,cy=0.5,w=0.4,h=0.2 -> x1=60,y1=40,w=80,h=20
        assert abs(x - 60) < 1e-3 and abs(y - 40) < 1e-3
        assert abs(w - 80) < 1e-3 and abs(h - 20) < 1e-3


@test("yolo_split_to_coco categories match CANONICAL_CLASSES order (0-indexed)")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        ids_to_names = {c["id"]: c["name"] for c in coco["categories"]}
        for i, name in enumerate(CANONICAL_CLASSES):
            assert ids_to_names[i] == name


@test("yolo_split_to_coco handles an image with zero boxes")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        b_image_id = next(i["id"] for i in coco["images"] if i["file_name"] == "b.jpg")
        anns_for_b = [a for a in coco["annotations"] if a["image_id"] == b_image_id]
        assert anns_for_b == []


print("\n" + "═" * 65)
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
print(f"  Results: {passed} passed, {failed} failed  ({len(_results)} total)")
if failed:
    for name, ok, err in _results:
        if not ok:
            print(f"    - {name}: {err}")
sys.exit(0 if failed == 0 else 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONSAFEPATH=1 python3 tests/test_yolo_to_coco.py 2>&1 | tail -20`
Expected: `ModuleNotFoundError: No module named 'ml.scripts.yolo_to_coco'`.

- [ ] **Step 3: Write minimal implementation**

Create `ml/scripts/yolo_to_coco.py`:

```python
"""
yolo_to_coco.py — convert ml/data/combined (YOLO format) to COCO JSON for
Co-DETR/MMDetection training.

Usage:
    python3 -m ml.scripts.yolo_to_coco --combined-root ml/data/combined --out ml/data/combined_coco
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from ml.src.utils import CANONICAL_CLASSES, get_logger, read_yolo_label, yolo_to_pixel

logger = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def yolo_split_to_coco(images_dir: Path, labels_dir: Path, class_names: list[str]) -> dict:
    """Convert one YOLO-format split (images_dir/labels_dir) to a COCO dict."""
    categories = [{"id": i, "name": name} for i, name in enumerate(class_names)]
    images: list[dict] = []
    annotations: list[dict] = []
    ann_id = 1

    for image_id, img_path in enumerate(sorted(images_dir.iterdir()), start=1):
        if img_path.suffix.lower() not in _IMAGE_EXTS:
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning("Could not read image %s — skipping", img_path)
            continue
        h, w = img.shape[:2]
        images.append({"id": image_id, "file_name": img_path.name, "width": w, "height": h})

        lbl_path = labels_dir / (img_path.stem + ".txt")
        for cid, cx, cy, bw, bh in read_yolo_label(lbl_path):
            x1, y1, x2, y2 = yolo_to_pixel(cx, cy, bw, bh, w, h)
            annotations.append({
                "id": ann_id,
                "image_id": image_id,
                "category_id": cid,
                "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                "area": float((x2 - x1) * (y2 - y1)),
                "iscrowd": 0,
            })
            ann_id += 1

    return {"images": images, "annotations": annotations, "categories": categories}


def convert_all_splits(combined_root: Path, out_root: Path) -> None:
    """Convert train/val/test splits under combined_root to COCO JSONs under out_root."""
    out_root.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        images_dir = combined_root / split / "images"
        labels_dir = combined_root / split / "labels"
        if not images_dir.exists():
            logger.warning("Split %s not found under %s — skipping", split, combined_root)
            continue
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        out_path = out_root / f"{split}.json"
        out_path.write_text(json.dumps(coco))
        logger.info("Wrote %s (%d images, %d annotations)", out_path, len(coco["images"]), len(coco["annotations"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-root", default="ml/data/combined")
    parser.add_argument("--out", default="ml/data/combined_coco")
    args = parser.parse_args()
    convert_all_splits(Path(args.combined_root), Path(args.out))


if __name__ == "__main__":
    main()
```

Create `ml/configs/co_detr_thermal.py` (MMDetection config; references the converted COCO data and does not import mmdet at plan-write time, just describes the config the way MMDetection expects to load it):

```python
"""
co_detr_thermal.py — MMDetection config for the Co-DETR bake-off candidate.

Usage (on the GCP training VM, inside an MMDetection checkout):
    python tools/train.py ml/configs/co_detr_thermal.py

Falls back to DINO (base = 'dino/dino-4scale_r50_8xb2-12e_coco.py') if Co-DETR
training proves unstable — see the "Risks" section of the design spec at
docs/superpowers/specs/2026-07-01-thermal-model-retraining-bakeoff-design.md.
"""

_base_ = "co_detr/co_dino_5scale_r50_1x_coco.py"

data_root = "ml/data/combined_coco/"
classes = (
    "cell", "cell-multi", "module", "string", "bypass-diode",
    "offline-module", "vegetation-shading", "soiling", "short-circuit",
    "hot-spot-low", "hot-spot-high",
)
num_classes = len(classes)

model = dict(
    query_head=dict(num_classes=num_classes),
    roi_head=[dict(bbox_head=dict(num_classes=num_classes))],
    bbox_head=[dict(num_classes=num_classes)],
)

train_dataloader = dict(
    dataset=dict(
        data_root=data_root,
        ann_file="train.json",
        data_prefix=dict(img="../combined/train/images/"),
        metainfo=dict(classes=classes),
    )
)
val_dataloader = dict(
    dataset=dict(
        data_root=data_root,
        ann_file="val.json",
        data_prefix=dict(img="../combined/val/images/"),
        metainfo=dict(classes=classes),
    )
)
test_dataloader = val_dataloader

val_evaluator = dict(ann_file=data_root + "val.json")
test_evaluator = val_evaluator

work_dir = "ml/runs/thermal/codetr_solar"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONSAFEPATH=1 python3 tests/test_yolo_to_coco.py 2>&1 | tail -20`
Expected: 5 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add ml/scripts/yolo_to_coco.py ml/configs/co_detr_thermal.py tests/test_yolo_to_coco.py
git commit -m "feat(ml): add YOLO-to-COCO converter and Co-DETR MMDetection config"
```

---

### Task 6: GCP Compute Engine training infrastructure

**Files:**
- Create: `deploy/gcp/provision-training-vm.sh`
- Create: `deploy/gcp/train-vm-startup.sh`
- Create: `deploy/gcp/README.md`

**Interfaces:**
- Consumes: `ml/scripts/train_ultralytics.py` + `ml/configs/thermal_yolo11x.yaml` / `thermal_rtdetr_x.yaml` (Task 4), `ml/scripts/yolo_to_coco.py` + `ml/configs/co_detr_thermal.py` (Task 5), `ml/data/combined` (Task 3).
- Produces: no Python interfaces — this is operator-facing shell tooling, verified by syntax check and manual review, not pytest.

- [ ] **Step 1: Write the provisioning script**

Create `deploy/gcp/provision-training-vm.sh`:

```bash
#!/usr/bin/env bash
# provision-training-vm.sh — create a spot GPU VM for one bake-off training run.
#
# Usage:
#   ./deploy/gcp/provision-training-vm.sh <candidate> <project-id> <zone>
#   ./deploy/gcp/provision-training-vm.sh yolo11x axalon-ml-training us-central1-a
#
# <candidate> is one of: yolo11x, rtdetr-x, codetr
set -euo pipefail

CANDIDATE="${1:?Usage: $0 <candidate> <project-id> <zone>}"
PROJECT_ID="${2:?Usage: $0 <candidate> <project-id> <zone>}"
ZONE="${3:?Usage: $0 <candidate> <project-id> <zone>}"

VM_NAME="thermal-train-${CANDIDATE}"
DISK_NAME="thermal-dataset-disk"

case "$CANDIDATE" in
  yolo11x|rtdetr-x|codetr) ;;
  *) echo "Unknown candidate: $CANDIDATE (expected yolo11x, rtdetr-x, or codetr)" >&2; exit 1 ;;
esac

# Persistent disk holding ml/data/combined (and ml/data/combined_coco for codetr).
# Create once, reused across all three candidate VMs.
if ! gcloud compute disks describe "$DISK_NAME" --zone="$ZONE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute disks create "$DISK_NAME" \
    --project="$PROJECT_ID" --zone="$ZONE" \
    --size=200GB --type=pd-balanced
  echo "Created $DISK_NAME — mount it once on a scratch VM and rsync ml/data/combined onto it before training."
fi

gcloud compute instances create "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --machine-type=g2-standard-8 \
  --accelerator="type=nvidia-l4,count=1" \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --image-family=common-cu124-ubuntu-2204 \
  --image-project=deeplearning-platform-release \
  --boot-disk-size=100GB \
  --disk="name=${DISK_NAME},device-name=${DISK_NAME},mode=rw" \
  --metadata=candidate="${CANDIDATE}" \
  --metadata-from-file=startup-script=deploy/gcp/train-vm-startup.sh

echo "VM ${VM_NAME} created. Tail progress with:"
echo "  gcloud compute instances tail-serial-port-output ${VM_NAME} --zone=${ZONE} --project=${PROJECT_ID}"
```

- [ ] **Step 2: Write the startup script**

Create `deploy/gcp/train-vm-startup.sh`:

```bash
#!/usr/bin/env bash
# train-vm-startup.sh — runs on first boot of a bake-off training VM.
# Clones the repo, mounts the pre-populated dataset disk, runs the training
# entrypoint for the candidate named in the "candidate" instance metadata key,
# then shuts the VM down so spot billing stops.
set -euo pipefail

CANDIDATE="$(curl -s -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/attributes/candidate')"

DATA_DEVICE="/dev/disk/by-id/google-thermal-dataset-disk"
MOUNT_POINT="/mnt/dataset"

mkdir -p "$MOUNT_POINT"
mount -o discard,defaults "$DATA_DEVICE" "$MOUNT_POINT"

cd /opt
git clone --depth 1 https://github.com/<org>/AxalonSystems.git repo
cd repo
ln -s "$MOUNT_POINT"/combined ml/data/combined
[ -d "$MOUNT_POINT/combined_coco" ] && ln -s "$MOUNT_POINT"/combined_coco ml/data/combined_coco

pip install -r ml/requirements.txt

case "$CANDIDATE" in
  yolo11x)
    python3 -m ml.scripts.train_ultralytics --config ml/configs/thermal_yolo11x.yaml
    ;;
  rtdetr-x)
    python3 -m ml.scripts.train_ultralytics --config ml/configs/thermal_rtdetr_x.yaml
    ;;
  codetr)
    git clone --depth 1 https://github.com/Sense-X/Co-DETR.git /opt/co-detr
    pip install -r /opt/co-detr/requirements.txt
    python3 -m ml.scripts.yolo_to_coco --combined-root ml/data/combined --out ml/data/combined_coco
    cd /opt/co-detr
    python tools/train.py /opt/repo/ml/configs/co_detr_thermal.py
    ;;
esac

shutdown -h now
```

- [ ] **Step 3: Write the runbook**

Create `deploy/gcp/README.md`:

```markdown
# GCP training runbook — thermal model bake-off

One-time setup:
1. Build the combined dataset locally: `PYTHONSAFEPATH=1 python3 -m ml.scripts.prepare_dataset`
2. `gcloud auth login` and set the project: `gcloud config set project <project-id>`
3. Provision the shared dataset disk (first run of `provision-training-vm.sh` creates it), then attach it to a small temporary VM and `rsync` `ml/data/combined` (and, for the codetr run, `ml/data/combined_coco` from `python3 -m ml.scripts.yolo_to_coco`) onto it.

Per-candidate run:
```bash
./deploy/gcp/provision-training-vm.sh yolo11x   axalon-ml-training us-central1-a
./deploy/gcp/provision-training-vm.sh rtdetr-x  axalon-ml-training us-central1-a
./deploy/gcp/provision-training-vm.sh codetr    axalon-ml-training us-central1-a
```

Each VM auto-shuts-down when training completes (see `train-vm-startup.sh`'s final `shutdown -h now`) so spot billing stops without manual intervention. Checkpoints land under `ml/runs/thermal/<name>/weights/` (Ultralytics candidates) or `ml/runs/thermal/codetr_solar/` (Co-DETR) — copy these back locally (`gcloud compute scp`) before deleting the VM.

Budget: three candidate runs plus one hyperparameter follow-up on the winner, within the $300 GCP credit, using spot L4 pricing.
```

- [ ] **Step 4: Verify shell syntax**

Run: `bash -n deploy/gcp/provision-training-vm.sh && bash -n deploy/gcp/train-vm-startup.sh && echo "syntax OK"`
Expected: `syntax OK`, no errors.

- [ ] **Step 5: Commit**

```bash
chmod +x deploy/gcp/provision-training-vm.sh deploy/gcp/train-vm-startup.sh
git add deploy/gcp/
git commit -m "feat(deploy): add GCP spot-GPU provisioning scripts for the model bake-off"
```

---

### Task 7: Bake-off winner selection

**Files:**
- Create: `ml/eval/select_winner.py`
- Test: `tests/test_select_winner.py`

**Interfaces:**
- Consumes: metrics JSONs in the shape produced by `ml/eval/evaluate.py`'s `run_eval()` (keys: `model`, `map50`, `map50_95`, `per_class: {name: {precision, recall, ap50}}`); `SEVERITY_MAP` from `ml.src.utils`.
- Produces: `score_candidate(metrics: dict, critical_weight: float = 2.0) -> float`, `select_winner(baseline_path: str, candidate_paths: dict[str, str], critical_weight: float = 2.0) -> dict` (returns `{"ranking": [...], "winner": str, "winner_metrics_path": str}`, and writes the same dict to `ml/eval/results/selection_report.json`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_select_winner.py`:

```python
"""
select_winner.py tests — run with:
    PYTHONSAFEPATH=1 python3 tests/test_select_winner.py
"""
from __future__ import annotations
import sys
import os
import json
import tempfile

import platform
import uuid

_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path = [_ROOT] + [p for p in sys.path if os.path.abspath(p) != _ROOT]

from pathlib import Path

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  [{PASS}] {name}")
        except Exception as exc:
            _results.append((name, False, str(exc)))
            print(f"  [{FAIL}] {name}: {exc}")
        return fn
    return decorator


from ml.eval.select_winner import score_candidate, select_winner

_FAKE_METRICS = {
    "map50": 0.5,
    "per_class": {
        "string":         {"ap50": 0.4},   # CRITICAL
        "bypass-diode":   {"ap50": 0.4},   # CRITICAL
        "hot-spot-high":  {"ap50": 0.4},   # CRITICAL
        "cell":           {"ap50": 0.8},   # MEDIUM
    },
}


@test("score_candidate weights CRITICAL classes higher than default weight 1")
def _():
    unweighted = score_candidate(_FAKE_METRICS, critical_weight=1.0)
    weighted = score_candidate(_FAKE_METRICS, critical_weight=2.0)
    assert weighted > unweighted


@test("score_candidate is deterministic")
def _():
    a = score_candidate(_FAKE_METRICS)
    b = score_candidate(_FAKE_METRICS)
    assert a == b


@test("select_winner picks the candidate with the highest weighted score")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        baseline = {"map50": 0.3, "per_class": {"string": {"ap50": 0.2}}}
        weak = {"map50": 0.35, "per_class": {"string": {"ap50": 0.25}}}
        strong = {"map50": 0.6, "per_class": {"string": {"ap50": 0.55}}}

        (tmp / "baseline.json").write_text(json.dumps(baseline))
        (tmp / "weak.json").write_text(json.dumps(weak))
        (tmp / "strong.json").write_text(json.dumps(strong))

        result = select_winner(
            baseline_path=str(tmp / "baseline.json"),
            candidate_paths={"weak": str(tmp / "weak.json"), "strong": str(tmp / "strong.json")},
            report_dir=tmp,
        )
        assert result["winner"] == "strong"
        assert (tmp / "selection_report.json").exists()


@test("select_winner ranking is sorted best-first")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        baseline = {"map50": 0.3, "per_class": {}}
        a = {"map50": 0.4, "per_class": {}}
        b = {"map50": 0.7, "per_class": {}}
        (tmp / "baseline.json").write_text(json.dumps(baseline))
        (tmp / "a.json").write_text(json.dumps(a))
        (tmp / "b.json").write_text(json.dumps(b))

        result = select_winner(
            baseline_path=str(tmp / "baseline.json"),
            candidate_paths={"a": str(tmp / "a.json"), "b": str(tmp / "b.json")},
            report_dir=tmp,
        )
        assert result["ranking"][0]["name"] == "b"
        assert result["ranking"][1]["name"] == "a"


print("\n" + "═" * 65)
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
print(f"  Results: {passed} passed, {failed} failed  ({len(_results)} total)")
if failed:
    for name, ok, err in _results:
        if not ok:
            print(f"    - {name}: {err}")
sys.exit(0 if failed == 0 else 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONSAFEPATH=1 python3 tests/test_select_winner.py 2>&1 | tail -20`
Expected: `ModuleNotFoundError: No module named 'ml.eval.select_winner'`.

- [ ] **Step 3: Write minimal implementation**

Create `ml/eval/select_winner.py`:

```python
#!/usr/bin/env python3
"""Pick the winning bake-off candidate from evaluate.py-style metrics JSONs.

Usage:
    python3 -m ml.eval.select_winner \
        --baseline ml/eval/results/baseline/metrics.json \
        --candidate yolo11x=ml/eval/results/yolo11x/metrics.json \
        --candidate rtdetr-x=ml/eval/results/rtdetr-x/metrics.json \
        --candidate codetr=ml/eval/results/codetr/metrics.json \
        --report-dir ml/eval/results

Weights CRITICAL-severity classes (per ml.src.utils.SEVERITY_MAP) more heavily
than the flat mAP@0.5, since those drive real remediation priority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.src.utils import SEVERITY_MAP

CRITICAL_CLASSES = {cls for cls, sev in SEVERITY_MAP.items() if sev == "CRITICAL"}


def _load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def score_candidate(metrics: dict, critical_weight: float = 2.0) -> float:
    """Weighted score: overall mAP50 plus extra weight on CRITICAL-class AP50."""
    score = metrics.get("map50", 0.0)
    for cls, per_class in metrics.get("per_class", {}).items():
        if cls in CRITICAL_CLASSES:
            score += (critical_weight - 1.0) * per_class.get("ap50", 0.0) / max(len(CRITICAL_CLASSES), 1)
    return score


def select_winner(
    baseline_path: str,
    candidate_paths: dict[str, str],
    critical_weight: float = 2.0,
    report_dir: Path | str = "ml/eval/results",
) -> dict:
    """Rank candidates by weighted score, pick a winner, persist the report."""
    baseline = _load(baseline_path)
    baseline_score = score_candidate(baseline, critical_weight)

    ranking = []
    for name, path in candidate_paths.items():
        metrics = _load(path)
        ranking.append({
            "name": name,
            "path": path,
            "score": score_candidate(metrics, critical_weight),
            "map50": metrics.get("map50", 0.0),
        })
    ranking.sort(key=lambda r: r["score"], reverse=True)

    winner = ranking[0]["name"] if ranking else None
    result = {
        "baseline_score": baseline_score,
        "ranking": ranking,
        "winner": winner,
        "winner_metrics_path": ranking[0]["path"] if ranking else None,
    }

    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "selection_report.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", action="append", required=True, help="name=path, repeatable")
    parser.add_argument("--report-dir", default="ml/eval/results")
    parser.add_argument("--critical-weight", type=float, default=2.0)
    args = parser.parse_args()

    candidate_paths = dict(c.split("=", 1) for c in args.candidate)
    result = select_winner(args.baseline, candidate_paths, args.critical_weight, args.report_dir)

    print(f"Baseline score: {result['baseline_score']:.4f}")
    print("\nRanking:")
    for r in result["ranking"]:
        print(f"  {r['name']:<12} score={r['score']:.4f}  mAP50={r['map50']:.4f}")
    print(f"\nWinner: {result['winner']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONSAFEPATH=1 python3 tests/test_select_winner.py 2>&1 | tail -20`
Expected: 4 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add ml/eval/select_winner.py tests/test_select_winner.py
git commit -m "feat(ml): add CRITICAL-weighted bake-off winner selection script"
```

---

## After all tasks: running the actual bake-off

This plan produces the tooling; running the three real training jobs is an operator action (GCP costs money, takes hours, and needs a Google Cloud account signed in). Once Tasks 1-7 are merged:

1. `PYTHONSAFEPATH=1 python3 -m ml.scripts.prepare_dataset` locally to build `ml/data/combined/`.
2. Follow `deploy/gcp/README.md` to run all three candidate trainings on GCP.
3. Copy each candidate's best weights + run `python3 -m ml.eval.evaluate --model <weights> --data ml/thermal_dataset.yaml --split test --output ml/eval/results/<candidate>/` for baseline and all three candidates.
4. Run `python3 -m ml.eval.select_winner --baseline <baseline metrics.json> --candidate yolo11x=<...> --candidate rtdetr-x=<...> --candidate codetr=<...>` to get the ranked report and winner.
5. Copy the winning weights to `ml/checkpoints/best.pt` (manual step — confirm with the user before overwriting production weights).

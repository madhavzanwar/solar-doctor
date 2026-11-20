"""Build the RGB manifest: extract, normalise class names, drop corrupt/duplicate files, group near-duplicates, split.

    python -m ml.rgb.data.prepare --zip solar-panel-images.zip      # or --kaggle / --raw-dir DIR
    python -m ml.rgb.data.prepare --verify                           # leakage check on the existing manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import warnings
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import imagehash
import pandas as pd
from PIL import Image
from sklearn.model_selection import StratifiedGroupKFold

from solardoctor.vision.model_def import CLASSES, load_image

DATA_DIR = Path(__file__).resolve().parent
KAGGLE_SLUG = "pythonafroz/solar-panel-images"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
ALIASES = {"birddrop": "bird_drop", "birddrops": "bird_drop", "bird_drops": "bird_drop", "dust": "dusty",
           "snow": "snow_covered", "snowcovered": "snow_covered", "electricaldamage": "electrical_damage",
           "physicaldamage": "physical_damage"}
COLUMNS = ["rel_path", "label", "sha256", "phash", "dhash", "group_id", "split", "fold"]


def normalise_class(name: str) -> str | None:
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    key = ALIASES.get(key, key)
    return key if key in CLASSES else None


def extract_zip(zip_path: Path, dest: Path) -> None:
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for m in zf.infolist():
            if not (dest / m.filename).resolve().is_relative_to(dest):
                raise ValueError(f"zip-slip attempt: {m.filename!r}")
        zf.extractall(dest)


def download_kaggle(dest: Path) -> Path:
    has_env = bool(os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")
                   or os.environ.get("KAGGLE_API_TOKEN"))
    if not (has_env or (Path.home() / ".kaggle" / "kaggle.json").exists()):
        raise RuntimeError("Kaggle credentials not found (set KAGGLE_USERNAME/KAGGLE_KEY or ~/.kaggle/kaggle.json)")
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()
    dest.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files(KAGGLE_SLUG, path=str(dest), unzip=False)
    return next(dest.glob("*.zip"))


def _variants(img: Image.Image) -> list[Image.Image]:
    """Original first, then hflip, vflip, rot90, rot180, rot270."""
    T = Image.Transpose
    return [img] + [img.transpose(t) for t in (T.FLIP_LEFT_RIGHT, T.FLIP_TOP_BOTTOM, T.ROTATE_90, T.ROTATE_180,
                                               T.ROTATE_270)]


def _all_hashes(path: Path) -> list[tuple[str, str]]:
    """(pHash, dHash) of the image and of its 5 flip/rotation variants; index 0 is the original."""
    with Image.open(path) as im:
        img = load_image(im)
    return [(str(imagehash.phash(v, 8)), str(imagehash.dhash(v, 8))) for v in _variants(img)]


def _hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def hash_dist(a_orig: tuple[str, str], b_variants: list[tuple[str, str]]) -> tuple[int, int]:
    """Min (pHash, dHash) Hamming distance between A's original hashes and any variant hash of B."""
    return (min(_hamming(a_orig[0], v[0]) for v in b_variants), min(_hamming(a_orig[1], v[1]) for v in b_variants))


def scan(raw_dir: Path) -> tuple[list[dict], list[dict]]:
    """Walk raw_dir -> (kept rows with hashes, removed rows). Raises on image folders that map to no class."""
    raw_dir = Path(raw_dir)
    rows, removed, unknown = [], [], set()
    for p in sorted(raw_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(raw_dir)
        label = next((c for d in reversed(rel.parts[:-1]) if (c := normalise_class(d))), None)
        if label is None:
            if p.suffix.lower() in IMG_EXTS:
                unknown.add(rel.parent.as_posix())
            continue
        rp = rel.as_posix()
        if p.suffix.lower() not in IMG_EXTS:
            removed.append({"rel_path": rp, "reason": "not_image", "kept_rel_path": ""})
            continue
        try:
            with Image.open(p) as im:
                im.verify()
            with Image.open(p) as im:
                im.load()
            variants = _all_hashes(p)
        except Exception:
            removed.append({"rel_path": rp, "reason": "corrupt", "kept_rel_path": ""})
            continue
        rows.append({"rel_path": rp, "label": label, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                     "phash": variants[0][0], "dhash": variants[0][1], "variants": variants})
    if unknown:
        raise ValueError(f"image folders that map to no known class {CLASSES}: {sorted(unknown)}")
    return rows, removed


def drop_exact_duplicates(rows: list[dict], removed: list[dict]) -> list[dict]:
    by_sha = defaultdict(list)
    for r in rows:
        by_sha[r["sha256"]].append(r)
    kept = []
    for grp in by_sha.values():
        grp.sort(key=lambda r: r["rel_path"])
        kept.append(grp[0])
        removed += [{"rel_path": r["rel_path"], "reason": "exact_duplicate", "kept_rel_path": grp[0]["rel_path"]}
                    for r in grp[1:]]
    return sorted(kept, key=lambda r: r["rel_path"])


def dinov2_embed_fn(batch_size: int = 32):
    """Default embedding function: list of RGB PIL images -> DINOv2-small features [N, D] (cosine is taken later)."""
    import numpy as np
    import torch
    from transformers import Dinov2Model

    from solardoctor.vision.model_def import preprocess
    from solardoctor.vision.ood import dinov2_features
    bb = Dinov2Model.from_pretrained("facebook/dinov2-small").eval()

    def fn(imgs):
        out = []
        for s in range(0, len(imgs), batch_size):
            x = torch.as_tensor(np.stack([preprocess(i, {"img_size": 224}) for i in imgs[s:s + batch_size]]))
            with torch.no_grad():
                out.append(dinov2_features(bb, x).numpy())
        return np.concatenate(out)
    return fn


def near_dup_groups(rows: list[dict], p_thr: int, d_thr: int, feats=None, cos_thr: float = 0.95
                    ) -> tuple[list[int], list[dict]]:
    """Union-find over edges: pHash<=p_thr or dHash<=d_thr (min over flip/rotation variants), or cosine>=cos_thr.

    `feats` ([N, D] embeddings aligned with rows, optional). Returns group ids (aligned with rows) + all edges,
    each with phash_dist, dhash_dist, cosine (None without feats) and `source` in hash|embedding|both.
    """
    import numpy as np
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cos = None
    if feats is not None:
        f = np.asarray(feats, dtype=np.float64)
        f = f / np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-12)
        cos = f @ f.T
    edges = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            dp, dd = hash_dist((rows[i]["phash"], rows[i]["dhash"]), rows[j]["variants"])
            by_hash = dp <= p_thr or dd <= d_thr
            by_emb = cos is not None and cos[i, j] >= cos_thr
            if by_hash or by_emb:
                parent[find(j)] = find(i)
                edges.append({"a": rows[i]["rel_path"], "b": rows[j]["rel_path"], "phash_dist": dp, "dhash_dist": dd,
                              "cosine": None if cos is None else float(cos[i, j]),
                              "source": "both" if by_hash and by_emb else "hash" if by_hash else "embedding"})
    # rows are sorted by rel_path, so numbering roots in first-seen order is deterministic
    ids: dict[int, int] = {}
    return [ids.setdefault(find(i), len(ids)) for i in range(len(rows))], edges


def _take_fold(df: pd.DataFrame, n_splits: int, seed: int):
    """(rest_idx, held_idx) of the first StratifiedGroupKFold split, stratified by group label."""
    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # tiny classes give a "least populated class" warning
        rest, held = next(iter(sgkf.split(df, df["strat"], df["group_id"])))
    return df.index[rest], df.index[held]


def assign_splits(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    df = df.copy()
    maj = {}
    for g, sub in df.groupby("group_id"):
        counts = Counter(sub["label"])
        maj[g] = min(counts, key=lambda c: (-counts[c], CLASSES.index(c)))  # ties -> lowest CLASSES index
    df["strat"] = df["group_id"].map(maj)
    df["split"], df["fold"] = "train", -1
    rest, test = _take_fold(df, 7, seed)  # ~14% test
    df.loc[test, "split"] = "test"
    _, val = _take_fold(df.loc[rest], 6, seed)  # ~14% of total
    df.loc[val, "split"] = "val"
    tv = df.loc[rest]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for k, (_, idx) in enumerate(StratifiedGroupKFold(5, shuffle=True, random_state=seed)
                                     .split(tv, tv["strat"], tv["group_id"])):
            df.loc[tv.index[idx], "fold"] = k
    return df.drop(columns="strat")


def _per_class(sub: pd.DataFrame) -> dict:
    c = Counter(sub["label"])
    return {k: c.get(k, 0) for k in CLASSES}


def build_stats(raw_counts, df, removed, edges, thresholds) -> dict:
    multi = df.groupby("group_id")["rel_path"].transform("count") > 1
    cross = [{"group_id": int(g), "members": [{"rel_path": r, "label": l} for r, l in zip(s["rel_path"], s["label"])]}
             for g, s in df.groupby("group_id") if s["label"].nunique() > 1]
    return {
        "thresholds": thresholds,
        "raw_per_class": raw_counts,
        "after_cleaning_per_class": _per_class(df),
        "removed_per_reason": dict(Counter(r["reason"] for r in removed)),
        "near_dup_groups_per_class": {k: int(df[multi & (df["label"] == k)]["group_id"].nunique()) for k in CLASSES},
        "near_dup_images_per_class": _per_class(df[multi]),
        "split_per_class": {s: _per_class(df[df["split"] == s]) for s in ("train", "val", "test")},
        "fold_per_class": {str(f): _per_class(df[df["fold"] == f]) for f in (-1, 0, 1, 2, 3, 4)},
        "cross_label_groups": cross,
        "edges": {"hash": sum(e["source"] != "embedding" for e in edges),
                  "embedding": sum(e["source"] != "hash" for e in edges),
                  "embedding_only": sum(e["source"] == "embedding" for e in edges)},
        # audit these to judge whether --cos-threshold is too loose
        "embedding_only_examples": [{"a": e["a"], "b": e["b"], "cosine": e["cosine"]} for e in
                                    sorted((e for e in edges if e["source"] == "embedding"),
                                           key=lambda e: (-e["cosine"], e["a"]))[:10]],
        "near_duplicate_examples": sorted((e for e in edges if e["source"] != "embedding"),
                                          key=lambda e: (e["phash_dist"] + e["dhash_dist"], e["a"]))[:10],
        "exact_duplicate_examples": [r for r in removed if r["reason"] == "exact_duplicate"][:10],
    }


def prepare(raw_dir: Path, out_dir: Path = DATA_DIR, p_thr: int = 6, d_thr: int = 6, seed: int = 42,
            embed_fn=None, cos_thr: float = 0.95) -> pd.DataFrame:
    """embed_fn: list[PIL RGB] -> [N, D] features (inject for tests; None disables the embedding edge)."""
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    rows, removed = scan(raw_dir)
    raw_counts = {k: sum(r["label"] == k for r in rows) for k in CLASSES}
    rows = drop_exact_duplicates(rows, removed)
    feats = None
    if embed_fn is not None:
        feats = embed_fn([load_image(Image.open(raw_dir / r["rel_path"])) for r in rows])
    gids, edges = near_dup_groups(rows, p_thr, d_thr, feats, cos_thr)
    df = assign_splits(pd.DataFrame(rows).assign(group_id=gids), seed)
    df = df[COLUMNS].sort_values("rel_path").reset_index(drop=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "manifest.csv", index=False)
    pd.DataFrame(sorted(removed, key=lambda r: r["rel_path"]),
                 columns=["rel_path", "reason", "kept_rel_path"]).to_csv(out_dir / "removed.csv", index=False)
    stats = build_stats(raw_counts, df, removed, edges, {"phash": p_thr, "dhash": d_thr, "seed": seed,
                                                     "cosine": cos_thr if embed_fn is not None else None,
                                                     "hash_variants": "orig+hflip+vflip+rot90/180/270"})
    stats["leak_check"] = verify_no_leak(df, raw_dir, p_thr, d_thr)
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2, sort_keys=True), encoding="utf-8")
    return df


def verify_no_leak(df: pd.DataFrame, raw_dir: Path | None = None, p_thr: int = 6, d_thr: int = 6) -> dict:
    """Raise AssertionError on any leak; with raw_dir also recompute hashes from files (test vs train/val)."""
    if (df.groupby("group_id")["split"].nunique() > 1).any():
        raise AssertionError("a group_id spans several splits")
    if (df[df["fold"] >= 0].groupby("group_id")["fold"].nunique() > 1).any():
        raise AssertionError("a group_id spans several folds")
    out = {"ok": True, "min_phash_dist": None, "min_dhash_dist": None}
    if raw_dir is not None:
        h = {r: _all_hashes(Path(raw_dir) / r) for r in df["rel_path"]}
        test = df.loc[df["split"] == "test", "rel_path"]
        other = df.loc[df["split"] != "test", "rel_path"]
        if len(test) and len(other):
            d = [hash_dist(h[a][0], h[b]) for a in test for b in other]
            out["min_phash_dist"], out["min_dhash_dist"] = min(x[0] for x in d), min(x[1] for x in d)
            if out["min_phash_dist"] <= p_thr or out["min_dhash_dist"] <= d_thr:
                raise AssertionError(f"test image within dedupe threshold of train/val: {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--zip", type=Path)
    src.add_argument("--kaggle", action="store_true")
    src.add_argument("--raw-dir", type=Path)
    ap.add_argument("--verify", action="store_true", help="check the existing manifest for leakage and exit")
    ap.add_argument("--phash-threshold", type=int, default=6)
    ap.add_argument("--dhash-threshold", type=int, default=6)
    ap.add_argument("--cos-threshold", type=float, default=0.95, help="DINOv2-small cosine edge threshold")
    ap.add_argument("--no-embed", action="store_true", help="disable the embedding edge (hash edges only)")
    a = ap.parse_args()
    raw = a.raw_dir or DATA_DIR / "raw"
    if a.verify:
        print(json.dumps(verify_no_leak(pd.read_csv(DATA_DIR / "manifest.csv"), raw,
                                        a.phash_threshold, a.dhash_threshold)))
        return
    if a.kaggle:
        a.zip = download_kaggle(DATA_DIR / "_download")
    if a.zip:
        extract_zip(a.zip, raw)
    df = prepare(raw, DATA_DIR, a.phash_threshold, a.dhash_threshold,
                 embed_fn=None if a.no_embed else dinov2_embed_fn(), cos_thr=a.cos_threshold)
    print(f"manifest: {len(df)} rows -> {DATA_DIR / 'manifest.csv'}")


if __name__ == "__main__":
    main()

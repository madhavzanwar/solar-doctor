import json
import zipfile

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from ml.rgb.augment import eval_array, normalize, train_transform
from ml.rgb.data import make_data_card
from ml.rgb.data.prepare import extract_zip, normalise_class, prepare, verify_no_leak
from ml.rgb.dataset import RGBPanelDataset, balanced_sampler, class_weights
from solardoctor.vision.model_def import CLASSES, preprocess

FOLDERS = {"clean": "Clean", "dusty": "Dust", "bird_drop": "Bird-drop", "snow_covered": "Snow-Covered",
           "electrical_damage": "Faulty_solar_panel/Electrical-damage", "physical_damage": "Faulty_solar_panel/Physical-Damage"}
PER_CLASS = 14
CFG = {"img_size": 64, "grayscale": False}


def _tex(seed: int) -> Image.Image:
    # low-frequency random texture: distinct hashes per seed
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (8, 8, 3), dtype=np.uint8)
    return Image.fromarray(small).resize((160, 120), Image.BICUBIC)


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    raw = tmp_path_factory.mktemp("raw")
    seed = 0
    for cls, folder in FOLDERS.items():
        d = raw / folder
        d.mkdir(parents=True)
        for i in range(PER_CLASS):
            _tex(seed).save(d / f"{i:02d}.jpg", quality=95)
            seed += 1
    c = raw / FOLDERS["clean"]
    img = Image.open(c / "00.jpg")
    img.resize((120, 90)).save(c / "near_resized.jpg", quality=60)
    Image.eval(img, lambda v: min(255, v + 6)).save(c / "near_bright.jpg", quality=60)
    (c / "exact.jpg").write_bytes((c / "01.jpg").read_bytes())
    (c / "corrupt.jpg").write_bytes(b"not a jpeg")
    (c / "notes.txt").write_text("hi")
    return raw


@pytest.fixture(scope="module")
def out(raw, tmp_path_factory):
    d = tmp_path_factory.mktemp("out")
    prepare(raw, d)
    return d


def test_normalise_class():
    for n in ["Bird-drop", "bird drop", "birddrop", " BIRD_DROP "]:
        assert normalise_class(n) == "bird_drop"
    assert normalise_class("Snow-Covered") == "snow_covered"
    assert normalise_class("dusty") == normalise_class("Dust") == "dusty"
    assert normalise_class("Electrical-damage") == "electrical_damage"
    assert normalise_class("Faulty_solar_panel") is None


def test_unknown_folder_raises(tmp_path):
    (tmp_path / "Clean").mkdir()
    _tex(1).save(tmp_path / "Clean" / "a.jpg")
    (tmp_path / "Weird").mkdir()
    _tex(2).save(tmp_path / "Weird" / "b.jpg")
    with pytest.raises(ValueError, match="Weird"):
        prepare(tmp_path, tmp_path / "o")


def test_removed(out):
    rm = pd.read_csv(out / "removed.csv").fillna("")
    by = dict(zip(rm["rel_path"], rm["reason"]))
    assert by["Clean/corrupt.jpg"] == "corrupt"
    assert by["Clean/notes.txt"] == "not_image"
    assert by["Clean/exact.jpg"] == "exact_duplicate"
    assert rm.set_index("rel_path").loc["Clean/exact.jpg", "kept_rel_path"] == "Clean/01.jpg"


def test_manifest_groups_and_splits(out):
    m = pd.read_csv(out / "manifest.csv")
    assert list(m.columns) == ["rel_path", "label", "sha256", "phash", "dhash", "group_id", "split", "fold"]
    assert set(m["label"]) == set(CLASSES)
    g = m.set_index("rel_path")["group_id"]
    assert g["Clean/00.jpg"] == g["Clean/near_resized.jpg"] == g["Clean/near_bright.jpg"]
    assert (m.groupby("group_id")["split"].nunique() == 1).all()
    tv = m[m["fold"] >= 0]
    assert (tv.groupby("group_id")["fold"].nunique() == 1).all()
    assert (m[m["split"] == "test"]["fold"] == -1).all() and set(tv["fold"]) == {0, 1, 2, 3, 4}
    frac = m["split"].value_counts(normalize=True)
    assert 0.08 < frac["test"] < 0.25 and 0.08 < frac["val"] < 0.25 and frac["train"] > 0.55
    assert all((m[m["split"] == "test"]["label"] == c).any() for c in CLASSES)
    st = json.loads((out / "stats.json").read_text())
    assert st["removed_per_reason"] == {"corrupt": 1, "not_image": 1, "exact_duplicate": 1}
    assert st["near_dup_groups_per_class"]["clean"] == 1 and st["leak_check"]["ok"]


def test_verify_no_leak(raw, out):
    m = pd.read_csv(out / "manifest.csv")
    res = verify_no_leak(m, raw)
    assert res["min_phash_dist"] > 6 and res["min_dhash_dist"] > 6
    leaked = m.copy()
    i = leaked.index[leaked["rel_path"] == "Clean/near_resized.jpg"][0]
    leaked.loc[i, "split"] = "test" if leaked.loc[i, "split"] != "test" else "train"
    with pytest.raises(AssertionError):
        verify_no_leak(leaked)
    # a test image cloned into train under a fresh group id is caught by the hash check
    t = m[m["split"] == "test"].iloc[0]
    clone = raw / "Clean" / "leak.jpg"
    Image.open(raw / t["rel_path"]).save(clone, quality=70)
    try:
        bad = pd.concat([m, pd.DataFrame([{**t.to_dict(), "rel_path": "Clean/leak.jpg", "group_id": 9999, "split": "train", "fold": 0}])])
        with pytest.raises(AssertionError):
            verify_no_leak(bad, raw)
    finally:
        clone.unlink()


def test_deterministic(raw, out, tmp_path):
    prepare(raw, tmp_path)
    for f in ("manifest.csv", "removed.csv", "stats.json"):
        assert (tmp_path / f).read_bytes() == (out / f).read_bytes()


def test_zip_input_and_slip(raw, tmp_path):
    z = tmp_path / "d.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for p in raw.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(raw).as_posix())
    extract_zip(z, tmp_path / "x")
    assert (tmp_path / "x" / "Clean" / "00.jpg").exists()
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escape.txt", "x")
    with pytest.raises(ValueError, match="zip-slip"):
        extract_zip(evil, tmp_path / "y")
    assert not (tmp_path / "escape.txt").exists()


def test_data_card(out):
    stats = json.loads((out / "stats.json").read_text())
    md = make_data_card.render(stats)
    assert "Unknown" in md and "Clean/exact.jpg" in md and "near:" in md
    assert str(stats["raw_per_class"]["clean"]) in md and "Leakage check" in md


def test_augment_and_eval():
    arr = np.asarray(_tex(3).resize((200, 150)))
    o = train_transform(64)(image=arr)["image"]
    assert o.shape == (64, 64, 3) and o.dtype == np.uint8
    for cfg in (CFG, {**CFG, "grayscale": True, "mean": [0.5] * 3, "std": [0.2] * 3}):
        pil = _tex(4)
        assert np.array_equal(eval_array(pil, cfg), preprocess(pil, cfg))
        x = normalize(np.asarray(pil.resize((64, 64))), cfg)
        assert x.shape == (3, 64, 64) and x.dtype == np.float32


def test_dataset(raw, out):
    m = pd.read_csv(out / "manifest.csv").head(8)
    for train in (True, False):
        ds = RGBPanelDataset(m, raw, CFG, train)
        x, y = ds[0]
        assert len(ds) == 8 and tuple(x.shape) == (3, 64, 64) and str(x.dtype) == "torch.float32" and 0 <= y < 6
    w = class_weights([0, 0, 0, 1])
    assert abs(float(w[[0, 1]].mean()) - 1) < 1e-6 and w[1] > w[0]
    assert len(list(balanced_sampler([0, 0, 0, 1]))) == 4

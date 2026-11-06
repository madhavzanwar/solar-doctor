from __future__ import annotations

import numpy as np
import pytest
import torch
from PIL import Image

from solardoctor.vision import ood
from solardoctor.vision.model_def import build_autoencoder


def test_mahalanobis_in_dist_low_shifted_high():
    rng = np.random.default_rng(0)
    train = rng.normal(size=(500, 8))
    mean, prec = ood.fit_mahalanobis(train)
    assert mean.shape == (8,) and prec.shape == (8, 8)
    inside = ood.mahalanobis_score(rng.normal(size=(100, 8)), mean, prec)
    shifted = ood.mahalanobis_score(rng.normal(loc=6.0, size=(100, 8)), mean, prec)
    assert inside.mean() < 4 and shifted.mean() > 3 * inside.mean()


def _tiny_dinov2():
    from transformers import Dinov2Config, Dinov2Model
    return Dinov2Model(Dinov2Config(hidden_size=32, num_hidden_layers=2, num_attention_heads=2,
                                    intermediate_size=64, image_size=28, patch_size=14))


def test_dinov2_features_and_scorer(tmp_path, monkeypatch):
    backbone = _tiny_dinov2().eval()
    x = torch.randn(3, 3, 28, 28)
    with torch.no_grad():
        assert ood.dinov2_features(backbone, x).shape == (3, 64)
    mean, prec = ood.fit_mahalanobis(np.random.default_rng(0).normal(size=(50, 64)))
    np.savez(tmp_path / "ood_stats.npz", mean=mean, precision=prec)
    monkeypatch.setattr(ood, "_load_dinov2", lambda _id, _rev=None: backbone)
    scorer = ood.load_scorer({"ood": {"method": "mahalanobis_dinov2"}}, tmp_path)
    assert scorer(Image.new("RGB", (40, 40), (10, 200, 30))) >= 0.0


def test_clip_zero_shot_score():
    from transformers import CLIPConfig, CLIPModel
    cfg = CLIPConfig(
        text_config=dict(hidden_size=16, intermediate_size=32, num_hidden_layers=1, num_attention_heads=2,
                         vocab_size=50, max_position_embeddings=8),
        vision_config=dict(hidden_size=16, intermediate_size=32, num_hidden_layers=1, num_attention_heads=2,
                           image_size=28, patch_size=14),
        projection_dim=8)

    def processor(text, images, return_tensors, padding):  # stub: tokenizer weights are not available offline
        return {"input_ids": torch.randint(0, 50, (len(text), 8)),
                "pixel_values": torch.randn(len(images), 3, 28, 28)}

    z = ood.ClipZeroShot("unused", ["a", "b"], ["c", "d", "e"], model=CLIPModel(cfg), processor=processor)
    s = z.score([Image.new("RGB", (8, 8))] * 2)
    assert s.shape == (2,) and ((s >= 0) & (s <= 1)).all()


def test_autoencoder_score_shape_and_helper(tmp_path):
    ae = build_autoencoder(100)
    g = ood.to_gray100(Image.new("RGB", (30, 50), (255, 0, 0)))
    assert g.shape == (1, 100, 100) and 0 <= g.min() and g.max() <= 1
    s = ood.autoencoder_score(ae, torch.rand(4, 1, 100, 100))
    assert s.shape == (4,) and (s >= 0).all()


def test_load_scorer_none_and_unknown(tmp_path):
    assert ood.load_scorer({"ood": {"method": "none"}}, tmp_path) is None
    assert ood.load_scorer({}, tmp_path) is None
    with pytest.raises(ValueError):
        ood.load_scorer({"ood": {"method": "bogus"}}, tmp_path)


def test_ood_backbones_are_loaded_at_the_pinned_revision(tmp_path, monkeypatch):
    import numpy as np
    import transformers
    from solardoctor.vision import ood
    seen = []

    class Fake:
        def eval(self):
            return self

    monkeypatch.setattr(transformers.Dinov2Model, "from_pretrained",
                        classmethod(lambda cls, i, **k: seen.append(("dino", k.get("revision"))) or Fake()))
    monkeypatch.setattr(transformers.CLIPModel, "from_pretrained",
                        classmethod(lambda cls, i, **k: seen.append(("clip", k.get("revision"))) or Fake()))
    monkeypatch.setattr(transformers.CLIPProcessor, "from_pretrained",
                        classmethod(lambda cls, i, **k: seen.append(("proc", k.get("revision"))) or Fake()))
    np.savez(tmp_path / "ood_stats.npz", mean=np.zeros(2), precision=np.eye(2))
    ood.load_scorer({"ood": {"method": "mahalanobis_dinov2", "backbone_revision": "abc123"}}, tmp_path)
    ood.load_scorer({"ood": {"method": "clip_zeroshot", "backbone_revision": "def456"}}, tmp_path)
    assert seen == [("dino", "abc123"), ("clip", "def456"), ("proc", "def456")]

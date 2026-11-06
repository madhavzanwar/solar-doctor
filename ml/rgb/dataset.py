"""Torch dataset over manifest rows; decodes each image once and caches a downscaled copy in RAM."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset, WeightedRandomSampler

from ml.rgb.augment import normalize, train_transform
from solardoctor.vision.model_def import CLASSES, load_image, preprocess


class RGBPanelDataset(Dataset):
    def __init__(self, rows, raw_dir, cfg: dict, train: bool):
        """rows: manifest DataFrame (or subset) with rel_path + label columns."""
        self.cfg, self.train = cfg, train
        self.labels = [CLASSES.index(l) for l in rows["label"]]
        self.tf = train_transform(int(cfg["img_size"])) if train else None
        short = max(int(cfg["img_size"] * 1.15), 256 if cfg["img_size"] <= 224 else 0)
        self.images = []
        for rel in rows["rel_path"]:
            with Image.open(Path(raw_dir) / rel) as im:
                img = load_image(im)
            scale = short / min(img.size)
            if scale < 1:
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.BILINEAR)
            self.images.append(img)

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, i: int):
        img = self.images[i]
        if self.train:
            x = normalize(self.tf(image=np.asarray(img))["image"], self.cfg)
        else:
            x = preprocess(img, self.cfg)
        return torch.from_numpy(x), self.labels[i]


def class_weights(labels) -> torch.Tensor:
    """Inverse-frequency weight per class index (mean 1 over classes present)."""
    counts = torch.bincount(torch.as_tensor(list(labels)), minlength=len(CLASSES)).float()
    w = torch.where(counts > 0, 1.0 / counts.clamp(min=1), torch.zeros_like(counts))
    return w * (counts > 0).sum() / w.sum()


def balanced_sampler(labels) -> WeightedRandomSampler:
    labels = list(labels)
    w = class_weights(labels)
    return WeightedRandomSampler([float(w[l]) for l in labels], num_samples=len(labels), replacement=True)

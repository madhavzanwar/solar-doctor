"""Train-time augmentation (albumentations 2.x API) + normalisation identical to model_def.preprocess."""
from __future__ import annotations

import albumentations as A
import numpy as np
from PIL import Image

from solardoctor.vision.model_def import preprocess


def train_transform(img_size: int) -> A.Compose:
    """uint8 HWC RGB -> uint8 img_size x img_size HWC RGB. Colour jitter is mild: colour carries the signal."""
    return A.Compose([
        A.RandomResizedCrop((img_size, img_size), scale=(0.6, 1.0)),
        A.HorizontalFlip(),
        A.VerticalFlip(),
        A.Rotate(limit=20, border_mode=0, p=0.7),
        A.Perspective(p=0.3),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2),
        A.HueSaturationValue(hue_shift_limit=5, sat_shift_limit=10, val_shift_limit=10, p=0.5),
        A.OneOf([A.GaussianBlur(), A.MotionBlur()], p=0.2),
        A.ImageCompression(quality_range=(40, 95), p=0.3),
        A.RandomSunFlare(p=0.05),  # glare
    ])


def normalize(arr: np.ndarray, cfg: dict) -> np.ndarray:
    """uint8 HWC RGB (already img_size square) -> float32 CHW, same semantics as model_def.preprocess."""
    return preprocess(Image.fromarray(arr), cfg)  # preprocess's resize is a no-op at the target size


def eval_array(pil: Image.Image, cfg: dict) -> np.ndarray:
    return preprocess(pil, cfg)

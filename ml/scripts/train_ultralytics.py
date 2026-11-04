"""
train_ultralytics.py — shared Ultralytics trainer for the YOLO11x and RT-DETR-x
bake-off candidates.

Usage:
    python3 -m ml.scripts.train_ultralytics --config ml/configs/thermal_yolo11x.yaml
    python3 -m ml.scripts.train_ultralytics --config ml/configs/thermal_rtdetr_x.yaml
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from ml.src.utils import get_logger

logger = get_logger(__name__)

_NON_TRAIN_KEYS = {"dataset_yaml", "model"}


def load_training_config(path: Path) -> dict:
    """Load a thermal_*.yaml training config."""
    return yaml.safe_load(Path(path).read_text())


def build_model(model_name: str, resume_from: str | None = None):
    """Lazily construct the right Ultralytics model class for `model_name`.

    If `resume_from` is given (a path to a prior last.pt checkpoint), the
    model is loaded from that checkpoint instead of the config's pretrained
    weights, so training resumes from where a preempted run left off.
    """
    weights = resume_from if resume_from else model_name
    if model_name.startswith("rtdetr"):
        from ultralytics import RTDETR
        return RTDETR(weights)
    from ultralytics import YOLO
    return YOLO(weights)


def _maybe_enable_wandb(model, run_name: str) -> None:
    """Attach W&B logging if WANDB_API_KEY is set in the environment; no-op otherwise.

    Uses Ultralytics' own stable, documented callback API (on_fit_epoch_end)
    rather than the wandb.integration.ultralytics package — that package's
    add_wandb_callback raised "NameError: name 'RANK' is not defined" against
    the ultralytics version pinned here, a version-compatibility break in the
    third-party wrapper rather than anything on our side.
    """
    if not os.environ.get("WANDB_API_KEY"):
        return
    import wandb

    wandb.login()
    wandb.init(entity="axalonsystems-", project="axalon-thermal-bakeoff", name=run_name, reinit=True)

    def _log_epoch(trainer) -> None:
        wandb.log(trainer.metrics, step=trainer.epoch)

    model.add_callback("on_fit_epoch_end", _log_epoch)
    logger.info("W&B logging enabled for run %s", run_name)


def run_training(config_path: Path, resume_from: str | None = None) -> None:
    """Train the model described by `config_path` and log the result location.

    If `resume_from` points at an existing last.pt checkpoint, training
    resumes from it (Ultralytics reads the saved training state) instead of
    starting fresh from the config's pretrained weights.
    """
    cfg = load_training_config(config_path)
    model = build_model(cfg["model"], resume_from=resume_from)
    _maybe_enable_wandb(model, run_name=cfg.get("name", "run"))

    train_kwargs = {k: v for k, v in cfg.items() if k not in _NON_TRAIN_KEYS}
    train_kwargs["data"] = cfg["dataset_yaml"]
    if resume_from:
        train_kwargs["resume"] = True

    logger.info("Starting training with config %s (resume_from=%s)", config_path, resume_from)
    model.train(**train_kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--resume-from", default=None, help="Path to a prior last.pt checkpoint to resume from")
    args = parser.parse_args()
    run_training(Path(args.config), resume_from=args.resume_from)


if __name__ == "__main__":
    main()

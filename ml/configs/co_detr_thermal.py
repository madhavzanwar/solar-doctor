"""
co_detr_thermal.py — MMDetection config for the Co-DETR bake-off candidate.

Usage (on the GCP training VM, cwd must be the mmdetection checkout so the
base config's custom_imports of projects.CO-DETR resolves):
    cd /opt/mmdetection && python3 tools/train.py /opt/repo/ml/configs/co_detr_thermal.py

Targets MMDetection 3.3.0's built-in CO-DETR project (open-mmlab/mmdetection,
projects/CO-DETR) with mmcv 2.1.0 + torch 2.1.2 — the Sense-X/Co-DETR repo is
mmdet 2.x-era and cannot build against this stack.

Falls back to DINO (base = 'dino/dino-4scale_r50_8xb2-12e_coco.py') if Co-DETR
training proves unstable — see the "Risks" section of the design spec at
docs/superpowers/specs/2026-07-01-thermal-model-retraining-bakeoff-design.md.
"""

# Absolute VM paths: this config is consumed only on the training VM, where the
# repo lives at /opt/repo and the mmdetection checkout at /opt/mmdetection.
_base_ = "/opt/mmdetection/projects/CO-DETR/configs/codino/co_dino_5scale_r50_8xb2_1x_coco.py"

data_root = "/opt/repo/ml/data/combined_coco/"
classes = (
    "cell", "cell-multi", "module", "string", "bypass-diode",
    "offline-module", "vegetation-shading", "soiling", "short-circuit",
    "hot-spot-low", "hot-spot-high",
)
num_classes = len(classes)

# mmengine merges dict overrides but REPLACES list-typed fields wholesale, so
# roi_head/bbox_head (lists in the base config) must be restated in full — a
# partial dict like [dict(bbox_head=dict(num_classes=...))] loses the 'type'
# key and fails model registry build. Copied verbatim from the base
# co_dino_5scale_r50_lsj_8xb2_1x_coco.py with only num_classes changed.
num_dec_layer = 6
loss_lambda = 2.0

model = dict(
    query_head=dict(num_classes=num_classes),
    roi_head=[
        dict(
            type="CoStandardRoIHead",
            bbox_roi_extractor=dict(
                type="SingleRoIExtractor",
                roi_layer=dict(type="RoIAlign", output_size=7, sampling_ratio=0),
                out_channels=256,
                featmap_strides=[4, 8, 16, 32, 64],
                finest_scale=56,
            ),
            bbox_head=dict(
                type="Shared2FCBBoxHead",
                in_channels=256,
                fc_out_channels=1024,
                roi_feat_size=7,
                num_classes=num_classes,
                bbox_coder=dict(
                    type="DeltaXYWHBBoxCoder",
                    target_means=[0.0, 0.0, 0.0, 0.0],
                    target_stds=[0.1, 0.1, 0.2, 0.2],
                ),
                reg_class_agnostic=False,
                reg_decoded_bbox=True,
                loss_cls=dict(
                    type="CrossEntropyLoss",
                    use_sigmoid=False,
                    loss_weight=1.0 * num_dec_layer * loss_lambda,
                ),
                loss_bbox=dict(
                    type="GIoULoss", loss_weight=10.0 * num_dec_layer * loss_lambda
                ),
            ),
        )
    ],
    bbox_head=[
        dict(
            type="CoATSSHead",
            num_classes=num_classes,
            in_channels=256,
            stacked_convs=1,
            feat_channels=256,
            anchor_generator=dict(
                type="AnchorGenerator",
                ratios=[1.0],
                octave_base_scale=8,
                scales_per_octave=1,
                strides=[4, 8, 16, 32, 64, 128],
            ),
            bbox_coder=dict(
                type="DeltaXYWHBBoxCoder",
                target_means=[0.0, 0.0, 0.0, 0.0],
                target_stds=[0.1, 0.1, 0.2, 0.2],
            ),
            loss_cls=dict(
                type="FocalLoss",
                use_sigmoid=True,
                gamma=2.0,
                alpha=0.25,
                loss_weight=1.0 * num_dec_layer * loss_lambda,
            ),
            loss_bbox=dict(
                type="GIoULoss", loss_weight=2.0 * num_dec_layer * loss_lambda
            ),
            loss_centerness=dict(
                type="CrossEntropyLoss",
                use_sigmoid=True,
                loss_weight=1.0 * num_dec_layer * loss_lambda,
            ),
        )
    ],
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
test_dataloader = dict(
    dataset=dict(
        data_root=data_root,
        ann_file="test.json",
        data_prefix=dict(img="../combined/test/images/"),
        metainfo=dict(classes=classes),
    )
)

val_evaluator = dict(ann_file=data_root + "val.json")
# classwise=True + the held-out test.json split (not val.json) match how
# ml/eval/evaluate.py scores the Ultralytics candidates, so results are
# directly comparable across all three bake-off candidates.
test_evaluator = dict(
    type="CocoMetric",
    ann_file=data_root + "test.json",
    metric="bbox",
    classwise=True,
)

# /opt/repo/runs is symlinked to the persistent dataset disk by the VM startup
# script, so checkpoints survive spot preemption (same pattern as the
# Ultralytics candidates).
work_dir = "/opt/repo/runs/thermal/codetr_solar"

# Log to the same W&B project as the two Ultralytics candidates so all three
# bake-off runs are monitorable from one dashboard. WANDB_API_KEY comes from
# instance metadata via the environment.
visualizer = dict(
    type="DetLocalVisualizer",
    vis_backends=[
        dict(type="LocalVisBackend"),
        dict(
            type="WandbVisBackend",
            init_kwargs=dict(
                entity="axalonsystems-",
                project="axalon-thermal-bakeoff",
                name="codetr_solar",
            ),
        ),
    ],
)

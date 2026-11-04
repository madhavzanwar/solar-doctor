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

Evaluation and winner selection:

Once weights are copied back locally, evaluate the baseline and every candidate on the held-out test split. `ml/eval/evaluate.py` writes `metrics.json` (plus plots) under a UTC-timestamped subdirectory of `--output`, e.g. `ml/eval/results/yolo11x/20260701_120000/metrics.json`:

```bash
python3 -m ml.eval.evaluate --model ml/checkpoints/best.pt --data ml/thermal_dataset.yaml --split test --output ml/eval/results/baseline/
python3 -m ml.eval.evaluate --model <yolo11x weights path> --data ml/thermal_dataset.yaml --split test --output ml/eval/results/yolo11x/
python3 -m ml.eval.evaluate --model <rtdetr-x weights path> --data ml/thermal_dataset.yaml --split test --output ml/eval/results/rtdetr-x/
python3 -m ml.eval.evaluate --model <codetr weights path> --data ml/thermal_dataset.yaml --split test --output ml/eval/results/codetr/
```

Then rank the candidates against the baseline and pick a winner:

```bash
python3 -m ml.eval.select_winner \
  --baseline ml/eval/results/baseline/<timestamp>/metrics.json \
  --candidate yolo11x=ml/eval/results/yolo11x/<timestamp>/metrics.json \
  --candidate rtdetr-x=ml/eval/results/rtdetr-x/<timestamp>/metrics.json \
  --candidate codetr=ml/eval/results/codetr/<timestamp>/metrics.json
```

Copying the winning weights to `ml/checkpoints/best.pt` is a manual step — confirm with the user before overwriting production weights.

Budget: three candidate runs plus one hyperparameter follow-up on the winner, within the $300 GCP credit, using spot L4 pricing.

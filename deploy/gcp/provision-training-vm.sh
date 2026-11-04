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

# Repo is private — mint a short-lived token via the local gh CLI so the VM
# can clone it. Never persisted to disk or committed anywhere; lives only in
# this VM's instance metadata for the duration of the training run.
GITHUB_TOKEN="$(gh auth token)"

# Optional: export WANDB_API_KEY locally before running this script to enable
# live training dashboards. Omitted entirely (not even as an empty value) when
# unset, so training still runs log-only without it.
WANDB_METADATA=()
if [ -n "${WANDB_API_KEY:-}" ]; then
  WANDB_METADATA=(--metadata "wandb-api-key=${WANDB_API_KEY}")
fi

gcloud compute instances create "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --machine-type=g2-standard-8 \
  --accelerator="type=nvidia-l4,count=1" \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --image-family=common-cu129-ubuntu-2204-nvidia-580 \
  --image-project=deeplearning-platform-release \
  --boot-disk-size=100GB \
  --disk="name=${DISK_NAME},device-name=${DISK_NAME},mode=rw" \
  --metadata=candidate="${CANDIDATE}",github-token="${GITHUB_TOKEN}" \
  "${WANDB_METADATA[@]}" \
  --metadata-from-file=startup-script=deploy/gcp/train-vm-startup.sh

echo "VM ${VM_NAME} created. Tail progress with:"
echo "  gcloud compute instances tail-serial-port-output ${VM_NAME} --zone=${ZONE} --project=${PROJECT_ID}"

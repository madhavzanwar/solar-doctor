#!/usr/bin/env bash
# Copy exactly the files a Hugging Face Docker Space needs for the drone relay
# into a local clone of the Space repo.
#
# Usage:
#   git clone https://huggingface.co/spaces/<user>/<space> /tmp/axalon-relay-space
#   deploy/hf-relay/stage.sh /tmp/axalon-relay-space
#   cd /tmp/axalon-relay-space && git add -A && git commit -m "Deploy relay" && git push
set -euo pipefail

dest="${1:?usage: stage.sh <space-repo-dir>}"
repo="$(cd "$(dirname "$0")/../.." && pwd)"

mkdir -p "$dest/drone"
rm -rf "$dest/drone/common" "$dest/drone/relay"
cp "$repo/deploy/hf-relay/Dockerfile" "$dest/Dockerfile"
cp "$repo/deploy/hf-relay/README.md" "$dest/README.md"
cp "$repo/drone/__init__.py" "$repo/drone/requirements.txt" "$dest/drone/"
cp -r "$repo/drone/common" "$repo/drone/relay" "$dest/drone/"
find "$dest/drone" -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "Staged relay Space files in $dest:"
find "$dest" -path "$dest/.git" -prune -o -type f -print | sort

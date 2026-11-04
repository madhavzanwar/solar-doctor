#!/usr/bin/env bash
# qwen-code.sh — Launch Aider with Qwen2.5-Coder (Ollama) for AxalonSystems
#
# Usage:
#   ./qwen-code.sh                → start fresh session
#   ./qwen-code.sh plan-01        → preload Plan 01 as context
#   ./qwen-code.sh plan-01 plan-02 → preload multiple plans
#   ./qwen-code.sh path/to/file.py → open specific file for editing

set -e
cd "$(dirname "$0")"

export OLLAMA_API_BASE="http://127.0.0.1:11434"

MODEL="ollama/qwen2.5-coder:latest"
PLAN_DIR="docs/plans"

READ_FLAGS=()
FILE_FLAGS=()

for arg in "$@"; do
  # Match plan-NN or plan-NN-some-name
  if [[ "$arg" =~ ^plan-[0-9] ]]; then
    PLAN_FILE="$PLAN_DIR/$arg.md"
    if [[ -f "$PLAN_FILE" ]]; then
      READ_FLAGS+=("--read" "$PLAN_FILE")
      echo ">>> Plan context: $PLAN_FILE"
    else
      echo "Plan not found: $PLAN_FILE"
      exit 1
    fi
  else
    FILE_FLAGS+=("$arg")
  fi
done

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║   AxalonSystems — Qwen2.5-Coder Agent          ║"
echo "║   Model : qwen2.5-coder:latest (Ollama)        ║"
echo "║   Always loaded: CLAUDE.md + MASTER_PLAN.md    ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "  /add <file>    add file to edit context"
echo "  /read <file>   add file as read-only"
echo "  /run <cmd>     run a shell command"
echo "  /diff          show pending diff"
echo "  /undo          undo last change"
echo "  /git           show git status"
echo "  /exit          quit"
echo ""

aider \
  --model "$MODEL" \
  "${READ_FLAGS[@]}" \
  "${FILE_FLAGS[@]}"

#!/usr/bin/env bash
# Prints (stdout) the pytest --deselect arguments for tests that need the thermal weights, but ONLY when
# ml/thermal/checkpoints/best.pt is missing. Prints a clear notice (stderr) listing what is deselected.
# Used by `make test-backend` and CI:   pytest $(scripts/pytest_deselect_args.sh)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIST="$ROOT/tests/weights_required.txt"
if [ -s "$ROOT/ml/thermal/checkpoints/best.pt" ]; then
  echo "pytest_deselect_args: thermal weights present, running ALL tests" >&2
  exit 0
fi
echo "================ WEIGHTS-DEPENDENT TESTS DESELECTED ================" >&2
echo "ml/thermal/checkpoints/best.pt is missing (run 'make weights' once HF_TOKEN/repo is available)." >&2
echo "These tests are NOT run, so this is not a full pass:" >&2
args=()
while IFS= read -r t; do
  case "$t" in ''|'#'*) continue ;; esac
  echo "  - $t" >&2
  args+=("--deselect" "$t")
done < "$LIST"
echo "====================================================================" >&2
printf '%s\n' "${args[@]}"

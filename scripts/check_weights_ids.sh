#!/usr/bin/env bash
# Fails if any test id in tests/weights_required.txt no longer exists (pytest silently ignores stale --deselect ids).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python}"
mapfile -t ids < <(grep -v '^#' tests/weights_required.txt | grep . || true)
echo "weights_required.txt lists ${#ids[@]} test ids"
out="$(mktemp)"
if ! "$PYTHON" -m pytest --collect-only -q "${ids[@]}" > "$out" 2>&1; then
  cat "$out"; echo "::error::a test id in tests/weights_required.txt no longer exists" >&2; exit 1
fi
n="$(grep -c '::' "$out" || true)"
if [ "$n" -ne "${#ids[@]}" ]; then
  cat "$out"; echo "::error::expected ${#ids[@]} tests, collected $n" >&2; exit 1
fi
echo "all ${#ids[@]} ids collect"

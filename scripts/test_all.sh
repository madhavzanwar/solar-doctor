#!/usr/bin/env bash
# test_all.sh — Run the full Phase 2 test suite (pytest + vitest + playwright).
#
# Usage:
#   ./scripts/test_all.sh
#
# Assumes ./run.sh all is up if you want the playwright step to pass.
# If services are not up, this script will start them, run, and stop them.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[test_all]${RESET} $*"; }
success() { echo -e "${GREEN}[test_all]${RESET} $*"; }
fail()    { echo -e "${RED}[test_all]${RESET} $*" >&2; }

started_services=0
ensure_services() {
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1 \
       && curl -fsS -o /dev/null http://localhost:3000/platform; then
        info "Services already running."
    else
        info "Starting services (./run.sh all)..."
        nohup ./run.sh all > /tmp/test_all_run.log 2>&1 &
        started_services=1
        for i in $(seq 1 90); do
            if curl -fsS http://localhost:8000/health >/dev/null 2>&1 \
               && curl -fsS -o /dev/null http://localhost:3000/platform; then
                success "Services ready."
                return 0
            fi
            sleep 1
        done
        fail "Services did not come up in 90s. Check /tmp/test_all_run.log."
        exit 1
    fi
}

cleanup_services() {
    if [ "$started_services" -eq 1 ]; then
        info "Stopping services we started..."
        ./run.sh stop || true
    fi
}
trap cleanup_services EXIT

info "▶ Backend pytest"
(cd /tmp && PYTHONSAFEPATH=1 python -m pytest "$REPO_ROOT" -v)

info "▶ Frontend vitest"
(cd "$REPO_ROOT/website/nextjs" && npm test --silent)

ensure_services

info "▶ Frontend playwright"
(cd "$REPO_ROOT/website/nextjs" && npm run test:e2e --silent)

success "All suites passed."

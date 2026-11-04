#!/usr/bin/env bash
# run.sh — Start Axalon platform services
#
# Usage:
#   ./run.sh               # show help
#   ./run.sh setup         # install platform dependencies
#   ./run.sh doctor        # environment checks
#   ./run.sh api           # start FastAPI on :8000
#   ./run.sh platform      # start Next.js platform UI on :3000
#   ./run.sh all           # start API (background) + platform UI (foreground)
#   ./run.sh stop          # kill running services
#   ./run.sh status        # show service status
#
# Options (env vars):
#   PORT=8000              # API port
#   PLATFORM_PORT=3000     # Next.js platform UI port
#   DEVICE=0               # 0 (GPU) or cpu
#   HOST=0.0.0.0           # bind host

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON="$(command -v python || command -v python3)"
PORT="${PORT:-8000}"
PLATFORM_PORT="${PLATFORM_PORT:-3000}"
HOST="${HOST:-0.0.0.0}"
DEVICE="${DEVICE:-0}"

API_PID_FILE="/tmp/axalon-api.pid"
PLATFORM_PID_FILE="/tmp/axalon-platform.pid"
PLATFORM_DIR="${REPO_ROOT}/website/nextjs"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[axalon]${RESET} $*"; }
success() { echo -e "${GREEN}[axalon]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[axalon]${RESET} $*"; }
error()   { echo -e "${RED}[axalon]${RESET} $*" >&2; }

check_deps() {
    local missing=()
    (cd /tmp && "$PYTHON" -c "import uvicorn") 2>/dev/null || missing+=("uvicorn (pip install uvicorn[standard])")
    (PYTHONSAFEPATH=1 cd /tmp && "$PYTHON" -c "import axalon") 2>/dev/null || \
        PYTHONSAFEPATH=1 "$PYTHON" -c "import axalon" 2>/dev/null || missing+=("axalon package (pip install -e .)")

    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing dependencies:"
        for dep in "${missing[@]}"; do
            error "  ✗ $dep"
        done
        echo ""
        echo "Run: pip install -r requirements_platform.txt && pip install -e ."
        exit 1
    fi
}

check_model() {
    if [ ! -f "${REPO_ROOT}/ml/checkpoints/best.pt" ]; then
        error "Model not found at ml/checkpoints/best.pt"
        exit 1
    fi
}

setup_env() {
    info "Installing ML deps..."
    "$PYTHON" -m pip install -r "${REPO_ROOT}/ml/requirements.txt"
    info "Installing platform deps..."
    "$PYTHON" -m pip install -r "${REPO_ROOT}/requirements_platform.txt"
    info "Installing axalon package..."
    "$PYTHON" -m pip install -e "${REPO_ROOT}"
    success "Setup complete."
}

doctor() {
    info "Python: $("$PYTHON" --version)"
    check_deps
    check_model
    success "All checks passed."
}

start_api() {
    if [ -f "$API_PID_FILE" ] && kill -0 "$(cat "$API_PID_FILE")" 2>/dev/null; then
        warn "API already running (PID $(cat "$API_PID_FILE"))"
        return
    fi
    info "Starting FastAPI on http://${HOST}:${PORT} ..."
    # Run from /tmp to prevent the local platform/ directory from shadowing
    # stdlib's 'platform' module (which uuid, uvicorn/websockets, etc. depend on).
    # PYTHONSAFEPATH=1 alone is insufficient because uvicorn loads websockets lazily
    # after startup; the CWD must not contain a 'platform/' entry in sys.path.
    nohup bash -c "cd /tmp && exec env PYTHONSAFEPATH=1 '$PYTHON' -m uvicorn axalon.api.app:app \
        --host '$HOST' --port '$PORT' --reload" \
        > "${REPO_ROOT}/logs/api.log" 2>&1 &
    echo $! > "$API_PID_FILE"
    sleep 1
    if kill -0 "$(cat "$API_PID_FILE")" 2>/dev/null; then
        success "API started (PID $(cat "$API_PID_FILE")) → http://localhost:${PORT}/docs"
    else
        error "API failed to start. Check logs/api.log"
        exit 1
    fi
}

start_platform() {
    if [ -f "$PLATFORM_PID_FILE" ] && kill -0 "$(cat "$PLATFORM_PID_FILE")" 2>/dev/null; then
        warn "Platform UI already running (PID $(cat "$PLATFORM_PID_FILE"))"
        return
    fi
    if [ ! -d "$PLATFORM_DIR" ]; then
        error "Platform UI directory not found: $PLATFORM_DIR"
        exit 1
    fi
    if ! command -v npm >/dev/null 2>&1; then
        error "npm not found — install Node.js to run the platform UI"
        exit 1
    fi
    if [ ! -d "$PLATFORM_DIR/node_modules" ]; then
        info "Installing Next.js dependencies (first run)..."
        (cd "$PLATFORM_DIR" && npm install) || { error "npm install failed"; exit 1; }
    fi
    info "Starting Next.js platform UI on http://${HOST}:${PLATFORM_PORT} ..."
    nohup setsid bash -c "cd '$PLATFORM_DIR' && exec npm run dev -- --hostname '$HOST' --port '$PLATFORM_PORT'" \
        > "${REPO_ROOT}/logs/platform.log" 2>&1 &
    echo $! > "$PLATFORM_PID_FILE"
    sleep 2
    if kill -0 "$(cat "$PLATFORM_PID_FILE")" 2>/dev/null; then
        success "Platform UI started (PID $(cat "$PLATFORM_PID_FILE")) → http://localhost:${PLATFORM_PORT}/platform"
    else
        error "Platform UI failed to start. Check logs/platform.log"
        exit 1
    fi
}

stop_platform() {
    if [ -f "$PLATFORM_PID_FILE" ]; then
        local pid
        pid=$(cat "$PLATFORM_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
            success "Platform UI stopped (PID $pid)"
        else
            warn "Platform UI was not running"
        fi
        rm -f "$PLATFORM_PID_FILE"
    else
        warn "Platform UI PID file not found"
    fi
}

stop_service() {
    local pid_file="$1"
    local name="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            success "$name stopped (PID $pid)"
        else
            warn "$name was not running"
        fi
        rm -f "$pid_file"
    else
        warn "$name PID file not found"
    fi
}

show_status() {
    echo -e "\n${BOLD}Axalon Platform Status${RESET}"
    echo "────────────────────────────"

    if [ -f "$API_PID_FILE" ] && kill -0 "$(cat "$API_PID_FILE")" 2>/dev/null; then
        echo -e "  API         ${GREEN}● running${RESET}  PID $(cat "$API_PID_FILE")  →  http://localhost:${PORT}"
    else
        echo -e "  API         ${RED}○ stopped${RESET}"
    fi

    if [ -f "$PLATFORM_PID_FILE" ] && kill -0 "$(cat "$PLATFORM_PID_FILE")" 2>/dev/null; then
        echo -e "  Platform UI ${GREEN}● running${RESET}  PID $(cat "$PLATFORM_PID_FILE")  →  http://localhost:${PLATFORM_PORT}/platform"
    else
        echo -e "  Platform UI ${RED}○ stopped${RESET}"
    fi
    echo ""
}

show_help() {
    echo -e "\n${BOLD}Axalon Solar Inspection Platform${RESET}"
    echo ""
    echo "Usage: ./run.sh <command>"
    echo ""
    echo -e "  ${CYAN}setup${RESET}     Install ML + platform deps"
    echo -e "  ${CYAN}doctor${RESET}    Check Python, deps, and model"
    echo -e "  ${CYAN}api${RESET}       Start FastAPI on :${PORT}"
    echo -e "  ${CYAN}platform${RESET}  Start Next.js platform UI on :${PLATFORM_PORT}"
    echo -e "  ${CYAN}all${RESET}       Start API (background) + platform UI (foreground)"
    echo -e "  ${CYAN}stop${RESET}      Stop all running services"
    echo -e "  ${CYAN}status${RESET}    Show running service status"
    echo ""
    echo "Environment variables:"
    echo "  PORT=8000          API port"
    echo "  PLATFORM_PORT=3000 Platform UI port"
    echo "  DEVICE=0           Inference device (0=GPU, cpu=CPU)"
    echo "  HOST=0.0.0.0       Bind address"
    echo ""
    echo "Logs:  logs/api.log  |  logs/platform.log"
    echo ""
}

mkdir -p "${REPO_ROOT}/logs"

COMMAND="${1:-help}"

case "$COMMAND" in
    setup)
        setup_env
        ;;
    doctor)
        doctor
        ;;
    api)
        check_deps
        check_model
        start_api
        tail -f "${REPO_ROOT}/logs/api.log"
        ;;
    platform)
        start_platform
        tail -f "${REPO_ROOT}/logs/platform.log"
        ;;
    all)
        check_deps
        check_model
        start_api
        info "API running in background. Starting platform UI..."
        info "  API          → http://localhost:${PORT}/docs"
        info "  Platform UI  → http://localhost:${PLATFORM_PORT}/platform"
        start_platform
        tail -f "${REPO_ROOT}/logs/platform.log"
        ;;
    stop)
        stop_service "$API_PID_FILE" "API"
        stop_platform
        ;;
    status)
        show_status
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac

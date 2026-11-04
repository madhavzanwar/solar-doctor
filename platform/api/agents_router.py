"""
agents_router.py — FastAPI router for Axalon Agent Console.

Endpoints:
    GET  /agents/sessions                         List all agent sessions
    GET  /agents/sessions/{id}/log                SSE stream of a session log
    POST /agents/run                              Spawn a new agent task
    DELETE /agents/sessions/{id}                  Kill a running agent
    GET  /agents/models                           List available Ollama models
    GET  /agents/types                            List agent type definitions
    GET  /agents/plan                             Get plan board state
    POST /agents/plan/run-next                    Run the next pending plan task
    POST /agents/plan/toggle-auto                 Toggle auto-run mode on/off
    POST /agents/plan/{task_id}/reset             Reset a task to pending
    POST /agents/plan/{task_id}/done              Manually mark a task done
    POST /agents/pipeline                         Start a 6-phase pipeline run
    GET  /agents/pipelines                        List all pipeline runs
    GET  /agents/pipeline/{id}                    Get pipeline state (live-synced)
    GET  /agents/pipeline/phases/definitions      Return phase definitions
    POST /agents/pipeline/{id}/phase/{p}/rerun    Re-run a specific phase
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

REPO_ROOT    = Path(__file__).parents[2]
LOGS_DIR     = REPO_ROOT / "logs" / "agent"
AGENT_SCRIPT = REPO_ROOT / "axalon_agent.py"
PLANS_DIR    = REPO_ROOT / "docs" / "plans"
PLAN_STATE   = PLANS_DIR / "plan-state.json"
SIDECAR_EXT  = ".session.json"

router = APIRouter(prefix="/agents", tags=["agents"])

# Lock protects plan-state.json reads/writes
_plan_lock = threading.Lock()


# ── Plan state helpers ────────────────────────────────────────────────────────

def _read_plan() -> dict:
    with _plan_lock:
        try:
            return json.loads(PLAN_STATE.read_text())
        except (OSError, json.JSONDecodeError):
            return {"auto_run": False, "current_session_id": None, "tasks": []}


def _write_plan(state: dict) -> None:
    with _plan_lock:
        PLAN_STATE.write_text(json.dumps(state, indent=2))


def _task_by_id(state: dict, task_id: str) -> dict | None:
    return next((t for t in state["tasks"] if t["id"] == task_id), None)


def _next_pending(state: dict) -> dict | None:
    return next((t for t in state["tasks"] if t["status"] == "pending"), None)


# ── Session helpers ───────────────────────────────────────────────────────────

def _sidecar_path(session_id: str) -> Path:
    return LOGS_DIR / f"{session_id}{SIDECAR_EXT}"


def _log_path(session_id: str) -> Path:
    return LOGS_DIR / f"{session_id}.md"


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _session_status(session_id: str) -> str:
    sidecar = _sidecar_path(session_id)
    log = _log_path(session_id)

    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text())
            pid = meta.get("pid")
            if pid and _is_alive(int(pid)):
                return "running"
        except (ValueError, KeyError):
            pass

    if log.exists():
        content = log.read_text(errors="replace")
        if "Action: done" in content or "✓" in content:
            return "done"
        if "⚠ Hit limit" in content:
            return "limit"
        if log.stat().st_size > 100:
            return "stopped"

    return "unknown"


def _parse_sessions() -> list[dict]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for log in sorted(LOGS_DIR.glob("*.md"), reverse=True)[:50]:
        session_id = log.stem
        sidecar = _sidecar_path(session_id)
        meta: dict = {}
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text())
            except (ValueError, KeyError):
                pass

        stat = log.stat()
        sessions.append({
            "id": session_id,
            "status": _session_status(session_id),
            "model": meta.get("model", "unknown"),
            "task": meta.get("task", ""),
            "started_at": meta.get("started_at", datetime.fromtimestamp(stat.st_mtime).isoformat()),
            "size_bytes": stat.st_size,
        })
    return sessions


def _spawn_plan_task(task: dict, model: str = "qwen2.5-coder:7b") -> str:
    """Spawn agent for a plan task. Returns session_id."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{ts}_{task['id']}"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    plan_file = PLANS_DIR / task["file"]
    task_prompt = (
        f"Execute the improvement plan in docs/plans/{task['file']} "
        f"(full content in your context). "
        f"Work through every step. Run tests after each significant change. "
        f"When complete, output Action: done."
    )

    cmd = [
        "python3", str(AGENT_SCRIPT),
        "--task", task_prompt,
        "--model", model,
        "--session-id", session_id,
        "--yes",
    ]
    if plan_file.exists():
        # Pass the plan file path; agent reads it via its plan-aware code path
        cmd = [
            "python3", str(AGENT_SCRIPT),
            task["id"],
            "--model", model,
            "--session-id", session_id,
            "--yes",
        ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    _sidecar_path(session_id).write_text(json.dumps({
        "pid": proc.pid,
        "model": model,
        "task": task["name"],
        "plan_task_id": task["id"],
        "started_at": datetime.now().isoformat(),
    }))

    return session_id


# ── Auto-run background watcher ───────────────────────────────────────────────

_auto_watcher_running = False


async def _auto_run_watcher() -> None:
    """Background task: when auto_run is on and the current session finishes,
    automatically start the next pending plan task."""
    global _auto_watcher_running
    _auto_watcher_running = True
    try:
        while True:
            await asyncio.sleep(10)
            state = _read_plan()
            if not state.get("auto_run"):
                continue

            current_sid = state.get("current_session_id")
            if current_sid:
                status = _session_status(current_sid)
                if status == "running":
                    continue
                # Current task finished — mark it done in plan
                for task in state["tasks"]:
                    if task.get("session_id") == current_sid and task["status"] == "running":
                        task["status"] = "done" if status == "done" else "failed"
                        task["completed_at"] = datetime.now().isoformat()
                state["current_session_id"] = None
                _write_plan(state)

            # Start next pending task if auto_run still on
            state = _read_plan()
            if not state.get("auto_run"):
                continue

            next_task = _next_pending(state)
            if not next_task:
                # All done — turn off auto_run
                state["auto_run"] = False
                _write_plan(state)
                continue

            session_id = _spawn_plan_task(next_task)
            next_task["status"] = "running"
            next_task["session_id"] = session_id
            next_task["started_at"] = datetime.now().isoformat()
            state["current_session_id"] = session_id
            _write_plan(state)
    finally:
        _auto_watcher_running = False


def _ensure_watcher(background_tasks: BackgroundTasks) -> None:
    if not _auto_watcher_running:
        background_tasks.add_task(_auto_run_watcher)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions():
    return _parse_sessions()


@router.get("/sessions/{session_id}/log")
async def stream_log(session_id: str):
    if not all(c.isalnum() or c in "-_" for c in session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id")

    log = _log_path(session_id)
    if not log.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    async def _generate() -> AsyncIterator[str]:
        offset = 0
        idle_ticks = 0

        while True:
            try:
                text = log.read_text(errors="replace")
            except OSError:
                break

            chunk = text[offset:]
            if chunk:
                idle_ticks = 0
                for line in chunk.splitlines(keepends=True):
                    yield f"data: {json.dumps(line)}\n\n"
                offset = len(text)
            else:
                idle_ticks += 1

            status = _session_status(session_id)
            if status != "running" and idle_ticks > 4:
                yield f"event: done\ndata: {json.dumps({'status': status})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/types")
def list_agent_types():
    types_file = REPO_ROOT / "docs" / "agents" / "agent-types.json"
    if not types_file.exists():
        return []
    try:
        return json.loads(types_file.read_text())
    except Exception:
        return []


class RunRequest(BaseModel):
    task: str
    model: str = "qwen2.5-coder:7b"
    agent_type: str = "coder"
    auto_yes: bool = True


@router.post("/run")
def run_agent(req: RunRequest):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{ts}_{req.agent_type}"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3", str(AGENT_SCRIPT),
        "--task", req.task,
        "--model", req.model,
        "--agent-type", req.agent_type,
        "--session-id", session_id,
    ]
    if req.auto_yes:
        cmd.append("--yes")

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    _sidecar_path(session_id).write_text(json.dumps({
        "pid": proc.pid,
        "model": req.model,
        "task": req.task,
        "started_at": datetime.now().isoformat(),
    }))

    return {"session_id": session_id, "pid": proc.pid, "status": "running"}


@router.delete("/sessions/{session_id}")
def kill_session(session_id: str):
    if not all(c.isalnum() or c in "-_" for c in session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id")

    sidecar = _sidecar_path(session_id)
    if not sidecar.exists():
        raise HTTPException(status_code=404, detail="Session not found or already stopped")

    try:
        meta = json.loads(sidecar.read_text())
        pid = int(meta["pid"])
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Cannot read PID from session")

    if _is_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    sidecar.unlink(missing_ok=True)

    # If this was the current plan task, clear it
    state = _read_plan()
    if state.get("current_session_id") == session_id:
        for task in state["tasks"]:
            if task.get("session_id") == session_id:
                task["status"] = "stopped"
                task["completed_at"] = datetime.now().isoformat()
        state["current_session_id"] = None
        _write_plan(state)

    return {"session_id": session_id, "killed": True}


@router.get("/models")
def list_models():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as resp:
            data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        return {"models": models, "ollama": "online"}
    except Exception:
        return {"models": [], "ollama": "offline"}


# ── Plan routes ───────────────────────────────────────────────────────────────

@router.get("/plan")
def get_plan():
    """Return plan board state, refreshing any running task statuses."""
    state = _read_plan()
    # Sync running task statuses from actual session state
    for task in state["tasks"]:
        if task["status"] == "running" and task.get("session_id"):
            live = _session_status(task["session_id"])
            if live in ("done", "limit", "stopped", "unknown") and live != "running":
                task["status"] = "done" if live == "done" else "failed"
                task["completed_at"] = datetime.now().isoformat()
                if state.get("current_session_id") == task["session_id"]:
                    state["current_session_id"] = None
    _write_plan(state)
    return state


class RunNextRequest(BaseModel):
    model: str = "qwen2.5-coder:7b"


@router.post("/plan/run-next")
def run_next(req: RunNextRequest, background_tasks: BackgroundTasks):
    state = _read_plan()

    # Don't start if something is already running
    if state.get("current_session_id"):
        live = _session_status(state["current_session_id"])
        if live == "running":
            raise HTTPException(status_code=409, detail="A task is already running")

    next_task = _next_pending(state)
    if not next_task:
        raise HTTPException(status_code=404, detail="No pending tasks")

    session_id = _spawn_plan_task(next_task, req.model)
    next_task["status"] = "running"
    next_task["session_id"] = session_id
    next_task["started_at"] = datetime.now().isoformat()
    state["current_session_id"] = session_id
    _write_plan(state)

    _ensure_watcher(background_tasks)
    return {"session_id": session_id, "task_id": next_task["id"]}


@router.post("/plan/toggle-auto")
def toggle_auto(background_tasks: BackgroundTasks):
    state = _read_plan()
    state["auto_run"] = not state.get("auto_run", False)
    _write_plan(state)

    if state["auto_run"]:
        _ensure_watcher(background_tasks)

    return {"auto_run": state["auto_run"]}


@router.post("/plan/{task_id}/reset")
def reset_task(task_id: str):
    state = _read_plan()
    task = _task_by_id(state, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task["status"] = "pending"
    task["session_id"] = None
    task["started_at"] = None
    task["completed_at"] = None
    _write_plan(state)
    return task


@router.post("/plan/{task_id}/done")
def mark_done(task_id: str):
    state = _read_plan()
    task = _task_by_id(state, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task["status"] = "done"
    task["completed_at"] = datetime.now().isoformat()
    _write_plan(state)
    return task


# ── Pipeline ──────────────────────────────────────────────────────────────────

PIPELINES_DIR   = REPO_ROOT / "docs" / "pipelines"
_pipeline_lock  = threading.Lock()
_pipeline_watcher_running = False

PIPELINE_PHASES: list[dict] = [
    {"id": "think",     "name": "Think",     "icon": "🧠", "color": "#d2a8ff", "agent_type": "coder",    "description": "Analyse problem and codebase"},
    {"id": "plan",      "name": "Plan",       "icon": "📋", "color": "#d29922", "agent_type": "planner",  "description": "Create step-by-step implementation plan"},
    {"id": "implement", "name": "Implement",  "icon": "⚡", "color": "#00d4b8", "agent_type": "coder",    "description": "Execute the plan and write code"},
    {"id": "review",    "name": "Review",     "icon": "🔍", "color": "#f0883e", "agent_type": "reviewer", "description": "Review changes and flag issues"},
    {"id": "test",      "name": "Test",       "icon": "🧪", "color": "#3fb950", "agent_type": "tester",   "description": "Write and run tests, target 80% coverage"},
    {"id": "refine",    "name": "Refine",     "icon": "✨", "color": "#58a6ff", "agent_type": "coder",    "description": "Fix issues found in review and tests"},
]


def _read_pipeline(pipeline_id: str) -> dict | None:
    path = PIPELINES_DIR / f"{pipeline_id}.json"
    with _pipeline_lock:
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None


def _write_pipeline(state: dict) -> None:
    PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
    path = PIPELINES_DIR / f"{state['id']}.json"
    with _pipeline_lock:
        path.write_text(json.dumps(state, indent=2))


def _list_pipelines() -> list[dict]:
    PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(PIPELINES_DIR.glob("*.json"), reverse=True)[:20]:
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            pass
    return out


def _extract_phase_output(session_id: str, max_chars: int = 4000) -> str:
    """Pull the most useful text from a finished phase log."""
    log = _log_path(session_id)
    if not log.exists():
        return ""
    content = log.read_text(errors="replace")
    # Prefer the Thought block immediately before the final Action: done
    done_idx = content.rfind("Action: done")
    if done_idx > 0:
        thought_idx = content.rfind("Thought:", 0, done_idx)
        if thought_idx > 0:
            chunk = content[thought_idx: done_idx + 200].strip()
            return chunk[-max_chars:]
    return content[-max_chars:].strip()


def _build_phase_task(pipeline: dict, phase: dict) -> str:
    task     = pipeline["task"]
    phase_id = phase["id"]
    outputs: dict[str, str] = {}
    for p in pipeline["phases"]:
        if p["status"] == "done" and p.get("session_id"):
            outputs[p["id"]] = _extract_phase_output(p["session_id"])

    if phase_id == "think":
        return (
            f"TASK: {task}\n\n"
            "Your role: ANALYSIS ONLY — do NOT write any code.\n"
            "1. Read CLAUDE.md and relevant source files.\n"
            "2. Map the current state of the codebase relevant to this task.\n"
            "3. Identify key files, functions, and dependencies.\n"
            "4. Evaluate possible approaches and trade-offs.\n"
            "5. Write a clear markdown analysis covering: current state, key files, "
            "recommended approach, risks.\nThen call Action: done."
        )
    if phase_id == "plan":
        return (
            f"ORIGINAL TASK: {task}\n\n"
            f"ANALYSIS:\n{outputs.get('think', '(not available)')}\n\n"
            "Your role: PLANNING ONLY — do NOT write any code.\n"
            "Create a sequenced implementation plan:\n"
            "- Numbered steps, each naming exact files and specific changes\n"
            "- Effort per step (Small/Medium/Large)\n"
            "- Dependencies between steps\n"
            "Write the complete plan, then call Action: done."
        )
    if phase_id == "implement":
        return (
            f"ORIGINAL TASK: {task}\n\n"
            f"ANALYSIS:\n{outputs.get('think', '')}\n\n"
            f"PLAN:\n{outputs.get('plan', '')}\n\n"
            "Your role: IMPLEMENTATION. Execute every step of the plan.\n"
            "- Read files before editing\n"
            "- Follow CLAUDE.md patterns exactly\n"
            "- Run tests after significant changes\n"
            "When all steps done, call Action: done."
        )
    if phase_id == "review":
        return (
            f"ORIGINAL TASK: {task}\n\n"
            f"IMPLEMENTATION SUMMARY:\n{outputs.get('implement', '')}\n\n"
            "Your role: CODE REVIEW — do NOT add features.\n"
            "For each issue: severity (CRITICAL/HIGH/MEDIUM/LOW), file, line, fix.\n"
            "Focus on: bugs, security, missing error handling, CLAUDE.md violations.\n"
            "Write REVIEW_REPORT.md with all findings, then call Action: done."
        )
    if phase_id == "test":
        return (
            f"ORIGINAL TASK: {task}\n\n"
            f"PLAN:\n{outputs.get('plan', '')}\n\n"
            f"REVIEW:\n{outputs.get('review', '')}\n\n"
            "Your role: TESTING — do NOT change production code.\n"
            "1. Write pytest tests in tests/backend/ (test_<module>.py)\n"
            "2. Run: python -m pytest tests/ -v\n"
            "3. Fix failures\n"
            "4. Run: python -m pytest tests/ --cov --cov-report=term-missing\n"
            "Target 80%+ coverage, then call Action: done."
        )
    if phase_id == "refine":
        return (
            f"ORIGINAL TASK: {task}\n\n"
            f"REVIEW ISSUES:\n{outputs.get('review', '')}\n\n"
            f"TEST RESULTS:\n{outputs.get('test', '')}\n\n"
            "Your role: REFINEMENT.\n"
            "1. Fix all CRITICAL and HIGH issues from review\n"
            "2. Fix any failing tests\n"
            "3. Re-run tests to confirm green\n"
            "Do NOT add new features. When done, call Action: done."
        )
    return task


def _spawn_pipeline_phase(pipeline: dict, phase: dict) -> str:
    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{ts}_{phase['id']}"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3", str(AGENT_SCRIPT),
        "--task",       _build_phase_task(pipeline, phase),
        "--model",      pipeline.get("model", "qwen2.5-coder:7b"),
        "--agent-type", phase["agent_type"],
        "--session-id", session_id,
        "--yes",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _sidecar_path(session_id).write_text(json.dumps({
        "pid":         proc.pid,
        "model":       pipeline.get("model", "qwen2.5-coder:7b"),
        "task":        f"[{phase['name']}] {pipeline['task'][:80]}",
        "pipeline_id": pipeline["id"],
        "phase_id":    phase["id"],
        "started_at":  datetime.now().isoformat(),
    }))
    return session_id


def _advance_pipeline(pipeline: dict) -> bool:
    """Check if the running phase finished; if so start the next. Returns True if state changed."""
    changed = False
    for i, phase in enumerate(pipeline["phases"]):
        if phase["status"] != "running" or not phase.get("session_id"):
            continue
        live = _session_status(phase["session_id"])
        if live == "running":
            break
        phase["status"] = "done" if live == "done" else "failed"
        phase["completed_at"] = datetime.now().isoformat()
        pipeline["current_phase"] = None
        changed = True
        if phase["status"] == "done":
            pending = [p for p in pipeline["phases"][i + 1:] if p["status"] == "pending"]
            if pending:
                nxt = pending[0]
                sid = _spawn_pipeline_phase(pipeline, nxt)
                nxt["status"]     = "running"
                nxt["session_id"] = sid
                nxt["started_at"] = datetime.now().isoformat()
                pipeline["current_phase"] = nxt["id"]
            else:
                pipeline["status"] = "done"
        else:
            pipeline["status"] = "failed"
        break
    return changed


async def _pipeline_watcher() -> None:
    global _pipeline_watcher_running
    _pipeline_watcher_running = True
    try:
        while True:
            await asyncio.sleep(5)
            for pl in _list_pipelines():
                if pl.get("status") != "running":
                    continue
                if _advance_pipeline(pl):
                    _write_pipeline(pl)
    finally:
        _pipeline_watcher_running = False


# ── Pipeline routes ───────────────────────────────────────────────────────────

@router.get("/pipeline/phases/definitions")
def get_phase_definitions():
    return PIPELINE_PHASES


@router.get("/pipelines")
def list_pipelines_route():
    return _list_pipelines()


@router.get("/pipeline/{pipeline_id}")
def get_pipeline(pipeline_id: str):
    if not all(c.isalnum() or c in "-_" for c in pipeline_id):
        raise HTTPException(status_code=400, detail="Invalid pipeline_id")
    pl = _read_pipeline(pipeline_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if _advance_pipeline(pl):
        _write_pipeline(pl)
    return pl


class PipelineRequest(BaseModel):
    task:   str
    model:  str        = "qwen2.5-coder:7b"
    phases: list[str]  = []  # empty = all 6


@router.post("/pipeline")
def start_pipeline(req: PipelineRequest, background_tasks: BackgroundTasks):
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    pipeline_id = f"pipeline_{ts}"
    ids         = set(req.phases) if req.phases else {p["id"] for p in PIPELINE_PHASES}

    phases = [
        {**p, "status": "pending", "session_id": None, "started_at": None, "completed_at": None}
        for p in PIPELINE_PHASES if p["id"] in ids
    ]
    pipeline: dict = {
        "id":            pipeline_id,
        "task":          req.task,
        "model":         req.model,
        "status":        "running",
        "current_phase": phases[0]["id"] if phases else None,
        "created_at":    datetime.now().isoformat(),
        "phases":        phases,
    }
    _write_pipeline(pipeline)

    # Kick off first phase
    first           = phases[0]
    sid             = _spawn_pipeline_phase(pipeline, first)
    first["status"]     = "running"
    first["session_id"] = sid
    first["started_at"] = datetime.now().isoformat()
    _write_pipeline(pipeline)

    if not _pipeline_watcher_running:
        background_tasks.add_task(_pipeline_watcher)

    return pipeline


@router.post("/pipeline/{pipeline_id}/phase/{phase_id}/rerun")
def rerun_phase(pipeline_id: str, phase_id: str, background_tasks: BackgroundTasks):
    if not all(c.isalnum() or c in "-_" for c in pipeline_id):
        raise HTTPException(status_code=400, detail="Invalid pipeline_id")
    pl = _read_pipeline(pipeline_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    phase = next((p for p in pl["phases"] if p["id"] == phase_id), None)
    if not phase:
        raise HTTPException(status_code=404, detail="Phase not found")

    sid                 = _spawn_pipeline_phase(pl, phase)
    phase["status"]     = "running"
    phase["session_id"] = sid
    phase["started_at"] = datetime.now().isoformat()
    phase["completed_at"] = None
    pl["status"]        = "running"
    pl["current_phase"] = phase_id
    _write_pipeline(pl)

    if not _pipeline_watcher_running:
        background_tasks.add_task(_pipeline_watcher)
    return pl

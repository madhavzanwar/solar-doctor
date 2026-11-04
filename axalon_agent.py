#!/usr/bin/env python3
"""
axalon_agent.py — Autonomous coding agent for AxalonSystems
Powered by Qwen2.5-Coder via Ollama. ReAct loop with Claude Code-style tools.

Usage:
    python3 axalon_agent.py                      # interactive prompt
    python3 axalon_agent.py plan-01              # execute plan autonomously
    python3 axalon_agent.py plan-01 --yes        # no confirmation prompts
    python3 axalon_agent.py --task "refactor X"  # one-shot task

Tools (same as Claude Code):
    read_file, write_file, str_replace, run_bash, list_dir, find_files, grep
"""

from __future__ import annotations
import argparse, json, os, re, subprocess, sys, textwrap
from datetime import datetime
from pathlib import Path
import urllib.request, urllib.error

OLLAMA_URL   = "http://127.0.0.1:11434/api/chat"
MODEL        = os.environ.get("AXALON_MODEL", "qwen2.5-coder:7b")
REPO_ROOT    = Path(__file__).parent
PLANS_DIR    = REPO_ROOT / "docs" / "plans"
AGENTS_DIR   = REPO_ROOT / "docs" / "agents"
LOGS_DIR     = REPO_ROOT / "logs" / "agent"
MAX_ITER     = 80
BASH_TIMEOUT = 120
AUTO_YES     = False
AGENT_TYPE   = "coder"

ALWAYS_READ = [REPO_ROOT / "CLAUDE.md", PLANS_DIR / "MASTER_PLAN.md"]


def _load_agent_types() -> dict:
    p = AGENTS_DIR / "agent-types.json"
    if not p.exists():
        return {}
    try:
        return {a["id"]: a for a in json.loads(p.read_text())}
    except Exception:
        return {}


def _agent_extra_prompt(agent_type_id: str) -> str:
    agent = _load_agent_types().get(agent_type_id)
    if not agent:
        return ""
    return f"\n\n--- Agent Role: {agent['name']} ---\n{agent['system_prompt_extra']}"

def _c(code, t): return f"\033[{code}m{t}\033[0m" if sys.stdout.isatty() else t
TEAL   = lambda t: _c("36", t)
GREEN  = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
RED    = lambda t: _c("31", t)
GREY   = lambda t: _c("90", t)
BOLD   = lambda t: _c("1",  t)

TOOL_DOCS = """
You are an autonomous coding agent for the AxalonSystems repository.
Use EXACTLY this format for every action:

Thought: <your reasoning>
Action: <tool_name>
Input: <JSON object>

After I run the tool I send: Observation: <result>
Continue until done, then:
Action: done
Input: {"summary": "what was done"}

Or to ask the user:
Action: ask_user
Input: {"question": "..."}

TOOLS:

read_file      {"path": "relative/path"}
               Returns file contents with line numbers. Read before editing.

write_file     {"path": "relative/path", "content": "full content"}
               Creates/overwrites a file. Prefer str_replace for existing files.

str_replace    {"path": "relative/path", "old_str": "exact text", "new_str": "replacement"}
               Replaces first occurrence. old_str must match exactly incl. whitespace.
               Read the file first to get exact text.

run_bash       {"command": "shell cmd", "timeout": 60}
               Runs in repo root. Returns stdout+stderr+exit code.

list_dir       {"path": "relative/path"}
               Lists directory contents.

find_files     {"pattern": "**/*.py", "path": "."}
               Glob search across the repo.

grep           {"pattern": "search", "path": ".", "include": "*.py"}
               Regex/text search across files.

RULES:
- Always read_file before str_replace (need exact text).
- Run tests after changes: run_bash {"command": "python3 -m pytest tests/backend/ -ra -x --tb=short"}
- Never hardcode secrets. Never cross-import website/ ↔ ml/ ↔ platform/.
- Severity/class constants come ONLY from ml/src/utils.py.
- Never git push without ask_user first.
- DO NOT use ask_user to ask "which module" or "what next" — just complete the task end-to-end autonomously.
- Only use ask_user if you genuinely cannot proceed (e.g. missing a secret or destructive action).
- After completing a task, output Action: done immediately.
"""

def build_system(extra: str = "", agent_type: str = "coder") -> str:
    parts = [TOOL_DOCS, _agent_extra_prompt(agent_type)]
    for p in ALWAYS_READ:
        if p.exists():
            parts.append(f"\n\n--- {p.name} ---\n{p.read_text()}")
    if extra:
        parts.append(f"\n\n--- Task Context ---\n{extra}")
    return "\n".join(parts)

# ── Tools ──────────────────────────────────────────────────────────────────

def t_read_file(path):
    p = REPO_ROOT / path
    if not p.exists(): return f"ERROR: not found: {path}"
    if p.stat().st_size > 400_000: return f"ERROR: file too large. Use grep."
    txt = p.read_text(errors="replace")
    lines = txt.splitlines()
    return "\n".join(f"{i+1:4d} | {l}" for i,l in enumerate(lines))

def t_write_file(path, content):
    p = REPO_ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written {len(content.splitlines())} lines to {path}"

def t_str_replace(path, old_str, new_str):
    p = REPO_ROOT / path
    if not p.exists(): return f"ERROR: not found: {path}"
    src = p.read_text()
    if old_str not in src:
        return f"ERROR: old_str not found in {path}. Read the file first to get exact text."
    n = src.count(old_str)
    if n > 1: return f"ERROR: old_str appears {n} times. Make it more specific."
    p.write_text(src.replace(old_str, new_str, 1))
    delta = len(new_str.splitlines()) - len(old_str.splitlines())
    return f"str_replace applied ({delta:+d} lines)"

def t_run_bash(command, timeout=BASH_TIMEOUT):
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True,
                           timeout=int(timeout), cwd=REPO_ROOT)
        out = r.stdout[-8000:]; err = r.stderr[-2000:]
        parts = []
        if out: parts.append(out)
        if err: parts.append(f"STDERR:\n{err}")
        parts.append(f"Exit: {r.returncode}")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: timed out after {timeout}s"

def t_list_dir(path):
    p = REPO_ROOT / path
    if not p.exists(): return f"ERROR: not found: {path}"
    items = sorted(p.iterdir())
    lines = []
    for it in items:
        if "__pycache__" in it.name: continue
        kind = "DIR " if it.is_dir() else "FILE"
        sz = f"{it.stat().st_size:>9,}B" if it.is_file() else "          "
        lines.append(f"{kind} {sz}  {it.name}")
    return "\n".join(lines)

def t_find_files(pattern, path="."):
    skip = {"__pycache__", ".next", "node_modules", ".venv", ".venv-relay"}
    matches = [
        str(m.relative_to(REPO_ROOT))
        for m in (REPO_ROOT/path).glob(pattern)
        if not any(s in str(m) for s in skip)
    ]
    if not matches: return f"No files matching '{pattern}'"
    return f"{len(matches)} files:\n" + "\n".join(sorted(matches))

def t_grep(pattern, path=".", include="*.py"):
    try:
        r = subprocess.run(["grep","-rn","--include",include, pattern, path],
                           capture_output=True, text=True, timeout=30, cwd=REPO_ROOT)
        if not r.stdout: return f"No matches for '{pattern}'"
        lines = r.stdout.splitlines()
        return f"{len(lines)} matches:\n" + "\n".join(lines[:100])
    except Exception as e:
        return f"ERROR: {e}"

TOOLS = {
    "read_file":  lambda a: t_read_file(**a),
    "write_file": lambda a: t_write_file(**a),
    "str_replace":lambda a: t_str_replace(**a),
    "run_bash":   lambda a: t_run_bash(**a),
    "list_dir":   lambda a: t_list_dir(**a),
    "find_files": lambda a: t_find_files(**a),
    "grep":       lambda a: t_grep(**a),
}

# ── Ollama ─────────────────────────────────────────────────────────────────

def chat(messages, system):
    payload = {
        "model": MODEL,
        "messages": [{"role":"system","content":system}] + messages,
        "stream": True,
        "options": {
            "temperature": 0.15,
            "num_ctx": 16384,
            "stop": ["Observation:", "\nObservation"],
        },
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data,
                                  headers={"Content-Type":"application/json"})
    resp_text = ""
    print(TEAL("▶ "), end="", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                try:
                    chunk = json.loads(raw.decode().strip())
                except: continue
                tok = chunk.get("message",{}).get("content","")
                if tok:
                    print(tok, end="", flush=True)
                    resp_text += tok
                if chunk.get("done"): break
    except urllib.error.URLError as e:
        print(RED(f"\nOllama error: {e}\nRun: ollama serve")); sys.exit(1)
    print()
    return resp_text

# ── Parser ─────────────────────────────────────────────────────────────────

def _try_json(s):
    """Try to parse JSON, with light cleanup for common model errors."""
    for candidate in [s, re.sub(r",\s*}", "}", s), re.sub(r",\s*]", "]", s)]:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
    return None

def parse_action(text):
    # Match "Action: toolname" — ignore trailing punctuation
    m = re.search(r"Action:\s*([a-zA-Z_]+)", text, re.IGNORECASE)
    if not m:
        return None
    action = m.group(1).lower()

    if action in ("done", "ask_user"):
        # Try Input: line, fall back to empty
        im = re.search(r"Input:\s*(\{.*?\})", text, re.DOTALL | re.IGNORECASE)
        args = _try_json(im.group(1)) if im else {}
        return action, (args or {})

    # 1. Prefer explicit "Input: {...}" block
    im = re.search(r"Input:\s*(\{.*?\})", text, re.DOTALL | re.IGNORECASE)
    if im:
        args = _try_json(im.group(1))
        if args is not None:
            return action, args

    # 2. Fallback: JSON on the same Action: line  e.g. "Action: list_dir {"path": "x"}"
    action_line = re.search(r"Action:\s*\w+\s*(\{.*?\})", text, re.IGNORECASE)
    if action_line:
        args = _try_json(action_line.group(1))
        if args is not None:
            return action, args

    # 3. Any JSON block in the text (last resort)
    any_json = re.findall(r"\{[^{}]+\}", text, re.DOTALL)
    for candidate in reversed(any_json):
        args = _try_json(candidate)
        if args is not None:
            return action, args

    return None

DESTRUCTIVE = [r"rm\s+-rf",r"git\s+push\s+--force",r"git\s+reset\s+--hard",r"drop\s+table"]

def is_destructive(cmd):
    return any(re.search(p, cmd, re.IGNORECASE) for p in DESTRUCTIVE)

def confirm(prompt):
    if AUTO_YES:
        print(GREY(f"  [auto-yes] {prompt}")); return True
    return input(YELLOW(f"  {prompt} [y/N] ")).strip().lower() in ("y","yes")

# ── Logger ─────────────────────────────────────────────────────────────────

class Logger:
    def __init__(self, tag, session_id: str | None = None):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if session_id:
            self.path = LOGS_DIR / f"{session_id}.md"
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.path = LOGS_DIR / f"{ts}_{tag}.md"
        self._f = self.path.open("w")
        self._f.write(f"# Agent Session — {tag}\n**Started:** {datetime.now().isoformat()}\n\n")
    def log(self, role, content):
        self._f.write(f"\n## {role}\n```\n{content}\n```\n"); self._f.flush()
    def close(self):
        self._f.write(f"\n---\n**Ended:** {datetime.now().isoformat()}\n"); self._f.close()

# ── Agent loop ──────────────────────────────────────────────────────────────

def run_agent(task, system, tag="session", session_id: str | None = None):
    log = Logger(tag, session_id=session_id)
    messages = []
    print(BOLD("\n━━━ Task ━━━"))
    print(textwrap.fill(task, 80)); print()
    messages.append({"role":"user","content":task})
    log.log("User", task)

    recent_actions: list = []  # last 3 (action, key_arg) for loop detection

    for i in range(1, MAX_ITER+1):
        print(GREY(f"\n[iter {i}/{MAX_ITER}]"))
        resp = chat(messages, system)
        messages.append({"role":"assistant","content":resp})
        log.log("Assistant", resp)

        parsed = parse_action(resp)
        if parsed is None:
            nudge = "Output your next Thought/Action/Input, or Action: done if complete."
            messages.append({"role":"user","content":nudge})
            log.log("Nudge", nudge); continue

        action, args = parsed

        if action == "done":
            summary = args.get("summary","(done)")
            print(GREEN(f"\n✓ {summary}")); log.log("Done", summary); break

        if action == "ask_user":
            q = args.get("question","?")
            print(YELLOW(f"\n? {q}"))
            if AUTO_YES:
                ans = "Do NOT ask again. Complete the original task end-to-end now and call Action: done when finished."
                print(GREY(f"  [auto-yes] {ans}"))
            else:
                ans = input("> ").strip() or "Please continue."
            obs = f"User: {ans}"
            messages.append({"role":"user","content":f"Observation: {obs}"}); continue

        if action not in TOOLS:
            obs = f"ERROR: unknown tool '{action}'. Use: {list(TOOLS)}"
            print(RED(f"  {obs}"))
            messages.append({"role":"user","content":f"Observation: {obs}"}); continue

        # Stuck-loop detection: same action+path 3 times → hard nudge
        key = (action, str(args.get("path", args.get("command", "")))[:60])
        recent_actions.append(key)
        if len(recent_actions) > 3:
            recent_actions.pop(0)
        if len(recent_actions) == 3 and len(set(recent_actions)) == 1:
            nudge = (
                "STOP. You have repeated the same action 3 times with no progress. "
                "Do NOT repeat it. Either: (a) use a DIFFERENT tool, or (b) if the task "
                "is complete, call Action: done with a summary now."
            )
            print(RED(f"  [loop-break] {nudge}"))
            messages.append({"role":"user","content":nudge})
            recent_actions.clear()
            continue

        # Show + maybe confirm
        if action == "run_bash":
            cmd = args.get("command","")
            print(TEAL(f"\n  $ {cmd}"))
            if is_destructive(cmd) and not confirm("Destructive — run?"):
                messages.append({"role":"user","content":"Observation: user declined"}); continue
            if not AUTO_YES and not confirm("Run?"):
                messages.append({"role":"user","content":"Observation: user skipped"}); continue
        elif action == "write_file":
            print(TEAL(f"\n  write → {args.get('path')}"))
            if not AUTO_YES and not confirm("Write file?"):
                messages.append({"role":"user","content":"Observation: user skipped"}); continue
        elif action == "str_replace":
            print(TEAL(f"\n  edit  → {args.get('path')}"))
        else:
            short = {k: str(v)[:50] for k,v in args.items()}
            print(TEAL(f"\n  {action}({short})"))

        try:
            obs = TOOLS[action](args)
        except TypeError as e:
            obs = f"ERROR wrong args for {action}: {e}"
        except Exception as e:
            obs = f"ERROR {action}: {e}"

        if len(obs) > 12000:
            obs = obs[:12000] + f"\n...[truncated {len(obs)} chars]"

        print(GREY(f"  → {obs[:160]}{'...' if len(obs)>160 else ''}"))
        log.log(f"Observation ({action})", obs)
        messages.append({"role":"user","content":f"Observation:\n{obs}"})
    else:
        print(YELLOW(f"\n⚠ Hit limit ({MAX_ITER} iters). Log: {log.path}"))

    log.close()
    print(GREY(f"\nLog: {log.path}"))

# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    global AUTO_YES, MODEL
    p = argparse.ArgumentParser(description="AxalonSystems autonomous coding agent")
    p.add_argument("target", nargs="?", help="plan-NN or task description")
    p.add_argument("--task", help="Task description")
    p.add_argument("--yes", action="store_true", help="Auto-approve all tool calls")
    p.add_argument("--model", default=MODEL)
    p.add_argument("--session-id", dest="session_id", help="Override log file name (used by API)")
    p.add_argument("--agent-type", dest="agent_type", default="coder",
                   help="Agent specialization: coder, reviewer, tester, ml-engineer, frontend, planner, devops")
    args = p.parse_args()
    AUTO_YES   = args.yes
    MODEL      = args.model
    AGENT_TYPE = args.agent_type

    print(BOLD(TEAL("\n╔══════════════════════════════════════════════╗")))
    print(BOLD(TEAL(f"║  AxalonSystems Agent  {MODEL:<25}║")))
    print(BOLD(TEAL("╚══════════════════════════════════════════════╝")))
    print(GREY("  Tools: read_file write_file str_replace run_bash list_dir find_files grep"))
    print(GREY("  --yes to auto-approve all tool calls"))

    extra, task, tag = "", "", "session"

    target = args.target or args.task
    if not target:
        print()
        print("  plan-01        split app.py into routers")
        print("  plan-02        add Pydantic schemas")
        print("  plan-03        implement park/locator.py")
        print("  plan-04        expand test coverage to 80%")
        print("  <free text>    any coding task")
        print()
        target = input(TEAL("> ")).strip()
        if not target: sys.exit(0)

    if target.startswith("plan-"):
        pf = PLANS_DIR / f"{target}.md"
        if not pf.exists(): print(RED(f"Not found: {pf}")); sys.exit(1)
        extra = pf.read_text()
        tag   = target
        task  = (
            f"Execute the improvement plan in docs/plans/{target}.md "
            f"(full content in your context). "
            f"Work through every step. Run tests after each significant change. "
            f"When complete, output Action: done."
        )
        print(f"\n  Plan: {pf.name}")
    else:
        task = target
        tag  = "task"

    # API can override the log filename for session tracking
    if args.session_id:
        tag = args.session_id

    run_agent(task, build_system(extra, AGENT_TYPE), tag, session_id=args.session_id if args.session_id else None)

if __name__ == "__main__":
    main()

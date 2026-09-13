"""Run eval tasks: install the scaffold into a fixture copy, invoke claude -p,
record transcripts and workdir snapshots under evals/results/<run>/."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

EVALS_DIR: Path = Path(__file__).resolve().parent
REPO_ROOT: Path = EVALS_DIR.parent
sys.path.insert(0, str(EVALS_DIR))

import transcript

TASKS_FILE: Path = EVALS_DIR / "tasks.toml"
FIXTURES_DIR: Path = EVALS_DIR / "fixtures"
WORK_ROOT: Path = EVALS_DIR / ".work"
RESULTS_ROOT: Path = EVALS_DIR / "results"
SCAFFOLD_DIR: Path = REPO_ROOT / "claude"
SNIPPET_FILE: Path = REPO_ROOT / "CLAUDE.snippet.md"
START_MARK: str = "<!-- claude-fable-orchestrator:start -->"
END_MARK: str = "<!-- claude-fable-orchestrator:end -->"
SETTINGS_NAME: str = "settings.json"
CLAUDE_MD: str = "CLAUDE.md"
DEFAULT_MODEL: str = "sonnet"
DEFAULT_TIMEOUT_S: int = 600
ASSERTION_LEVELS: frozenset[str] = frozenset({"error", "warn"})
RUN_DIR_FORMAT: str = "run-%Y%m%d-%H%M%S"
EMPTY_MCP_CONFIG: str = '{"mcpServers":{}}'
SNAPSHOT_EXCLUDES: frozenset[str] = frozenset(
    {"__pycache__", ".venv", ".pytest_cache", ".claude"}
)


@dataclass
class Assertion:
    type: str
    level: str = "error"
    path: Optional[str] = None
    pattern: Optional[str] = None
    cmd: Optional[str] = None
    paths: List[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    fixture: str
    prompt: str
    expect_flow: Optional[str] = None
    must_spawn: List[str] = field(default_factory=list)
    must_spawn_any: List[List[str]] = field(default_factory=list)
    must_not_spawn: List[str] = field(default_factory=list)
    min_spawned: int = 0
    max_spawned: Optional[int] = None
    timeout_s: Optional[int] = None
    assertions: List[Assertion] = field(default_factory=list)


@dataclass
class ClaudeResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool


def load_tasks(path: Path = TASKS_FILE) -> List[Task]:
    data: object = tomllib.loads(path.read_text(encoding="utf-8"))
    tasks: List[Task] = []
    entries = data.get("task", []) if isinstance(data, dict) else []
    for entry in entries:
        assertions: List[Assertion] = []
        for a in entry.get("assertion", []):
            level = a.get("level", "error")
            if level not in ASSERTION_LEVELS:
                raise ValueError(
                    f"task {entry['id']!r}: unknown assertion level {level!r}"
                    f" (expected one of {sorted(ASSERTION_LEVELS)})"
                )
            assertions.append(
                Assertion(
                    type=a["type"],
                    level=level,
                    path=a.get("path"),
                    pattern=a.get("pattern"),
                    cmd=a.get("cmd"),
                    paths=list(a.get("paths", [])),
                )
            )
        tasks.append(
            Task(
                id=entry["id"],
                fixture=entry["fixture"],
                prompt=entry["prompt"],
                expect_flow=entry.get("expect_flow"),
                must_spawn=list(entry.get("must_spawn", [])),
                must_spawn_any=[list(g) for g in entry.get("must_spawn_any", [])],
                must_not_spawn=list(entry.get("must_not_spawn", [])),
                min_spawned=entry.get("min_spawned", 0),
                max_spawned=entry.get("max_spawned"),
                timeout_s=entry.get("timeout_s"),
                assertions=assertions,
            )
        )
    return tasks


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_manifest(fixture_dir: Path, workdir: Path) -> Dict[str, str]:
    manifest: Dict[str, str] = {}
    for source in sorted(fixture_dir.rglob("*")):
        if not source.is_file():
            continue
        if SNAPSHOT_EXCLUDES & set(source.relative_to(fixture_dir).parts):
            continue
        rel = source.relative_to(fixture_dir)
        target = workdir / rel
        if target.is_file():
            manifest[str(rel)] = _sha256(target)
    return manifest


def prepare_workdir(task: Task, model: str) -> Path:
    fixture_dir = FIXTURES_DIR / task.fixture
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"fixture not found: {fixture_dir}")
    workdir = WORK_ROOT / task.id
    if workdir.exists():
        shutil.rmtree(workdir)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_dir, workdir)
    shutil.copytree(SCAFFOLD_DIR, workdir / ".claude")
    settings = {"model": model, "enabledPlugins": {}}
    (workdir / ".claude" / SETTINGS_NAME).write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )
    claude_md = workdir / CLAUDE_MD
    existing = claude_md.read_text(encoding="utf-8") if claude_md.is_file() else ""
    snippet = SNIPPET_FILE.read_text(encoding="utf-8")
    if START_MARK not in existing:
        block = f"{START_MARK}\n{snippet.rstrip()}\n{END_MARK}\n"
        separator = "\n" if existing.strip() else ""
        claude_md.write_text(existing + separator + block, encoding="utf-8")
    return workdir.resolve()


def _scaffold_commit() -> str:
    try:
        head = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if head.returncode != 0:
            return "unknown"
        commit = head.stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if status.returncode == 0 and status.stdout.strip():
            commit += "-dirty"
        return commit
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _claude_version() -> str:
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return version if result.returncode == 0 and version else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def run_claude(prompt: str, model: str, session_id: str, workdir: Path,
               timeout_s: int) -> ClaudeResult:
    argv = [
        "claude",
        "-p",
        "--model", model,
        "--session-id", session_id,
        "--output-format", "json",
        "--strict-mcp-config",
        "--mcp-config", EMPTY_MCP_CONFIG,
        "--dangerously-skip-permissions",
        prompt,
    ]
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            cwd=workdir,
            env=dict(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return ClaudeResult(
            returncode=127,
            stdout="",
            stderr=f"failed to launch claude: {exc}",
            duration_s=0.0,
            timed_out=False,
        )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        stdout, stderr = proc.communicate()
    return ClaudeResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
        duration_s=time.monotonic() - start,
        timed_out=timed_out,
    )


def _result_text(stdout: str) -> Optional[str]:
    try:
        data: object = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    result: object = data.get("result")
    return result if isinstance(result, str) else None


def _snapshot_workdir(workdir: Path, dest: Path) -> None:
    def ignore(directory: str, names: List[str]) -> set[str]:
        return {n for n in names if n in SNAPSHOT_EXCLUDES}

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(workdir, dest, ignore=ignore)


def _new_run_dir() -> Path:
    stamp = datetime.now().strftime(RUN_DIR_FORMAT)
    name = f"{stamp}-{uuid.uuid4().hex[:8]}"
    path = RESULTS_ROOT / name
    path.mkdir(parents=True, exist_ok=False)
    return path


def _write_record(run_dir: Path, record: Dict[str, object]) -> Path:
    path = run_dir / f"{record['id']}.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def run_task(task: Task, run_dir: Path, model: str, timeout_s: int,
             keep_work: bool) -> Dict[str, object]:
    fixture_dir = FIXTURES_DIR / task.fixture
    workdir = prepare_workdir(task, model)
    manifest = snapshot_manifest(fixture_dir, workdir)
    session_id = str(uuid.uuid4())
    task_dir = run_dir / task.id
    task_dir.mkdir(parents=True, exist_ok=True)

    result = run_claude(task.prompt, model, session_id, workdir, timeout_s)
    (task_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (task_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")

    session_file = transcript.find_session_file(
        transcript.projects_root(), session_id
    )
    parsed: Optional[transcript.SessionParse] = None
    if session_file is not None:
        parsed = transcript.parse_session(session_file)

    snapshot_rel = f"{task.id}/workdir"
    _snapshot_workdir(workdir, task_dir / "workdir")
    if not keep_work:
        shutil.rmtree(workdir, ignore_errors=True)

    record: Dict[str, object] = {
        "id": task.id,
        "prompt": task.prompt,
        "model": model,
        "session_id": session_id,
        "claude_version": _claude_version(),
        "scaffold_commit": _scaffold_commit(),
        "returncode": result.returncode,
        "duration_s": round(result.duration_s, 2),
        "timed_out": result.timed_out,
        "result_text": _result_text(result.stdout),
        "workdir_snapshot": snapshot_rel,
        "manifest": manifest,
        "session_file": str(session_file) if session_file else None,
        "transcript": parsed.to_dict() if parsed else None,
    }
    _write_record(run_dir, record)
    return record


def _list_tasks(tasks: List[Task]) -> None:
    for task in tasks:
        flow = task.expect_flow or "auto"
        print(f"{task.id:<18} fixture={task.fixture:<12} flow={flow:<9} {task.prompt[:60]}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run orchestrator eval tasks against claude -p."
    )
    which = parser.add_mutually_exclusive_group()
    which.add_argument(
        "--task", action="append", default=[], metavar="ID",
        help="task id to run (repeatable)",
    )
    which.add_argument("--all", action="store_true", help="run every task")
    parser.add_argument("--list", action="store_true", help="list tasks and exit")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"session model (default {DEFAULT_MODEL}; fable quota may be exhausted)",
    )
    parser.add_argument(
        "--timeout", type=int, default=None, metavar="SECONDS",
        help=f"per-task timeout override (default {DEFAULT_TIMEOUT_S} or task timeout_s)",
    )
    parser.add_argument(
        "--into", metavar="RUN_DIR",
        help="merge results into an existing run dir, overwriting per-task records",
    )
    parser.add_argument(
        "--keep-work", action="store_true",
        help=f"keep {WORK_ROOT.name}/ workdirs after the run",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    tasks = load_tasks()
    if args.list:
        _list_tasks(tasks)
        return 0
    selected: List[Task] = []
    if args.all:
        selected = tasks
    elif args.task:
        by_id = {task.id: task for task in tasks}
        for task_id in args.task:
            if task_id not in by_id:
                print(f"error: unknown task {task_id!r}", file=sys.stderr)
                return 2
            selected.append(by_id[task_id])
    if not selected:
        print("error: pass --task ID or --all (see --list)", file=sys.stderr)
        return 2

    if args.into:
        run_dir = Path(args.into)
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = _new_run_dir()
    print(f"run dir: {run_dir}")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    failures = 0
    for task in selected:
        timeout_s = (
            args.timeout
            if args.timeout is not None
            else task.timeout_s or DEFAULT_TIMEOUT_S
        )
        print(f"[{task.id}] fixture={task.fixture} model={args.model} "
              f"timeout={timeout_s}s")
        try:
            record = run_task(task, run_dir, args.model, timeout_s,
                              args.keep_work)
        except FileNotFoundError as exc:
            print(f"  error: {exc}", file=sys.stderr)
            failures += 1
            continue
        spawned = []
        stored = record.get("transcript")
        if isinstance(stored, dict):
            parsed = transcript.SessionParse.from_dict(stored)
            spawned = parsed.spawned_roles
        print(f"  rc={record['returncode']} timed_out={record['timed_out']} "
              f"duration={record['duration_s']}s spawned={spawned}")
        if record["timed_out"] or record["returncode"] != 0:
            failures += 1
    if not args.keep_work:
        shutil.rmtree(WORK_ROOT, ignore_errors=True)
    print(f"records: {run_dir}  (grade with: python3 evals/grade.py {run_dir})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

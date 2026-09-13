"""Grade eval run records deterministically against tasks.toml expectations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

EVALS_DIR: Path = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS_DIR))

import transcript
from run_evals import Assertion, Task, load_tasks

RESULTS_ROOT: Path = EVALS_DIR / "results"
LEVEL_ERROR: str = "error"
LEVEL_WARN: str = "warn"
TESTS_PASS_TIMEOUT_S: int = 120
STATUS_PASS: str = "PASS"
STATUS_WARN: str = "WARN"
STATUS_FAIL: str = "FAIL"


@dataclass
class Check:
    name: str
    level: str
    ok: bool
    detail: str = ""


@dataclass
class TaskGrade:
    task_id: str
    checks: List[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(not c.ok and c.level == LEVEL_ERROR for c in self.checks):
            return STATUS_FAIL
        if any(not c.ok for c in self.checks):
            return STATUS_WARN
        return STATUS_PASS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_record(path: Path) -> Optional[Dict[str, object]]:
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_transcript(record: Dict[str, object]) -> Optional[transcript.SessionParse]:
    stored: object = record.get("transcript")
    if isinstance(stored, dict):
        return transcript.SessionParse.from_dict(stored)
    session_file: object = record.get("session_file")
    if isinstance(session_file, str):
        path = Path(session_file)
        if path.is_file():
            return transcript.parse_session(path)
    return None


def _roles_detail(parsed: Optional[transcript.SessionParse]) -> str:
    if parsed is None:
        return "no session transcript"
    roles = parsed.spawned_roles
    return f"spawned={roles or 'none'}"


def _spawn_checks(task: Task, parsed: Optional[transcript.SessionParse],
                  grade: TaskGrade) -> None:
    roles = parsed.normalized_roles if parsed else []
    for role in task.must_spawn:
        want = transcript.normalize_role(role)
        grade.checks.append(
            Check(
                name=f"must_spawn:{role}",
                level=LEVEL_ERROR,
                ok=want in roles,
                detail=_roles_detail(parsed),
            )
        )
    for group in task.must_spawn_any:
        wanted = {transcript.normalize_role(r) for r in group}
        grade.checks.append(
            Check(
                name=f"must_spawn_any:{'|'.join(group)}",
                level=LEVEL_ERROR,
                ok=bool(wanted & set(roles)),
                detail=_roles_detail(parsed),
            )
        )
    for role in task.must_not_spawn:
        want = transcript.normalize_role(role)
        grade.checks.append(
            Check(
                name=f"must_not_spawn:{role}",
                level=LEVEL_ERROR,
                ok=want not in roles,
                detail=_roles_detail(parsed),
            )
        )
    if task.min_spawned:
        count = len(parsed.spawned) if parsed else 0
        grade.checks.append(
            Check(
                name=f"min_spawned:{task.min_spawned}",
                level=LEVEL_ERROR,
                ok=count >= task.min_spawned,
                detail=f"spawned={count}",
            )
        )
    if task.max_spawned is not None:
        count = len(parsed.spawned) if parsed else 0
        grade.checks.append(
            Check(
                name=f"max_spawned:{task.max_spawned}",
                level=LEVEL_WARN,
                ok=count <= task.max_spawned,
                detail=f"spawned={count}",
            )
        )


def _flow_checks(task: Task, parsed: Optional[transcript.SessionParse],
                 grade: TaskGrade) -> None:
    observed = parsed.flow_observed if parsed else None
    source = parsed.flow_source if parsed else None
    if task.expect_flow is None:
        detail = f"observed={observed or 'none'}"
        if source:
            detail += f" via {source}"
        grade.checks.append(
            Check(name="flow:observed", level=LEVEL_WARN, ok=True, detail=detail)
        )
        return
    if observed is None:
        grade.checks.append(
            Check(
                name=f"expect_flow:{task.expect_flow}",
                level=LEVEL_WARN,
                ok=False,
                detail="unobserved",
            )
        )
        return
    grade.checks.append(
        Check(
            name=f"expect_flow:{task.expect_flow}",
            level=LEVEL_ERROR,
            ok=observed == task.expect_flow,
            detail=f"observed={observed} via {source}",
        )
    )


def _snapshot_dir(run_dir: Path, record: Dict[str, object]) -> Optional[Path]:
    rel: object = record.get("workdir_snapshot")
    if not isinstance(rel, str):
        return None
    path = run_dir / rel
    return path if path.is_dir() else None


def _check_file_exists(snapshot: Optional[Path], assertion: Assertion) -> Check:
    name = f"file_exists:{assertion.path}"
    if snapshot is None or assertion.path is None:
        return Check(name, assertion.level, False, "no workdir snapshot")
    target = snapshot / assertion.path
    return Check(name, assertion.level, target.is_file(),
                 "" if target.is_file() else "missing")


def _check_file_contains(snapshot: Optional[Path], assertion: Assertion) -> Check:
    name = f"file_contains:{assertion.path}"
    if snapshot is None or assertion.path is None or assertion.pattern is None:
        return Check(name, assertion.level, False, "no workdir snapshot")
    target = snapshot / assertion.path
    if not target.is_file():
        return Check(name, assertion.level, False, "missing")
    try:
        found = re.search(assertion.pattern, target.read_text(encoding="utf-8"))
    except (OSError, re.error) as exc:
        return Check(name, assertion.level, False, str(exc))
    return Check(name, assertion.level, found is not None,
                 "" if found else f"pattern {assertion.pattern!r} not found")


def _check_output_contains(record: Dict[str, object],
                           assertion: Assertion) -> Check:
    name = f"output_contains:{assertion.pattern}"
    result_text: object = record.get("result_text")
    if not isinstance(result_text, str) or assertion.pattern is None:
        return Check(name, assertion.level, False, "no result text")
    try:
        found = re.search(assertion.pattern, result_text)
    except re.error as exc:
        return Check(name, assertion.level, False, str(exc))
    return Check(name, assertion.level, found is not None,
                 "" if found else "pattern not found in result")


def _check_tests_pass(snapshot: Optional[Path], assertion: Assertion) -> Check:
    name = f"tests_pass:{assertion.cmd}"
    if snapshot is None or not assertion.cmd:
        return Check(name, assertion.level, False, "no workdir snapshot")
    try:
        proc = subprocess.run(
            shlex.split(assertion.cmd),
            cwd=snapshot,
            capture_output=True,
            text=True,
            timeout=TESTS_PASS_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, assertion.level, False, str(exc))
    detail = "" if proc.returncode == 0 else (
        proc.stderr.strip().splitlines() or proc.stdout.strip().splitlines() or [""]
    )[-1][:200]
    return Check(name, assertion.level, proc.returncode == 0, detail)


def _check_files_unchanged(snapshot: Optional[Path], record: Dict[str, object],
                           assertion: Assertion) -> List[Check]:
    manifest: object = record.get("manifest")
    checks: List[Check] = []
    for rel in assertion.paths:
        name = f"files_unchanged:{rel}"
        if snapshot is None or not isinstance(manifest, dict):
            checks.append(Check(name, assertion.level, False,
                                "no workdir snapshot or manifest"))
            continue
        target = snapshot / rel
        expected = manifest.get(rel)
        if not target.is_file():
            checks.append(Check(name, assertion.level, False, "missing"))
        elif not isinstance(expected, str):
            checks.append(Check(name, assertion.level, False,
                                "not in pre-run manifest"))
        else:
            actual = _sha256(target)
            checks.append(Check(name, assertion.level, actual == expected,
                                "" if actual == expected else "hash changed"))
    return checks


def _assertion_checks(task: Task, record: Dict[str, object],
                      run_dir: Path, grade: TaskGrade) -> None:
    snapshot = _snapshot_dir(run_dir, record)
    for assertion in task.assertions:
        if assertion.type == "file_exists":
            grade.checks.append(_check_file_exists(snapshot, assertion))
        elif assertion.type == "file_contains":
            grade.checks.append(_check_file_contains(snapshot, assertion))
        elif assertion.type == "output_contains":
            grade.checks.append(_check_output_contains(record, assertion))
        elif assertion.type == "tests_pass":
            grade.checks.append(_check_tests_pass(snapshot, assertion))
        elif assertion.type == "files_unchanged":
            grade.checks.extend(
                _check_files_unchanged(snapshot, record, assertion)
            )
        else:
            grade.checks.append(
                Check(f"assertion:{assertion.type}", assertion.level, False,
                      "unknown assertion type")
            )


def grade_record(task: Task, record: Dict[str, object],
                 run_dir: Path) -> TaskGrade:
    grade = TaskGrade(task_id=task.id)
    timed_out = record.get("timed_out") is True
    returncode = record.get("returncode")
    grade.checks.append(
        Check(
            name="run_completed",
            level=LEVEL_ERROR,
            ok=not timed_out and returncode == 0,
            detail=f"rc={returncode} timed_out={timed_out}",
        )
    )
    parsed = _parse_transcript(record)
    _spawn_checks(task, parsed, grade)
    _flow_checks(task, parsed, grade)
    _assertion_checks(task, record, run_dir, grade)
    return grade


def _latest_run_dir() -> Optional[Path]:
    if not RESULTS_ROOT.is_dir():
        return None
    runs = [p for p in RESULTS_ROOT.iterdir() if p.is_dir()]
    if not runs:
        return None
    return max(runs, key=lambda p: p.stat().st_mtime)


def _record_files(run_dir: Path) -> List[Path]:
    return sorted(p for p in run_dir.glob("*.json") if p.is_file())


def _print_grade(grade: TaskGrade) -> None:
    print(f"{grade.task_id:<20} {grade.status}")
    for check in grade.checks:
        mark = "ok" if check.ok else check.level.upper()
        line = f"  {check.level:<5} {mark:<5} {check.name}"
        if check.detail:
            line += f"  — {check.detail}"
        print(line)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Grade eval run records against tasks.toml."
    )
    parser.add_argument(
        "run_dir", nargs="?", metavar="RUN_DIR",
        help="run dir under evals/results/ (or use --latest)",
    )
    parser.add_argument(
        "--latest", action="store_true", help="grade the newest run dir",
    )
    parser.add_argument(
        "--task", action="append", default=[], metavar="ID",
        help="grade only these task ids (repeatable)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.latest and args.run_dir:
        parser.error("RUN_DIR and --latest are mutually exclusive")
    run_dir: Optional[Path] = None
    if args.latest:
        run_dir = _latest_run_dir()
        if run_dir is None:
            print(f"error: no run dirs under {RESULTS_ROOT}", file=sys.stderr)
            return 2
    elif args.run_dir:
        run_dir = Path(args.run_dir)
    if run_dir is None or not run_dir.is_dir():
        print("error: pass a run dir path or --latest", file=sys.stderr)
        return 2

    tasks = {task.id: task for task in load_tasks()}
    grades: List[TaskGrade] = []
    for record_path in _record_files(run_dir):
        record = _load_record(record_path)
        if record is None:
            print(f"warn: unreadable record {record_path}", file=sys.stderr)
            continue
        task_id = str(record.get("id", record_path.stem))
        if args.task and task_id not in args.task:
            continue
        task = tasks.get(task_id)
        if task is None:
            print(f"warn: no task spec for {task_id!r}", file=sys.stderr)
            continue
        grades.append(grade_record(task, record, run_dir))

    if not grades:
        print(f"no gradable records in {run_dir}")
        return 0
    print(f"run: {run_dir}")
    for grade in grades:
        _print_grade(grade)
    counts = {STATUS_PASS: 0, STATUS_WARN: 0, STATUS_FAIL: 0}
    for grade in grades:
        counts[grade.status] += 1
    print(
        f"summary: {counts[STATUS_PASS]} PASS, {counts[STATUS_WARN]} WARN, "
        f"{counts[STATUS_FAIL]} FAIL of {len(grades)}"
    )
    return 1 if counts[STATUS_FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())

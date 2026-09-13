#!/usr/bin/env python3
"""Report token usage from Claude Code session transcripts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

DEFAULT_DIR: Path = Path.home() / ".claude" / "projects"
SESSION_GLOB: str = "*.jsonl"
INPUT_TOKENS: str = "input_tokens"
OUTPUT_TOKENS: str = "output_tokens"
CACHE_CREATION_TOKENS: str = "cache_creation_input_tokens"
CACHE_READ_TOKENS: str = "cache_read_input_tokens"
TOKEN_FIELDS: Tuple[str, ...] = (
    INPUT_TOKENS,
    OUTPUT_TOKENS,
    CACHE_CREATION_TOKENS,
    CACHE_READ_TOKENS,
)
COLUMN_HEADERS: Tuple[str, ...] = ("input", "output", "cache_write", "cache_read", "total")
MAIN_LANE: str = "main"
SIDECHAIN_LANE: str = "sidechain"
UNKNOWN_MODEL: str = "unknown"
DATE_FORMAT: str = "%Y-%m-%d"
TIME_FORMAT: str = "%Y-%m-%d %H:%M"
STAMP_WIDTH: int = 16
NUM_WIDTH: int = 12
EMPTY_MESSAGE: str = "No matching session transcripts found."


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    def add(self, other: "UsageTotals") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens


@dataclass
class ParsedEntry:
    model: str
    is_sidechain: bool
    usage: UsageTotals


def _empty_lanes() -> Dict[str, UsageTotals]:
    return {MAIN_LANE: UsageTotals(), SIDECHAIN_LANE: UsageTotals()}


@dataclass
class SessionUsage:
    project: str
    session_id: str
    path: Path
    mtime: float
    message_count: int = 0
    totals: UsageTotals = field(default_factory=UsageTotals)
    lanes: Dict[str, UsageTotals] = field(default_factory=_empty_lanes)
    by_model: Dict[str, UsageTotals] = field(default_factory=dict)


def load_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _token_count(usage: Dict[object, object], key: str) -> int:
    value: object = usage.get(key)
    return value if isinstance(value, int) else 0


def _totals_from_usage(usage: Dict[object, object]) -> UsageTotals:
    return UsageTotals(
        input_tokens=_token_count(usage, INPUT_TOKENS),
        output_tokens=_token_count(usage, OUTPUT_TOKENS),
        cache_creation_input_tokens=_token_count(usage, CACHE_CREATION_TOKENS),
        cache_read_input_tokens=_token_count(usage, CACHE_READ_TOKENS),
    )


def parse_entry(line: str) -> Optional[ParsedEntry]:
    try:
        data: object = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    message: object = data.get("message")
    if not isinstance(message, dict):
        return None
    usage: object = message.get("usage")
    if not isinstance(usage, dict):
        return None
    model: object = message.get("model")
    return ParsedEntry(
        model=model if isinstance(model, str) else UNKNOWN_MODEL,
        is_sidechain=data.get("isSidechain") is True,
        usage=_totals_from_usage(usage),
    )


def aggregate_session(path: Path) -> SessionUsage:
    session = SessionUsage(
        project=path.parent.name,
        session_id=path.stem,
        path=path,
        mtime=_mtime(path),
    )
    for line in load_lines(path):
        entry = parse_entry(line)
        if entry is None:
            continue
        session.message_count += 1
        session.totals.add(entry.usage)
        lane = SIDECHAIN_LANE if entry.is_sidechain else MAIN_LANE
        session.lanes[lane].add(entry.usage)
        session.by_model.setdefault(entry.model, UsageTotals()).add(entry.usage)
    return session


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _file_date(path: Path) -> Optional[date]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None


def scan_sessions(
    root: Path,
    date_filter: Optional[date] = None,
    project_filter: Optional[str] = None,
) -> List[Path]:
    if not root.is_dir():
        return []
    try:
        candidates = [p for p in root.rglob(SESSION_GLOB) if p.is_file()]
    except OSError:
        return []
    paths: List[Path] = []
    for path in candidates:
        if project_filter is not None and project_filter not in path.parent.name:
            continue
        if date_filter is not None and _file_date(path) != date_filter:
            continue
        paths.append(path)
    return sorted(paths, key=_mtime)


def _column_header(title: str, width: int) -> str:
    return f"  {title:<{width}}" + "".join(
        f"{label:>{NUM_WIDTH}}" for label in COLUMN_HEADERS
    )


def _usage_row(label: str, width: int, usage: UsageTotals) -> str:
    values = (
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_creation_input_tokens,
        usage.cache_read_input_tokens,
        usage.total,
    )
    return f"  {label:<{width}}" + "".join(f"{v:>{NUM_WIDTH},}" for v in values)


def _usage_block(title: str, rows: List[Tuple[str, UsageTotals]]) -> List[str]:
    if not rows:
        return []
    width = max([len(title)] + [len(label) for label, _ in rows])
    lines = [_column_header(title, width)]
    lines.extend(_usage_row(label, width, usage) for label, usage in rows)
    lines.append("")
    return lines


def _sorted_models(by_model: Dict[str, UsageTotals]) -> List[Tuple[str, UsageTotals]]:
    return sorted(by_model.items(), key=lambda item: item[1].total, reverse=True)


def _lane_rows(lanes: Dict[str, UsageTotals]) -> List[Tuple[str, UsageTotals]]:
    return [
        (MAIN_LANE, lanes[MAIN_LANE]),
        (SIDECHAIN_LANE, lanes[SIDECHAIN_LANE]),
    ]


def _format_session(session: SessionUsage) -> List[str]:
    stamp = (
        datetime.fromtimestamp(session.mtime).strftime(TIME_FORMAT)
        if session.mtime > 0
        else "-"
    )
    lines = [
        f"session {session.session_id}  project={session.project}  "
        f"modified={stamp}  messages={session.message_count}"
    ]
    lines.extend(_usage_block("model", _sorted_models(session.by_model)))
    lines.extend(_usage_block("lane", _lane_rows(session.lanes)))
    return lines


def _combine(sessions: List[SessionUsage]) -> SessionUsage:
    combined = SessionUsage(
        project="*", session_id="TOTAL", path=Path(), mtime=0.0
    )
    for session in sessions:
        combined.message_count += session.message_count
        combined.totals.add(session.totals)
        for lane, usage in session.lanes.items():
            combined.lanes[lane].add(usage)
        for model, usage in session.by_model.items():
            combined.by_model.setdefault(model, UsageTotals()).add(usage)
    return combined


def _format_total(sessions: List[SessionUsage]) -> List[str]:
    combined = _combine(sessions)
    lines = [f"TOTAL  sessions={len(sessions)}  messages={combined.message_count}"]
    lines.extend(_usage_block("model", _sorted_models(combined.by_model)))
    lines.extend(_usage_block("lane", _lane_rows(combined.lanes)))
    return lines


def format_report(sessions: List[SessionUsage]) -> str:
    if not sessions:
        return EMPTY_MESSAGE
    lines: List[str] = []
    for session in sessions:
        lines.extend(_format_session(session))
    if len(sessions) > 1:
        lines.extend(_format_total(sessions))
    return "\n".join(lines).rstrip()


def format_listing(sessions: List[SessionUsage]) -> str:
    if not sessions:
        return EMPTY_MESSAGE
    rows = sorted(sessions, key=lambda s: s.mtime)
    project_width = max(len("project"), max(len(s.project) for s in rows))
    session_width = max(len("session"), max(len(s.session_id) for s in rows))
    lines = [
        f"{'project':<{project_width}}  {'session':<{session_width}}  "
        f"{'modified':<{STAMP_WIDTH}}  {'tokens':>{NUM_WIDTH}}"
    ]
    for session in rows:
        stamp = datetime.fromtimestamp(session.mtime).strftime(TIME_FORMAT)
        lines.append(
            f"{session.project:<{project_width}}  "
            f"{session.session_id:<{session_width}}  "
            f"{stamp:<{STAMP_WIDTH}}  "
            f"{session.totals.total:>{NUM_WIDTH},}"
        )
    return "\n".join(lines)


def _parse_date(
    value: Optional[str], parser: argparse.ArgumentParser
) -> Optional[date]:
    if value is None:
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        parser.error(f"--date must be YYYY-MM-DD, got {value!r}")
        return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report token usage from Claude Code JSONL transcripts."
    )
    parser.add_argument(
        "--dir",
        default=str(DEFAULT_DIR),
        metavar="PATH",
        help="transcript root (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list session files instead of a usage report",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="restrict to the most recently modified session",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="only sessions modified on this date",
    )
    parser.add_argument(
        "--project",
        metavar="SUBSTR",
        help="only project dirs containing this substring",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    date_filter = _parse_date(args.date, parser)
    paths = scan_sessions(
        Path(args.dir).expanduser(),
        date_filter=date_filter,
        project_filter=args.project,
    )
    if args.latest and paths:
        paths = [max(paths, key=_mtime)]
    sessions = [aggregate_session(path) for path in paths]
    if args.list:
        print(format_listing(sessions))
    else:
        print(format_report(sessions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

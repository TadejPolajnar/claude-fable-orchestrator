"""Locate and parse Claude Code session transcripts for eval grading."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

DEFAULT_PROJECTS_ROOT: Path = Path.home() / ".claude" / "projects"
SUBAGENTS_DIR: str = "subagents"
SUBAGENT_GLOB: str = "agent-*.jsonl"
META_SUFFIX: str = ".meta.json"
AGENT_TYPE_FIELD: str = "agentType"
DEFAULT_ROLE: str = "subagent"
UNKNOWN_MODEL: str = "unknown"
SKILL_TOOL: str = "Skill"
SKILL_NAME: str = "orchestrator"
FLOW_NAMES: Tuple[str, ...] = ("quick", "standard", "full", "debug", "research")
FLOW_SOURCE_SKILL_ARGS: str = "skill-args"
FLOW_SOURCE_TEXT: str = "text"
FLOW_PATH_RE: str = r"flows/({})\.md"
FLOW_PHRASE_RE: str = r"the `?({})`? flow"

ROLE_ALIASES: Dict[str, str] = {
    "Explore": "explorer",
    "explore": "explorer",
    "general-purpose": "worker",
}


def normalize_role(role: str) -> str:
    return ROLE_ALIASES.get(role, role)


def projects_root() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / "projects"
    return DEFAULT_PROJECTS_ROOT


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

    def to_dict(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "UsageTotals":
        def count(key: str) -> int:
            value: object = data.get(key)
            return value if isinstance(value, int) else 0

        return cls(
            input_tokens=count("input_tokens"),
            output_tokens=count("output_tokens"),
            cache_creation_input_tokens=count("cache_creation_input_tokens"),
            cache_read_input_tokens=count("cache_read_input_tokens"),
        )


@dataclass
class SubagentInfo:
    role: str
    model: str
    usage: UsageTotals
    path: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "role": self.role,
            "model": self.model,
            "usage": self.usage.to_dict(),
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SubagentInfo":
        usage: object = data.get("usage")
        return cls(
            role=str(data.get("role", DEFAULT_ROLE)),
            model=str(data.get("model", UNKNOWN_MODEL)),
            usage=UsageTotals.from_dict(usage if isinstance(usage, dict) else {}),
            path=str(data.get("path", "")),
        )


@dataclass
class SessionParse:
    path: Path
    spawned: List[SubagentInfo] = field(default_factory=list)
    skill_invoked: bool = False
    flow_observed: Optional[str] = None
    flow_source: Optional[str] = None
    main_model: Optional[str] = None
    main_usage: UsageTotals = field(default_factory=UsageTotals)

    @property
    def spawned_roles(self) -> List[str]:
        return [agent.role for agent in self.spawned]

    @property
    def normalized_roles(self) -> List[str]:
        return [normalize_role(role) for role in self.spawned_roles]

    @property
    def total_usage(self) -> UsageTotals:
        total = UsageTotals()
        total.add(self.main_usage)
        for agent in self.spawned:
            total.add(agent.usage)
        return total

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "spawned": [agent.to_dict() for agent in self.spawned],
            "skill_invoked": self.skill_invoked,
            "flow_observed": self.flow_observed,
            "flow_source": self.flow_source,
            "main_model": self.main_model,
            "main_usage": self.main_usage.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SessionParse":
        spawned_raw: object = data.get("spawned")
        spawned = [
            SubagentInfo.from_dict(item)
            for item in (spawned_raw if isinstance(spawned_raw, list) else [])
            if isinstance(item, dict)
        ]
        main_usage: object = data.get("main_usage")
        flow_observed: object = data.get("flow_observed")
        flow_source: object = data.get("flow_source")
        main_model: object = data.get("main_model")
        return cls(
            path=Path(str(data.get("path", ""))),
            spawned=spawned,
            skill_invoked=data.get("skill_invoked") is True,
            flow_observed=flow_observed if isinstance(flow_observed, str) else None,
            flow_source=flow_source if isinstance(flow_source, str) else None,
            main_model=main_model if isinstance(main_model, str) else None,
            main_usage=UsageTotals.from_dict(
                main_usage if isinstance(main_usage, dict) else {}
            ),
        )


def find_session_file(projects_root: Path, session_id: str) -> Optional[Path]:
    if not projects_root.is_dir():
        return None
    try:
        matches = [
            path
            for path in projects_root.glob(f"*/{session_id}.jsonl")
            if path.is_file()
        ]
    except OSError:
        return None
    if not matches:
        return None
    return max(matches, key=_mtime)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _iter_entries(path: Path) -> Iterator[Dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            data: object = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            yield data


def _usage_of(entry: Dict[str, object]) -> Optional[UsageTotals]:
    message: object = entry.get("message")
    if not isinstance(message, dict):
        return None
    usage: object = message.get("usage")
    if not isinstance(usage, dict):
        return None
    return UsageTotals.from_dict(usage)


def _model_of(entry: Dict[str, object]) -> Optional[str]:
    message: object = entry.get("message")
    if not isinstance(message, dict):
        return None
    model: object = message.get("model")
    return model if isinstance(model, str) else None


def _content_blocks(entry: Dict[str, object]) -> List[Dict[str, object]]:
    if entry.get("type") != "assistant":
        return []
    message: object = entry.get("message")
    if not isinstance(message, dict):
        return []
    content: object = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _first_flow(text: str, patterns: List[re.Pattern[str]]) -> Optional[str]:
    best: Optional[re.Match[str]] = None
    for pattern in patterns:
        match = pattern.search(text)
        if match is not None and (best is None or match.start() < best.start()):
            best = match
    if best is None:
        return None
    return best.group(1)


def _flow_patterns(template: str) -> List[re.Pattern[str]]:
    names = "|".join(FLOW_NAMES)
    return [re.compile(template.format(names))]


FLOW_WORD_RE: re.Pattern[str] = re.compile(
    r"\b({})\b".format("|".join(FLOW_NAMES))
)


def _skill_arg_flow(block: Dict[str, object]) -> Optional[str]:
    tool_input: object = block.get("input")
    if not isinstance(tool_input, dict):
        return None
    if tool_input.get("skill") != SKILL_NAME:
        return None
    args: object = tool_input.get("args")
    if not isinstance(args, str):
        return None
    match = FLOW_WORD_RE.search(args)
    if match is None:
        return None
    return match.group(1)


def _subagent_role(agent_path: Path) -> str:
    meta_path = agent_path.with_suffix(META_SUFFIX)
    try:
        data: object = json.loads(
            meta_path.read_text(encoding="utf-8", errors="replace")
        )
    except (OSError, ValueError):
        return DEFAULT_ROLE
    if not isinstance(data, dict):
        return DEFAULT_ROLE
    role: object = data.get(AGENT_TYPE_FIELD)
    if isinstance(role, str) and role:
        return role
    return DEFAULT_ROLE


def _parse_subagent(agent_path: Path) -> SubagentInfo:
    role = _subagent_role(agent_path)
    model = UNKNOWN_MODEL
    usage = UsageTotals()
    for entry in _iter_entries(agent_path):
        entry_usage = _usage_of(entry)
        if entry_usage is not None:
            usage.add(entry_usage)
            if model == UNKNOWN_MODEL:
                entry_model = _model_of(entry)
                if entry_model is not None:
                    model = entry_model
    return SubagentInfo(role=role, model=model, usage=usage, path=str(agent_path))


def _scan_main(session: SessionParse, path: Path) -> None:
    flow_path_re = _flow_patterns(FLOW_PATH_RE)
    flow_phrase_re = _flow_patterns(FLOW_PHRASE_RE)
    skill_arg_flow: Optional[str] = None
    text_flow: Optional[str] = None
    for entry in _iter_entries(path):
        if entry.get("isSidechain") is True:
            continue
        usage = _usage_of(entry)
        if usage is not None:
            session.main_usage.add(usage)
            if session.main_model is None:
                session.main_model = _model_of(entry)
        for block in _content_blocks(entry):
            block_type = block.get("type")
            if block_type == "tool_use" and block.get("name") == SKILL_TOOL:
                flow = _skill_arg_flow(block)
                tool_input = block.get("input")
                if isinstance(tool_input, dict) and tool_input.get("skill") == SKILL_NAME:
                    session.skill_invoked = True
                    if skill_arg_flow is None:
                        skill_arg_flow = flow
            elif block_type == "text" and text_flow is None:
                text: object = block.get("text")
                if isinstance(text, str):
                    text_flow = _first_flow(text, flow_path_re) or _first_flow(
                        text, flow_phrase_re
                    )
    if skill_arg_flow is not None:
        session.flow_observed = skill_arg_flow
        session.flow_source = FLOW_SOURCE_SKILL_ARGS
    elif text_flow is not None:
        session.flow_observed = text_flow
        session.flow_source = FLOW_SOURCE_TEXT


def parse_session(path: Path) -> SessionParse:
    session = SessionParse(path=path)
    _scan_main(session, path)
    subagents_dir = path.parent / path.stem / SUBAGENTS_DIR
    if subagents_dir.is_dir():
        try:
            agent_files = sorted(
                p for p in subagents_dir.glob(SUBAGENT_GLOB) if p.is_file()
            )
        except OSError:
            agent_files = []
        for agent_path in agent_files:
            session.spawned.append(_parse_subagent(agent_path))
    return session

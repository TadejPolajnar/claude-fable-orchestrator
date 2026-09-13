"""Tests for evals/transcript.py."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

import transcript

MODEL_ROOT: str = "claude-sonnet-5"
MODEL_AGENT: str = "claude-opus-5"


def _usage(input_tokens: int = 1, output_tokens: int = 2) -> Dict[str, int]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": 3,
        "cache_read_input_tokens": 4,
    }


def _assistant_line(
    model: str,
    content: Optional[List[Dict[str, object]]] = None,
    usage: Optional[Dict[str, int]] = None,
    sidechain: bool = False,
) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "isSidechain": sidechain,
            "message": {
                "role": "assistant",
                "model": model,
                "content": content or [{"type": "text", "text": "ok"}],
                "usage": usage or _usage(),
            },
        }
    )


def _skill_block(args: str, skill: str = "orchestrator") -> Dict[str, object]:
    return {
        "type": "tool_use",
        "name": "Skill",
        "input": {"skill": skill, "args": args},
    }


def _text_block(text: str) -> Dict[str, object]:
    return {"type": "text", "text": text}


def _write_session(root: Path, project: str, session_id: str,
                   lines: List[str]) -> Path:
    directory = root / project
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_subagent(root: Path, project: str, session_id: str, name: str,
                    lines: List[str],
                    meta: Optional[Dict[str, object]] = None) -> Path:
    directory = root / project / session_id / "subagents"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if meta is not None:
        path.with_suffix(".meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
    return path


def test_find_session_file_locates_by_uuid(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path, "-some-project", "abc-123",
        [_assistant_line(MODEL_ROOT)],
    )
    _write_session(tmp_path, "-other", "def-456", [_assistant_line(MODEL_ROOT)])

    found = transcript.find_session_file(tmp_path, "abc-123")
    assert found == session
    assert transcript.find_session_file(tmp_path, "missing-id") is None
    assert transcript.find_session_file(tmp_path / "nope", "abc-123") is None


def test_parse_session_roles_models_tokens(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path,
        "proj",
        "s1",
        [
            _assistant_line(MODEL_ROOT, usage=_usage(10, 20)),
            _assistant_line(MODEL_ROOT, usage=_usage(1, 1)),
        ],
    )
    _write_subagent(
        tmp_path, "proj", "s1", "agent-aaa",
        [
            _assistant_line(MODEL_AGENT, usage=_usage(5, 6)),
            _assistant_line(MODEL_AGENT, usage=_usage(7, 8)),
        ],
        meta={"agentType": "tester"},
    )
    _write_subagent(
        tmp_path, "proj", "s1", "agent-bbb",
        [_assistant_line(MODEL_AGENT, usage=_usage(2, 2))],
        meta={"agentType": "worker"},
    )

    parsed = transcript.parse_session(session)
    assert parsed.main_model == MODEL_ROOT
    assert parsed.main_usage.input_tokens == 11
    assert parsed.main_usage.output_tokens == 21
    assert parsed.spawned_roles == ["tester", "worker"]
    assert parsed.spawned[0].model == MODEL_AGENT
    assert parsed.spawned[0].usage.input_tokens == 12
    assert parsed.spawned[0].usage.cache_read_input_tokens == 8
    assert parsed.total_usage.input_tokens == 11 + 12 + 2


def test_parse_session_meta_fallback_and_aliases(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path, "proj", "s1", [_assistant_line(MODEL_ROOT)]
    )
    _write_subagent(
        tmp_path, "proj", "s1", "agent-aaa",
        [_assistant_line(MODEL_AGENT)],
    )
    _write_subagent(
        tmp_path, "proj", "s1", "agent-bbb",
        [_assistant_line(MODEL_AGENT)],
        meta={"agentType": "general-purpose"},
    )
    _write_subagent(
        tmp_path, "proj", "s1", "agent-ccc",
        [_assistant_line(MODEL_AGENT)],
        meta={"agentType": "Explore"},
    )

    parsed = transcript.parse_session(session)
    assert parsed.spawned_roles == ["subagent", "general-purpose", "Explore"]
    assert parsed.normalized_roles == ["subagent", "worker", "explorer"]
    assert transcript.normalize_role("explore") == "explorer"
    assert transcript.normalize_role("worker") == "worker"


def test_skill_invoked_and_flow_from_skill_args(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path,
        "proj",
        "s1",
        [
            _assistant_line(MODEL_ROOT, [_text_block("thinking")]),
            _assistant_line(
                MODEL_ROOT,
                [_skill_block("debug flow: trace the crash in average()")],
            ),
            _assistant_line(MODEL_ROOT, [_text_block("done")]),
        ],
    )

    parsed = transcript.parse_session(session)
    assert parsed.skill_invoked is True
    assert parsed.flow_observed == "debug"
    assert parsed.flow_source == "skill-args"


def test_flow_from_text_when_skill_args_silent(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path,
        "proj",
        "s1",
        [
            _assistant_line(MODEL_ROOT, [_skill_block("")]),
            _assistant_line(
                MODEL_ROOT,
                [_text_block("I'll use the `standard` flow for this.")],
            ),
        ],
    )

    parsed = transcript.parse_session(session)
    assert parsed.skill_invoked is True
    assert parsed.flow_observed == "standard"
    assert parsed.flow_source == "text"


def test_flow_from_flows_path_in_text(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path,
        "proj",
        "s1",
        [
            _assistant_line(
                MODEL_ROOT,
                [_text_block("Loading flows/research.md for this audit.")],
            ),
        ],
    )

    parsed = transcript.parse_session(session)
    assert parsed.skill_invoked is False
    assert parsed.flow_observed == "research"
    assert parsed.flow_source == "text"


def test_no_skill_no_flow(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path,
        "proj",
        "s1",
        [
            _assistant_line(
                MODEL_ROOT,
                [_text_block("I fixed the typo directly.")],
            ),
        ],
    )

    parsed = transcript.parse_session(session)
    assert parsed.skill_invoked is False
    assert parsed.flow_observed is None
    assert parsed.flow_source is None
    assert parsed.spawned == []


def test_skill_args_first_flow_word_wins(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path,
        "proj",
        "s1",
        [
            _assistant_line(
                MODEL_ROOT,
                [_skill_block("not a flow name here")],
            ),
            _assistant_line(
                MODEL_ROOT,
                [_skill_block("full flow: then maybe a quick check")],
            ),
        ],
    )

    parsed = transcript.parse_session(session)
    assert parsed.skill_invoked is True
    assert parsed.flow_observed == "full"
    assert parsed.flow_source == "skill-args"


def test_malformed_lines_and_missing_dirs(tmp_path: Path) -> None:
    session = _write_session(
        tmp_path,
        "proj",
        "s1",
        [
            "{not json",
            "",
            json.dumps({"type": "summary", "summary": "x"}),
            _assistant_line(MODEL_ROOT, usage=_usage(4, 4)),
        ],
    )

    parsed = transcript.parse_session(session)
    assert parsed.main_usage.input_tokens == 4
    assert parsed.spawned == []

    empty = _write_session(tmp_path, "proj2", "s2", [])
    parsed2 = transcript.parse_session(empty)
    assert parsed2.main_usage.total == 0
    assert parsed2.main_model is None

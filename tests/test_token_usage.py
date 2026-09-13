"""Tests for scripts/token_usage.py."""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import token_usage

MODEL_OPUS: str = "claude-opus-4-8"
MODEL_FABLE: str = "claude-fable-5"


def _assistant_line(
    model: str, usage: Dict[str, int], sidechain: bool = False
) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "isSidechain": sidechain,
            "message": {"role": "assistant", "model": model, "usage": usage},
        }
    )


def _write_session(
    root: Path, project: str, name: str, lines: List[str], mtime: datetime
) -> Path:
    directory = root / project
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stamp = mtime.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _write_subagent(
    root: Path,
    project: str,
    session: str,
    name: str,
    lines: List[str],
    meta: Optional[Dict[str, object]] = None,
    mtime: Optional[datetime] = None,
) -> Path:
    directory = root / project / session / "subagents"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if meta is not None:
        path.with_suffix(".meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
    if mtime is not None:
        stamp = mtime.timestamp()
        os.utime(path, (stamp, stamp))
    return path


def test_parse_entry_reads_usage_and_skips_non_usage_lines() -> None:
    usage = {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_creation_input_tokens": 2,
        "cache_read_input_tokens": 3,
    }
    entry = token_usage.parse_entry(_assistant_line(MODEL_OPUS, usage))
    assert entry is not None
    assert entry.model == MODEL_OPUS
    assert entry.is_sidechain is False
    assert entry.usage.input_tokens == 10
    assert entry.usage.total == 20

    sidechain = token_usage.parse_entry(
        _assistant_line(MODEL_OPUS, usage, sidechain=True)
    )
    assert sidechain is not None
    assert sidechain.is_sidechain is True

    no_usage = json.dumps({"type": "user", "message": {"role": "user"}})
    no_message = json.dumps({"type": "summary", "summary": "x"})
    not_object = json.dumps([1, 2, 3])
    assert token_usage.parse_entry(no_usage) is None
    assert token_usage.parse_entry(no_message) is None
    assert token_usage.parse_entry(not_object) is None


def test_aggregate_sessions_exact_totals(tmp_path: Path) -> None:
    first = _write_session(
        tmp_path,
        "proj-a",
        "s1",
        [
            _assistant_line(
                MODEL_OPUS,
                {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 40,
                },
            ),
            _assistant_line(
                MODEL_FABLE,
                {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "cache_creation_input_tokens": 3,
                    "cache_read_input_tokens": 4,
                },
                sidechain=True,
            ),
        ],
        datetime(2026, 1, 1, 12, 0, 0),
    )
    second = _write_session(
        tmp_path,
        "proj-a",
        "s2",
        [
            _assistant_line(
                MODEL_FABLE,
                {
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 300,
                    "cache_read_input_tokens": 400,
                },
            )
        ],
        datetime(2026, 1, 2, 12, 0, 0),
    )

    one = token_usage.aggregate_session(first)
    assert one.message_count == 2
    assert one.totals.input_tokens == 11
    assert one.totals.output_tokens == 22
    assert one.totals.cache_creation_input_tokens == 33
    assert one.totals.cache_read_input_tokens == 44
    assert one.totals.total == 110
    assert one.lanes[token_usage.MAIN_LANE].total == 100
    assert one.lanes[token_usage.SIDECHAIN_LANE].total == 10
    assert one.by_model[MODEL_OPUS].total == 100
    assert one.by_model[MODEL_FABLE].total == 10

    two = token_usage.aggregate_session(second)
    assert two.message_count == 1
    assert two.totals.total == 1000
    assert two.lanes[token_usage.MAIN_LANE].total == 1000
    assert two.lanes[token_usage.SIDECHAIN_LANE].total == 0
    assert two.by_model[MODEL_FABLE].output_tokens == 200


def test_date_filter_excludes_other_mtimes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    day = datetime(2026, 1, 10, 9, 0, 0)
    _write_session(
        tmp_path,
        "proj",
        "on-date",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        day,
    )
    _write_session(
        tmp_path,
        "proj",
        "off-date",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        day + timedelta(days=1),
    )

    found = token_usage.scan_sessions(tmp_path, date_filter=day.date())
    assert [path.stem for path in found] == ["on-date"]

    exit_code = token_usage.main(
        ["--dir", str(tmp_path), "--date", day.strftime("%Y-%m-%d")]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "on-date" in out
    assert "off-date" not in out


def test_malformed_lines_do_not_crash(tmp_path: Path) -> None:
    path = _write_session(
        tmp_path,
        "proj",
        "mixed",
        [
            "{not json",
            "",
            "   ",
            json.dumps({"message": "scalar"}),
            _assistant_line(MODEL_OPUS, {"input_tokens": 7, "output_tokens": 3}),
            '{"message": {"usage": "oops"}}',
        ],
        datetime(2026, 1, 1, 0, 0, 0),
    )
    session = token_usage.aggregate_session(path)
    assert session.message_count == 1
    assert session.totals.total == 10


def test_empty_dir_reports_gracefully(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = token_usage.main(["--dir", str(tmp_path)])
    assert exit_code == 0
    assert token_usage.EMPTY_MESSAGE in capsys.readouterr().out

    exit_code = token_usage.main(["--dir", str(tmp_path), "--list"])
    assert exit_code == 0
    assert token_usage.EMPTY_MESSAGE in capsys.readouterr().out


def test_subagent_usage_rolls_into_parent_session(tmp_path: Path) -> None:
    stamp = datetime(2026, 1, 1, 12, 0, 0)
    session_path = _write_session(
        tmp_path,
        "proj-a",
        "s1",
        [
            _assistant_line(
                MODEL_OPUS,
                {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 40,
                },
            )
        ],
        stamp,
    )
    _write_subagent(
        tmp_path,
        "proj-a",
        "s1",
        "agent-aaa",
        [
            _assistant_line(
                MODEL_FABLE,
                {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "cache_creation_input_tokens": 3,
                    "cache_read_input_tokens": 4,
                },
            )
        ],
        meta={"agentType": "tester"},
    )

    session = token_usage.aggregate_session(session_path)
    assert session.subagent_count == 1
    assert session.message_count == 2
    assert session.totals.total == 110
    assert session.lanes[token_usage.MAIN_LANE].total == 100
    assert session.lanes[token_usage.SIDECHAIN_LANE].total == 10
    assert session.by_model[MODEL_OPUS].total == 100
    assert session.by_model[MODEL_FABLE].total == 10
    assert session.by_role["tester"].total == 10


def test_scan_sessions_skips_nested_subagent_files(tmp_path: Path) -> None:
    stamp = datetime(2026, 1, 1, 12, 0, 0)
    session_path = _write_session(
        tmp_path,
        "proj-a",
        "s1",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        stamp,
    )
    _write_subagent(
        tmp_path,
        "proj-a",
        "s1",
        "agent-aaa",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 2})],
    )
    _write_subagent(
        tmp_path,
        "proj-a",
        "orphan",
        "agent-bbb",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 3})],
    )

    found = token_usage.scan_sessions(tmp_path)
    assert found == [session_path]


def test_missing_or_bad_meta_falls_back_to_subagent_role(
    tmp_path: Path,
) -> None:
    stamp = datetime(2026, 1, 1, 12, 0, 0)
    session_path = _write_session(
        tmp_path,
        "proj-a",
        "s1",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        stamp,
    )
    _write_subagent(
        tmp_path,
        "proj-a",
        "s1",
        "agent-nometa",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 2, "output_tokens": 3})],
    )
    bad = _write_subagent(
        tmp_path,
        "proj-a",
        "s1",
        "agent-badmeta",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 5})],
    )
    bad.with_suffix(".meta.json").write_text("{not json", encoding="utf-8")

    session = token_usage.aggregate_session(session_path)
    assert session.subagent_count == 2
    assert session.by_role == {
        token_usage.DEFAULT_ROLE: session.by_role[token_usage.DEFAULT_ROLE]
    }
    assert session.by_role[token_usage.DEFAULT_ROLE].total == 10
    assert session.lanes[token_usage.SIDECHAIN_LANE].total == 10


def test_role_block_in_report_sorted_by_total(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stamp = datetime(2026, 1, 1, 12, 0, 0)
    _write_session(
        tmp_path,
        "proj-a",
        "s1",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        stamp,
    )
    _write_subagent(
        tmp_path,
        "proj-a",
        "s1",
        "agent-aaa",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 10})],
        meta={"agentType": "tester"},
    )
    _write_subagent(
        tmp_path,
        "proj-a",
        "s1",
        "agent-bbb",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 30})],
        meta={"agentType": "builder"},
    )

    exit_code = token_usage.main(["--dir", str(tmp_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "subagents=2" in out
    assert "role" in out
    assert "builder" in out
    assert "tester" in out
    assert out.index("builder") < out.index("tester")


def test_project_filter_matches_subagents_via_parent_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stamp = datetime(2026, 1, 1, 12, 0, 0)
    _write_session(
        tmp_path,
        "proj-keep",
        "s1",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        stamp,
    )
    _write_subagent(
        tmp_path,
        "proj-keep",
        "s1",
        "agent-aaa",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 2})],
        meta={"agentType": "tester"},
    )
    _write_session(
        tmp_path,
        "proj-drop",
        "s2",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        stamp,
    )
    _write_subagent(
        tmp_path,
        "proj-drop",
        "s2",
        "agent-bbb",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 4})],
        meta={"agentType": "builder"},
    )

    found = token_usage.scan_sessions(tmp_path, project_filter="keep")
    assert [path.stem for path in found] == ["s1"]

    exit_code = token_usage.main(
        ["--dir", str(tmp_path), "--project", "keep"]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "session s1" in out
    assert "session s2" not in out
    assert "tester" in out
    assert "builder" not in out


def test_latest_picks_session_file_not_subagent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_session(
        tmp_path,
        "proj-a",
        "s1",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        datetime(2026, 1, 1, 12, 0, 0),
    )
    _write_subagent(
        tmp_path,
        "proj-a",
        "s1",
        "agent-aaa",
        [_assistant_line(MODEL_FABLE, {"input_tokens": 2})],
        meta={"agentType": "tester"},
        mtime=datetime(2026, 1, 3, 12, 0, 0),
    )
    _write_session(
        tmp_path,
        "proj-a",
        "s2",
        [_assistant_line(MODEL_OPUS, {"input_tokens": 1})],
        datetime(2026, 1, 2, 12, 0, 0),
    )

    exit_code = token_usage.main(["--dir", str(tmp_path), "--latest"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "session s2" in out
    assert "session s1" not in out
    assert "subagents=0" in out

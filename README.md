# claude-fable-orchestrator

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Portable Claude Code orchestration scaffold, ported from
[donvito/codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator).
A `fable` root agent orchestrates `opus` execution subagents (explorer, worker,
tester, researcher) and an independent `fable` reviewer — review runs on a
different model than implementation, so findings are not self-grading.
Workflows ("flows") are loaded at runtime by the orchestrator skill: the user
names one, or the skill picks by task shape.

## Layout

```
claude-fable-orchestrator/
├── setup.sh                    # interactive installer (bash, macOS/Linux)
├── CLAUDE.snippet.md           # orchestration block appended to target CLAUDE.md
├── CONTRIBUTING.md
├── claude/                     # installed into <target>/.claude/
│   ├── agents/                 # explorer, worker, tester, researcher, reviewer
│   └── skills/orchestrator/
│       ├── SKILL.md            # delegation gate, contracts, flow loader
│       └── flows/              # quick, standard, full, debug, research
├── scripts/
│   └── token_usage.py          # token usage from local transcripts
└── tests/
    └── test_token_usage.py     # pytest suite for token_usage.py
```

## Models

| Role                | Model                  | Effort          |
| ------------------- | ---------------------- | --------------- |
| root (orchestrator) | fable (session model)  | session default |
| explorer            | opus                   | medium          |
| worker              | opus                   | high            |
| tester              | opus                   | medium          |
| researcher          | opus                   | medium          |
| reviewer            | fable                  | low             |

## Prerequisites

- Claude Code v2.1.x or newer, where `fable` resolves as a model alias —
  verify with `/model fable`.
- `effort: max` support depends on the model and Claude Code version; if it
  is rejected, fall back to `high` in `.claude/agents/*.md` frontmatter.
- `effort` frontmatter may be ignored for Agent-tool spawns on some Claude
  Code versions; the `model:` pin is the reliable lever.

## Install

```
git clone <this repo>
cd claude-fable-orchestrator
./setup.sh
```

`setup.sh` prompts for the target repo path (must exist, must not be the
scaffold itself), then asks per component: `.claude/agents`, the
`.claude/skills/orchestrator` skill, the CLAUDE.md orchestration block, and
`.claude/settings.json` with `"model": "fable"`. Existing files are listed
before any overwrite and need a separate `Update?` confirmation. The CLAUDE.md
block is marker-wrapped and skipped if already installed; an existing
`settings.json` is never edited — the installer prints the key to add instead.

## Flows

| Flow     | When to use                                                                 |
| -------- | --------------------------------------------------------------------------- |
| quick    | One bounded fix where the code path is already known; worker only.          |
| standard | Default for non-trivial work: explore → implement → test → review.          |
| full     | Multi-module or repo-wide changes: parallel explore/research, parallel workers, test, fable review, root integration. |
| debug    | Cross-component bugs: parallel evidence → diagnosis → fix → reproduction/regression check, plus an optional reviewer step when the fix is high-risk or non-obvious. |
| research | Investigation only, no edits: audits, feasibility, pre-planning.            |

Add a flow by dropping `<name>.md` into `.claude/skills/orchestrator/flows/`
in the target repo: frontmatter `name` + `description` (the when-to-use), then
ordered steps naming a role, an optional model override, a parallel group, and
the delegated task. No installer rerun needed.

Runtime selection:

- `use the orchestrator skill` — the skill picks a flow by task shape
- `use the debug flow` — explicit pick
- `orchestrate the full flow on <task>` — pick + task in one line

## Tuning

- Executor efforts (`medium`/`high`) are deliberately set below upstream's
  `max` to keep cost down; `xhigh`/`max` are available if you raise them
  manually in `.claude/agents/*.md` frontmatter.
- Cheaper runs: lower `effort:` to `low`/`medium`, or switch executors to
  `model: sonnet`.
- Bigger repos: raise worker `effort` to `max` (if your Claude Code version
  accepts it), add more parallel workers in the `full` flow.
- Strict separation: read-only roles are enforced via `disallowedTools`
  (tool-level, weaker than an OS sandbox). `explorer` and `researcher` also
  lose `Bash`; `reviewer` keeps `Bash` for `git diff`/inspection. Every role
  disallows `Agent`, so only the main thread orchestrates.

## Token usage

```
python3 scripts/token_usage.py --list             # sessions with token sums
python3 scripts/token_usage.py --latest           # most recent session
python3 scripts/token_usage.py --date 2026-01-15  # sessions on a date
```

Reads `~/.claude/projects/<project>/<session>.jsonl` transcripts plus each
session's `subagents/agent-*.jsonl` files; `--dir` and `--project` narrow the
scan. Reports per-model sums, a main-vs-sidechain split, and a per-agent-role
breakdown from `agent-*.meta.json` (`agentType`, fallback role `subagent`).

## Notes

- The `model` parameter on an Agent spawn overrides agent frontmatter
  per-invocation; flow steps use it for deliberate overrides only.
- Nested subagents are disabled for all roles by design (`Agent` in
  `disallowedTools`) — the root thread is the only orchestrator.
- `setup.sh` is bash on macOS/Linux only; no Windows installer.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE). Ported from
[donvito/codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator)
(Apache-2.0).

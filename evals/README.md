# evals/

Deterministic eval harness for the orchestrator scaffold. Each task copies a
tiny fixture project into a scratch workdir, installs the scaffold
(`.claude/` + CLAUDE.md orchestration block + model-pinned `settings.json`),
runs `claude -p` on a prompt, then grades the run from the session transcript
and a post-run workdir snapshot.

What it measures:

- Delegation actually happened — spawned subagent roles from
  `agent-*.meta.json` (`agentType`), checked against `must_spawn`,
  `must_spawn_any`, `must_not_spawn`, `min_spawned`, `max_spawned`.
- Roles + models — per-role model from each agent's first `message.model`,
  plus per-role token totals.
- Flow pick — `expect_flow` checked against the flow named in the Skill
  tool_use args, or flow mentions in assistant text; unobserved flow is a
  warn, not a fail.
- Outcome assertions — `file_exists`, `file_contains`, `output_contains`,
  `tests_pass`, `files_unchanged` (sha256 vs pre-run manifest).
- Cost — token totals land in each task record under `transcript`.

## Run

```
python3 evals/run_evals.py --list                 # show the dataset
python3 evals/run_evals.py --all --model sonnet   # full run, real API cost
python3 evals/run_evals.py --task calc-bug        # single task
python3 evals/grade.py --latest                   # grade newest run dir
python3 evals/grade.py evals/results/run-<ts>-<id>
```

Default model is `sonnet` (the user's fable quota is exhausted; override with
`--model`). `--timeout` overrides per-task `timeout_s`. `--into <run-dir>`
merges a rerun into an existing run dir. `--keep-work` keeps
`evals/.work/<id>` scratch dirs.

Artifacts per task under `evals/results/<run>/`: `<id>.json` (record:
session_id, claude_version, scaffold_commit, returncode, duration, timed_out,
result_text, manifest, transcript summary), `<id>/stdout.txt`,
`<id>/stderr.txt`, `<id>/workdir/` (post-run snapshot, `.claude` and caches
excluded).

## Caveats

- Real token cost: roughly 1-10M tokens per task depending on flow.
- Non-determinism: the model may pick different roles or flows; warn-level
  checks (`max_spawned`, unobserved flow) exist for that reason.
- Environment leakage: MCP servers are stripped via `--strict-mcp-config
  --mcp-config '{"mcpServers":{}}'`, but the user's global `~/.claude`
  config (CLAUDE.md, plugins) still applies — `CLAUDE_CONFIG_DIR` is left
  untouched on purpose. When set, transcripts are read from
  `$CLAUDE_CONFIG_DIR/projects` instead of `~/.claude/projects`.
- The transcript format (`message.model`, `message.usage`, `isSidechain`,
  `agentType` meta files, subagents dir layout) is Claude Code internals and
  may change across versions; `claude_version` is recorded per run.
- `tests_pass` runs the assertion `cmd` (shlex-split, no shell) inside the
  workdir snapshot with a 120s cap.

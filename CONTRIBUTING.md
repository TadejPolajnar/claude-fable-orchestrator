# Contributing

Issues and pull requests are welcome.

## Ways to contribute

- **New flows** — add `claude/skills/orchestrator/flows/<name>.md`: frontmatter
  `name` + `description` (when-to-use), then ordered steps with `role`,
  optional `model`, `parallel` group, and `task`.
- **Agent role tuning** — edits to `claude/agents/*.md` frontmatter (`model`,
  `effort`, `disallowedTools`) or role bodies. Keep bodies terse and
  imperative; end each with the escalation rule.
- **Installer improvements** — `setup.sh` must stay bash 3.2-safe (macOS
  default): no `mapfile`, no associative arrays, no `${var,,}`.
- **Token usage** — `scripts/token_usage.py` is stdlib-only and fully typed.

## Checks before a PR

```
bash -n setup.sh
python3 -m pytest tests/
```

## Conventions

- English only, no emojis.
- Minimal comments — only where a reader would be confused without one.
- The port tracks `donvito/codex-astra-luna-orchestrator`; if you port new
  upstream behavior, keep the model mapping (root fable, executors opus,
  reviewer fable).

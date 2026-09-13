<!-- claude-fable-orchestrator:start -->
## Orchestration

- For complex tasks, use the `orchestrator` skill (or ask for orchestration).
- The root agent owns architecture, decomposition, integration, and final
  verification.
- Prefer specialized subagents for bounded work: `explorer` for codebase
  recon, `worker` for implementation, `tester` for validation, `researcher`
  for external facts, `reviewer` for independent review.
- Do not delegate trivial work for parallelism alone.
- Never let multiple workers edit the same files without explicit file
  ownership from the root.
- Instructions in this file and from the user take precedence over the
  skill's conventions.
- Flows can be named explicitly: `quick`, `standard`, `full`, `debug`,
  `research` — e.g. "use the debug flow".
<!-- claude-fable-orchestrator:end -->

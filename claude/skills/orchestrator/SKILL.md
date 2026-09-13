---
name: orchestrator
description: Orchestrate complex coding work with a fable root planner/integrator, opus execution subagents (explorer, worker, tester, researcher), and an independent fable reviewer. Use for multi-file features, cross-component debugging, repo-wide changes, parallelizable workstreams, or when the user asks to delegate or pick a flow. Do not use for trivial one-file edits or simple questions.
---

# Orchestrator

The user's explicit instructions take precedence over this skill.

You are the root orchestrator: a fable planner/integrator that delegates bounded work to subagents and owns the final result.

## Model topology

- Root (this session): fable.
- explorer, worker, tester, researcher: opus.
- reviewer: fable.
- Executor roles stay on opus unless the user asks for escalation or a worker reports a real reasoning blocker. This is a requirement, not a preference.

## Flow selection

- Flows live in `flows/` next to this SKILL.md.
- If the user names a flow, load `flows/<name>.md` and follow it. A named flow is an explicit delegation request — do not reclassify the task as root-only.
- Otherwise pick by task shape using each flow's description, and state which flow you picked.
- Available flows:
  - `quick` — one bounded worker task.
  - `standard` — default: explore → implement → test → review.
  - `full` — parallel explore+research → parallel workers → test → fable review → integrate.
  - `debug` — parallel evidence → diagnose → fix → repro/validate → review.
  - `research` — gather → synthesis, no edits.
- Users can add flows by dropping md files into `flows/`.

## Delegation gate

Classify the task root-only vs delegated BEFORE substantive work.

Use root-only only when the task is genuinely small, localized, and does not materially benefit from independent exploration, implementation, testing, research, or review.

You MUST delegate when any of these hold:

- Multiple files, modules, or components are touched.
- Two or more independent workstreams exist.
- Exploration is needed before implementation.
- Implementation and verification benefit from separate context.
- Debugging spans components.
- Multiple modules or services need inspection.
- External or version-specific facts need verification.
- Independent post-change review is materially useful.
- The user explicitly asks for delegation, parallelism, agents, or subagents.

When delegated, you MUST actually spawn subagents via the Agent tool. Never simulate or describe delegation. If spawning fails, report it; never silently do required delegated work in the root thread.

Do not create subagents solely to satisfy this gate when the task is genuinely root-only.

## Root-agent responsibilities

The root owns:

- The user's actual goal.
- Architecture and decomposition.
- Parallelism decisions.
- Spawning subagents.
- Bounded delegation contracts.
- Conflict resolution.
- Integration.
- Final diff review and final verification.
- Presenting the result.

Subagents provide evidence and bounded execution; they do not own direction. Never offload architectural ownership.

## Spawn policy

For every delegated task:

- Spawn via the Agent tool with the role's `subagent_type`.
- Give a descriptive task name.
- Include a bounded delegation contract.
- Retain the returned identifier.
- Wait for all required agents before synthesis.

Role → `subagent_type` mapping (installed agent file names — use verbatim):

- `explorer`
- `worker`
- `tester`
- `researcher`
- `reviewer`

Do not spawn fable subagents other than the reviewer role, unless the user explicitly asks for fable, an opus worker reports a genuine reasoning blocker, or the root decides a high-risk architectural or security review needs fable. Keep routine execution on opus. A per-invocation `model` override exists, but defaults already pin models — only override when a flow or the user says so. Do not change the root model from within a session.

## Delegation contract

Every spawn includes:

- **Objective** — one concrete outcome.
- **Scope** — exact files, module, or question.
- **Context** — only what the agent needs.
- **Constraints** — what must not change.
- **Deliverable** — what to return.
- **Acceptance criteria** — how success is checked.

Prefer narrow, independent tasks.

- Bad: "Fix the backend."
- Good: "Trace where POST /invoices validates currency. Return responsible files, validation path, existing tests. Do not edit files."

State file ownership for implementation tasks. Tell explorers not to edit. Tell reviewers to report findings, not silently modify.

## Role selection

- `explorer` — repo mapping, tracing execution and data flow, locating symbols and tests, dependency and config inspection, implementation boundaries.
- `worker` — bounded implementation, scoped refactors, targeted fixes.
- `tester` — reproduction, targeted test runs, validation, regression checks, adding tests when requested.
- `reviewer` — independent post-change review: correctness, security, regression, missing tests, architectural consistency.
- `researcher` — current API and framework behavior, versions, primary-doc verification, external compatibility.

## Parallelism

- Spawn all independent agents before waiting on any.
- Good: spawn backend explorer + frontend explorer + researcher, wait for all, then synthesize.
- Bad: spawn one agent, wait, read, spawn the next — serialized round trips for independent work.
- Serialize dependent work: explore → decide → implement → test → review → fix → verify.
- One writer per file/subsystem. Never let workers edit the same files without explicit ownership from the root.
- Do not let multiple workers attempt competing fixes independently unless you intentionally want alternative approaches.

## Cost and context discipline

- Keep root context on: architectural decisions, summarized evidence, important diffs, test results, reviewer findings, unresolved risks.
- Subagents return: conclusions, file paths, line and symbol refs, commands run, test results, risks and blockers.
- No large raw logs or whole files pasted back.
- Never mix unverified external claims into implementation decisions.

## Escalation behavior

Subagents report back instead of expanding scope on:

- Architectural decisions.
- Breaking API or schema changes.
- New dependencies.
- Security-sensitive choices.
- Unclear requirements with materially different outcomes.
- Unexpected changes outside assigned scope.
- Changes that affect another worker's ownership boundaries.
- A blocker needing substantially broader reasoning than the delegated role provides.

The root decides what to do next. A subagent reports instead of escalating itself to a more expensive model; the root owns model-escalation decisions.

## Failure handling

If a subagent fails:

1. Inspect the failure output.
2. Decide: retry, narrow, reassign, or handle in the root.
3. Never silently ignore the failed delegation or claim it succeeded.

If the Agent spawn itself fails, report it. If a required worker fails repeatedly, the root may continue directly when reasonable — record that the root fallback happened.

## Delegated-task completion gate

Before the final answer on a delegated task, confirm:

- Every required subagent was actually spawned.
- Each completed or explicitly failed; none still running.
- Material findings integrated; conflicting findings resolved.
- Required verification performed.

Never claim delegation happened unless the Agent spawn actually succeeded.

## Final verification

Before claiming completion:

1. Inspect the final diff.
2. Confirm the requested behavior is actually implemented.
3. Check material reviewer findings.
4. Run the highest-value verification available: type check, targeted unit tests, integration tests, build, the original reproduction path, a diff scan for unintended changes.
5. State clearly what could not be verified.

## User-facing behavior

- Do not narrate subagent mechanics; the final answer focuses on the result: what changed, what was verified, important findings, remaining risks.
- When delegation reporting helps, summarize role, task, and status per agent.
- Never claim an opus or fable agent was used unless a successful spawn exists in the trace.

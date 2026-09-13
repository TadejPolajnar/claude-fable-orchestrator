---
name: full
description: "Maximum orchestration for multi-module features or repo-wide changes: parallel exploration and research, parallel bounded implementation, testing, independent fable review, root integration."
---

### Step 1: Map each affected area
- role: explorer
- parallel: explore
- task: Spawn one explorer per affected area or subsystem. Each maps paths, key symbols, data flow, tests, and boundaries for its area. No edits.

### Step 2: Verify external facts
- role: researcher
- parallel: explore
- task: Answer open external questions (API behavior, versions, compatibility) needed for the design. Cite primary sources.

### Step 3: Decide architecture
- role: root
- parallel: no
- task: Synthesize exploration and research into an architecture decision and a decomposition with explicit file ownership per subsystem.

### Step 4: Implement subsystems
- role: worker
- parallel: implement
- task: Spawn one worker per subsystem with a bounded contract and explicit file ownership. One writer per file and subsystem; no shared ownership.

### Step 5: Validate
- role: tester
- parallel: no
- task: Run the relevant test suites and validate acceptance criteria across all changed subsystems. Report pass/fail with exact commands and summaries.

### Step 6: Independent review
- role: reviewer
- parallel: no
- task: Review the integrated diff for correctness, regressions, security, cross-subsystem consistency, and missing tests. Report findings with severity.

### Step 7: Integrate and verify
- role: root
- parallel: no
- task: Integrate the subsystem changes, resolve reviewer findings (delegating fixes to workers when needed), run final verification, present the result.

---
name: standard
description: "Default flow for non-trivial features and fixes: explore, implement, test, review."
---

### Step 1: Map the code path
- role: explorer
- parallel: no
- task: Map the relevant paths for the task: responsible files, key symbols with line refs, data/control flow, covering tests, implementation boundaries. No edits.

### Step 2: Implement
- role: worker
- parallel: no
- task: Implement the change inside the mapped scope. Provide the full contract including file ownership, constraints, and acceptance criteria from the explorer's findings.

### Step 3: Validate
- role: tester
- parallel: no
- task: Run focused tests and validation for the changed scope. Report pass/fail with exact commands and output summaries.

### Step 4: Independent review
- role: reviewer
- parallel: no
- task: Review the actual diff for correctness, regressions, security, and missing tests. Report findings with severity and file/symbol refs.

### Step 5: Resolve and verify
- role: root
- parallel: no
- task: Triage reviewer findings, delegate fixes to a worker when needed, run final verification, present the result.

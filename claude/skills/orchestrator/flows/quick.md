---
name: quick
description: "Single bounded implementation or fix where the code path is already known. One worker, no exploration or review. Use for small delegated tasks."
---

### Step 1: Implement
- role: worker
- parallel: no
- task: Delegate the task with a full contract: objective, exact files in scope, context, constraints, deliverable, acceptance criteria. On return, the root verifies the diff against the contract.

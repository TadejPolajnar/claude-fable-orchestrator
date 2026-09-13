---
name: debug
description: "Cross-component debugging: parallel evidence gathering, root-cause diagnosis, bounded fix, reproduction and regression check."
---

### Step 1: Map suspected areas
- role: explorer
- parallel: evidence
- task: Spawn one explorer per suspected component. Each reports the relevant code paths, symbols, and data flow around the reported failure. No edits.

### Step 2: Reproduce the failure
- role: tester
- parallel: evidence
- task: Attempt to reproduce the reported behavior. Report the exact reproduction command, observed vs expected output, and whether reproduction succeeded.

### Step 3: Diagnose root cause
- role: root
- parallel: no
- task: Pick the most likely root cause from the gathered evidence. State the hypothesis and the fix scope.

### Step 4: Implement the fix
- role: worker
- parallel: no
- task: Implement the bounded fix for the diagnosed root cause. Provide file ownership, constraints, and the acceptance criterion that the failure no longer reproduces.

### Step 5: Reproduce then validate
- role: tester
- parallel: no
- task: Confirm the original failure no longer reproduces, then run regression validation for the touched scope. Report exact commands and pass/fail.

### Step 6: Review if high-risk
- role: reviewer
- parallel: no
- task: Run only when the fix is high-risk or non-obvious. Review the diff for regressions and missed edge cases. Skip otherwise and record why.

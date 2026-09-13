---
name: research
description: "Investigation only, no code changes: gather repo and external evidence, return a synthesis. Use for audits, feasibility questions, and pre-planning."
---

### Step 1: Gather external facts
- role: researcher
- parallel: gather
- task: Answer the delegated external questions: API behavior, versions, compatibility, prior art. Cite primary sources and flag uncertainty.

### Step 2: Survey repo state
- role: explorer
- parallel: gather
- task: Map the repo state relevant to the question: affected paths, current implementation, tests, constraints. No edits.

### Step 3: Synthesize report
- role: root
- parallel: no
- task: Combine all findings into a report answering the original question with evidence, implications, and open risks. No workers, no edits.

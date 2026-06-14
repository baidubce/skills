---
name: famou-artifact-generator
description: "Interactive end-to-end Famou workflow for defining, implementing, and solving optimization tasks. The workflow typically proceeds in three stages: (1) understand the data and define the task, producing `problem.md`; (2) implement and validate `evaluator.py`, `init.py`, and `prompt.md` from the task definition; (3) run deep solving through Famou. Trigger this skill whenever the user wants to define, clarify, create, or fix a Famou task; prepare Famou experiment artifacts; write or update `problem.md`, `evaluator.py`, `init.py`, or `prompt.md`; run Famou; do deep solving; or solve an optimization, ML, or search problem with evolutionary methods. Even if the user simply says \"help me make a Famou task\", \"help me solve this\", or \"run Famou\", trigger this skill whenever the surrounding context indicates an optimization or search task. Also trigger when the user describes a combinatorial optimization, scheduling, routing, or ML problem without mentioning Famou — treat it as a potential Famou task."
metadata:
  author: famou-group
  version: "10.0"
---

# Famou Workflow Router

Route user tasks to the correct workflow.

## Responsibilities

1. Identify task type from user description
2. Select exactly one workflow file in `references/`
3. Delegate execution to that workflow
4. Do not embed step details — those belong in workflows and components

## Routing Rules

**Priority order:**

1. **User choice**: If the user explicitly names a workflow, use it
2. **Automatic routing**: Otherwise, match by task characteristics:

## Workflow Selection

| Workflow | When to Use |
|----------|-------------|
| `general` | Generic optimization, search, planning, scheduling, or ML tasks — all other cases |

## Execution Flow

1. **Route**: Determine workflow based on routing rules
2. **Delegate**: Read the selected file in `references/` and follow its instructions
3. **Exit**: After delegation, router's job is complete

If uncertain, default to `general` workflow and note assumptions.

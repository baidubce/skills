---
name: famou-artifact-generator
description: Interactive end-to-end FaMou task solving workflow in three steps: (1) data understanding and problem definition, producing `problem.md`; (2) implementing and validating `evaluator.py`, `init.py`, and `prompt.md` based on `problem.md`; (3) deep solving via Auto-Search or FaMou. Trigger this skill whenever the user wants to define, clarify, or create a FaMou task, prepare FaMou experiment artifacts, write or fix `problem.md`, `evaluator.py`, `init.py`, or `prompt.md`, do FaMou solving, run deep solving, or solve an optimization / ML / search problem with evolutionary methods. Even if the user simply says "help me make a FaMou task", "help me solve this", or "run FaMou", trigger this skill if the context involves optimization or search.
metadata:
  author: famou-group
  version: "2.0"
---

# FaMou Task Solver — Three-Step Workflow

Transform user-provided data and requirements into a runnable FaMou solving experiment.

```
┌─────────────────────────────────────────────────────────────┐
│  Input: user description / data files / documents           │
│           ↓                                                  │
│  Step 1  Data Understanding & Problem Definition            │
│                            → problem.md                     │
│           ↓                                                  │
│  Step 2  Adapter Implementation                             │
│                            → evaluator.py                   │
│                            → init.py                        │
│                            → prompt.md                      │
│           ↓                                                  │
│  Step 3  Deep Solving (user's choice)                       │
│                            → Auto-Search or FaMou           │
│                                                             │
│  Output: best solution + score                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Step Navigation

**Read the reference file before entering each step.**

| Step | Core Task | Input | Output | Reference |
|------|-----------|-------|--------|-----------|
| Step 1 | Data understanding, workspace analysis, interactive clarification, problem definition | User description + data files | `problem.md` | `references/step1-problem-definition.md` |
| Step 2 | Implement evaluator, initial solution, prompt | `problem.md` | `evaluator.py` `init.py` `prompt.md` | `references/step2-adapter.md` |
| Step 3 | Choose solving engine, execute | `evaluator.py` `init.py` `prompt.md` | Best solution + score | `references/step3-solving.md` |

---

## Execution Flow

```
① Read references/step1-problem-definition.md
   → Analyze workspace and user data
   → Clarify problem interactively
   → Write problem.md as the task contract, wait for user confirmation

② Read references/step2-adapter.md
   → Implement the adapter using problem.md + the fixed Step 2 implementation contract
   → Validate evaluator + init locally
   → Present to user for confirmation

③ Read references/step3-solving.md
   → Ask user to choose solving method
   → Execute and return best solution
```

**Each step requires explicit user confirmation before proceeding.**

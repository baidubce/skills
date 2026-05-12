# Workflow — General

Use this workflow for generic optimization, search, planning, scheduling, combinatorial, or ML tasks.

## Composition

1. Read `components/default-problem-definition.md`
2. After explicit user confirmation on `problem.md`, read `components/adapter.md`
3. After explicit user confirmation on Step 2 artifacts, read `components/solving.md`

## Artifact Flow

```text
user description / data
  -> components/default-problem-definition.md
  -> problem.md
  -> components/adapter.md
  -> evaluator.py + init.py + prompt.md
  -> components/solving.md
  -> best solution + score
```

## Workflow Rules

- This workflow owns only sequencing and handoff.
- Domain-specific step instructions belong in components, not here.

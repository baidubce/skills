# Step 1 — Data Understanding & Problem Definition

**Input**: User description + data files / documents  
**Output**: `problem.md` — complete problem definition, confirmed by the user

---

## Phase A: Understand Current State

Your goal is to build a complete mental model of the workspace before asking the user anything. Read first, ask later.

**DO:** Explore data files, scripts, README, and configs.  
**DO:** Understand scale, format, interfaces, and what they imply about the problem.  
**DO NOT:** Stop at a surface-level inventory.  
**DO NOT:** Ask the user anything in this phase.

Report findings before moving on:

```text
Workspace Scan
- Data files:    [filename] — [schema, scale, notable characteristics]
- Existing code: [yes/no; key interfaces and logic]
- Documentation: [yes/no; key conclusions extracted]
```

---

## Phase B: Clarification Loop

Resolve all required items below. Anything answerable from the workspace should be marked resolved immediately.

**Problem definition**
- [ ] Core problem: what does a solution look like, and what makes one better than another?
- [ ] Optimization objective and how it is measured
- [ ] Constraints: what must hold, what is optimized, and how quality is judged

**Data understanding**
- [ ] Tables / files involved and how they relate
- [ ] Data quality: missing values, duplicates, type inconsistencies, outliers
- [ ] Preprocessing assumptions needed before evaluation

**Task contract**
- [ ] I/O: CLI args, input files, expected output
- [ ] Scoring basis: how to distinguish solution quality levels
- [ ] Initial solution direction or baseline approach

**Loop** — ask one question at a time. If the user wants to move on before all items are fully resolved, continue with explicit assumptions.

---

## Phase C: Write & Confirm problem.md

Write `problem.md` using the template below. Merge with existing content if it already exists. User-clarified information takes precedence.

`problem.md` is the **task contract only**. Do not repeat implementation details that belong to Step 2, such as the evaluator interface, system-level execution constraints, or validation checklist.

```markdown
## Objective
<!-- READONLY: Prepare init.py, evaluator.py, and prompt.md for a FaMou evolutionary task -->

## 1. Task Definition
- Core problem description
- Input: (CLI arguments / data files)
- Output: (stdout / generated files)
- Primary optimization objective
- Key metrics and formulas

## 2. Data Description
- Data sources (file/table names, schema, field definitions)
- Access method (path, format)
- Data quality and preprocessing assumptions

## 3. Constraints and Evaluation Basis
- Hard constraints
- Soft constraints / optimization targets
- How solution quality should be measured

## 4. Initial Solution Direction
- Strategy or baseline direction
- Any required properties of a valid initial solution

## 5. Supplementary Information (optional)
- References
- Notes
- Open questions or assumptions
```

After writing, ask the user: *"Please review `problem.md` — is the problem definition clear and complete?"* Only proceed to Step 2 on explicit confirmation.

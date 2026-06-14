# Component — Problem Definition

**Input**: User description + data files / documents  
**Output**: `problem.md` — complete problem definition, confirmed by the user

---

## Phase A: Understand Current State

Your goal is to build a complete mental model of the workspace before asking the user anything. Read first, ask later.

**DO:** Review data files, user-provided schemas/descriptions, business documents, relevant code, README, and configs.  
**DO:** Understand scale, format, interfaces, data quality, and what they imply about the problem.  
**DO:** For complex data, use the `famou-data-analysis` skill when it helps clarify structure, quality, or meaning.  
**DO NOT:** Stop at a surface-level inventory; connect evidence to task semantics, constraints, and evaluation.  
**DO NOT:** Guess unclear business meaning, data semantics, or code intent; record doubts and confirm them in the clarification loop.  
**DO NOT:** Ask the user anything before completing this initial scan.

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
- [ ] Data-path contract: `init.py` reads data from an external path argument; `evaluator.py` passes an absolute path
- [ ] Scoring basis: how to distinguish solution quality levels
- [ ] Initial solution direction or baseline approach

**Loop** — prefer built-in question tools such as `ask_user` when requesting clarification or confirmation. Ask one question at a time. If the user wants to move on before all items are fully resolved, continue with explicit assumptions.

---

## Phase C: Write & Confirm `problem.md`

Write `problem.md` using the template below. Merge with existing content if it already exists. User-clarified information takes precedence.

`problem.md` is the **task contract only**. Do not repeat implementation details that belong to adapter generation, such as the evaluator interface, system-level execution constraints, or validation checklist.

```markdown
## Objective
<!-- READONLY: Prepare init.py, evaluator.py, and prompt.md for a Famou evolutionary task -->

## 1. Task Definition
- Core problem description
- Input: (CLI arguments / data files, including the data path passed from `evaluator.py` to `init.py`)
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

After writing, prefer a built-in question tool such as `ask_user` to ask: *"Please review `problem.md` — is the problem definition clear and complete?"* Only proceed after explicit confirmation.

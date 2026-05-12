# Component — Adapter

**Input**: `problem.md`  
**Output**: `evaluator.py`, `init.py`, `prompt.md`

**Goal**: Produce a runnable adapter for Famou, centered on a correct evaluator that can reliably score and distinguish feasible solutions of different quality, then verify it with two candidate solutions and keep the better valid one as `init.py`.

This component is the single source of truth for implementation requirements.

Use `problem.md` as the core dependency for task definition, data understanding, constraints, scoring basis, and initial solution direction. If some implementation detail is not explicitly written, make a reasonable assumption and keep it consistent with `problem.md`.

Implement in this order:

1. `evaluator.py`
2. `init.py`
3. `prompt.md`
4. validate and fix until passing
5. move other non-important intermediate results into `build/`
6. check once more after cleanup; if there is an error, fix it and rerun

## 1. `evaluator.py`

Fixed interface:

```python
def evaluate(path_user_py: str, task_name: str = "default", timeout: int = 3600) -> dict:
    return {
        "validity": float,
        "combined_score": float,
        "cost_time": float,
        "error_info": str,
    }
```

Rules:

- `validity` indicates whether the candidate is a valid feasible solution; `1` means it runs correctly and satisfies all required constraints.
- `combined_score` must be numeric and higher-is-better: `0` means the solution is invalid, a low score means the solution is valid but performs poorly, and a high score means the algorithm quality is high.
- `error_info` describes the reason for failure; if the solution is valid and correct, `error_info` must be `""`.
- You may add additional return fields beyond the core ones when they help debugging, analysis, or downstream inspection.
- Default parameter values such as `task_name` and `timeout` may be adjusted dynamically when needed, as long as the evaluator interface remains compatible with the contract.
- The evaluator must work even if `init.py` is not in the same directory.
- If using `subprocess`, set `cwd` to the directory containing `evaluator.py`.
- Do not depend on a temporary directory as the working directory.
- If task data is needed, `evaluator.py` resolves the absolute data path and passes it to `init.py`.
- `init.py` must not infer data paths from cwd, `__file__`, or hard-coded relative paths.

Execution flow:

1. Resolve paths. First resolve `evaluator.py` to an absolute path, then derive the absolute data path passed to the candidate.
2. Prepare required outputs.
3. Run the candidate script with the I/O contract from `problem.md`.
4. Capture exit status, stdout/stderr, timeout, and output files.
5. Check hard constraints first.
6. If hard constraints fail, return `validity = 0`, `combined_score = 0`, and set `error_info` to the failure reason.
7. Otherwise compute quality metrics and return a monotonic `combined_score` that can distinguish different feasible solution qualities.

## 2. `init.py`

Requirements:

- single file and directly runnable
- exactly follows the I/O contract in `problem.md`
- satisfies all hard constraints
- uses a simple, stable, baseline strategy
- if task data is needed, read it from the path argument supplied by `evaluator.py`; do not infer paths yourself

Prefer a deterministic heuristic, greedy method, simple rule-based baseline, or other lightweight valid solution.

Before finalizing `init.py`, try at least two feasible solution versions with different expected quality levels. Keep the better valid one as the final `init.py`.

## 3. `prompt.md`

Requirements:

- at most 100 lines
- no emoji
- no new business assumptions beyond `problem.md`

Must include:

1. Role
2. Task description
3. Data description
4. Reference feasible solution

Use `problem.md` as the source of truth and make the hard constraints explicit.

## 4. Validation

Run:

```bash
python evaluator.py <path_to_candidate_solution_a.py>
python evaluator.py <path_to_candidate_solution_b.py>
```

Passing requires:

- both candidate solutions are feasible: `validity == 1`
- both `combined_score` values are numeric
- both `error_info == ""`
- the evaluator assigns different scores to the two feasible solutions in the expected quality direction
- the better valid candidate is kept as the final `init.py`

If validation fails, fix the relevant file and rerun.

## 5. Failure Check Order

1. I/O mismatch between `init.py` and `evaluator.py`
2. path or working-directory handling
3. missing or malformed output
4. incorrect hard-constraint checks
5. wrong score mapping
6. evaluator cannot distinguish feasible solutions of different quality

## 6. Final Review

After validation passes, review `evaluator.py` and `init.py` once more to ensure there is no missing or incorrect implementation against `problem.md`. If any issue is found, fix it and rerun validation.

## 7. Workspace Cleanup

After the final review passes, clean the workspace without deleting files.

Rules:

- do not delete files as part of this cleanup step
- keep important files such as `evaluator.py`, `init.py`, `prompt.md`, and `problem.md` in the workspace root
- move other non-important intermediate results, including validation logs, temporary outputs, candidate variants, debug files, generated reports, and similar artifacts, into `build/`
- after cleanup, check once more; if there is an error, fix it and rerun

# Step 3 — Deep Solving

**Input**: `evaluator.py`, `init.py`, `prompt.md` (from Step 2)  
**Output**: Best `init.py` + score, tracked in git

Ask the user to choose a solving path before proceeding using an `ask-user` or other question-type tool.

> "Two solving options — please choose:
>
> **A. Auto-Search** — autonomous local loop; Claude iteratively improves `init.py`, git-tracked, no external service needed.  
> **B. FaMou** — submit to FaMou evolutionary platform via the `famou-experiment-manager` skill; requires API credentials."

---

## Path A: Auto-Search (Autonomous Loop)

Once started, **run continuously without asking the user**. Stop only when interrupted.

### A.1 Setup

```bash
# Initialize git tracking
git init
git add evaluator.py init.py prompt.md
git commit -m "baseline"

# Initialize results log
echo -e "commit\tscore\timprovement\tstatus\tdescription" > results.tsv
```

Run the baseline immediately and record it:
```bash
python evaluator.py init.py > run.log 2>&1
grep "combined_score\|validity" run.log
```

Log to `results.tsv`:
```
<7-char hash>   <score>   0.00%   keep   baseline
```

### A.2 The Loop — NEVER STOP

```
LOOP FOREVER:
  1. Form a hypothesis: what change to init.py might improve the score?
  2. Edit init.py directly.
  3. git commit -m "<description of change>"
  4. Run: python evaluator.py init.py > run.log 2>&1
  5. Read result: grep "combined_score\|validity\|error_info" run.log
     - If validity == 0 or error_info != "" → crashed or infeasible.
       Run: tail -30 run.log, fix if trivial, else discard.
  6. Log to results.tsv (tab-separated):
       <hash>  <score>  <improvement%>  keep|discard|crash  <description>
  7. If score improved → keep, this is the new baseline.
     If not → git revert to previous baseline: git checkout HEAD~1 -- init.py
  8. Go to 1.
```

**What to vary in `init.py`**:
- Algorithm logic: greedy → local search → more sophisticated heuristic
- Neighborhood / mutation strategy
- Construction approach (smarter initialization)
- Parameter tuning (step sizes, weights, thresholds)
- Problem-specific domain knowledge (exploit structure)
- Hybrid strategies combining multiple approaches

**Rules**:
- `evaluator.py` is **read-only** — never modify it.
- Simplicity wins: a tiny score gain with major complexity is not worth keeping; a simplification that holds the score is always a win.
- Trivial crash (typo, missing import) → fix and retry. Fundamentally broken idea → log `crash`, revert, move on.

`results.tsv` format (tab-separated):
```
commit	score	improvement	status	description
a1b2c3d	0.000000	0.00%	keep	baseline
b2c3d4e	0.123400	+12.34%	keep	greedy nearest-neighbor init
c3d4e5f	0.098000	-20.65%	discard	random restart, worse than baseline
d4e5f6g	0.000000	—	crash	tried beam search (import error)
```

---

## Path B: FaMou Deep Solving

Use the `famou-experiment-manager` skill and follow its complete workflow.

The three inputs for the FaMou task are the files produced in Step 2:

```
experiment/
├── evaluator.py     ← fixed scoring interface (READONLY)
├── init.py          ← this is what FaMou evolves
└── prompt.md        ← guides LLM mutation
```

Generate `config.yaml` based on problem scale from `problem.md`:

```yaml
evolve_config:
  max_iterations: 200      # small: 50–100, large: 200–500
  population_size: 50
  num_islands: 2

initial_program: "init.py"
evaluator: "evaluator.py"
system_message: "prompt.md"
```

Submit the experiment, then inform the user: *"Experiment submitted — FaMou jobs can take a while. I'll check status periodically; feel free to do other things."*

**Status polling** — use the `famou-experiment-manager` skill to query status every few minutes until the job completes. Report progress at each check:

```
⏳ [HH:MM] Experiment <id> — status: running | iterations: 42/200 | best_score: 0.1234
```

Once complete, retrieve results and proceed to the Result Report.

---

## Result Report

Upon completion (or when the user interrupts Path A), display:

```
📊 Results
─────────────────────────────────────
Engine:         Auto-Search | FaMou
Baseline score: {init_score:.6f}
Best score:     {best_score:.6f}
Improvement:    {improvement:+.2f}%
─────────────────────────────────────
Best solution:  init.py @ {commit}
```
---
name: famou-experiment-diagnosis
description: Diagnose a Famou experiment on explicit user request by inspecting its current status, latest leaderboard and result code, score improvement, candidate diversity, evaluator reward hacking, and signs of local convergence. Use when the user asks whether an experiment is healthy, improving, hacked, plateaued, stuck in a local optimum, or needs a diagnostic recommendation. Default to one read-only diagnosis; monitor repeatedly only when the user explicitly requests continuous diagnosis.
metadata:
  author: famou-group
  version: "1.0"
---

# Famou Experiment Diagnosis

Diagnose with current evidence, not status alone. Keep the workflow read-only and never pause, update, continue, cancel, delete, or resubmit an experiment without a separate explicit user request.

## Inputs

Resolve before asking the user:

- `experiment_id`
- local experiment directory containing `config.yaml` and, when available, `problem.md`, `evaluator.py`, `init.py`, and `prompt.md`

If local artifacts or earlier snapshots are unavailable, continue with platform evidence and mark the affected conclusions `INCONCLUSIVE`.

## Diagnose

### 1. Establish the Contract

Read the local task artifacts. Extract the candidate I/O contract, hard constraints, score direction and range, baseline score, evaluator checks, iteration budget, population size, island count, and cloud type. Treat `problem.md` as the task contract and `evaluator.py` as the implemented scoring contract; report any disagreement.

### 2. Collect Current Evidence

Run these read-only commands:

```bash
famou-ctl experiment status <experiment-id> --json
famou-ctl experiment leaderboard <experiment-id> --json
famou-ctl experiment results <experiment-id> --rank <k> --output ./results --json
famou-ctl experiment results <experiment-id> --top <k> --output ./results --json
```

Choose `k` based on the population size (default to 5). Save all outputs under `./results/`.

Do not overwrite `init.py`. If the leaderboard has no scored solutions, skip `results` and judge whether that is normal for the current stage.

Also read the most recent earlier snapshot under `.famou/diagnostics/<experiment-id>/` when one exists. A single snapshot can reveal invalid code or evaluator exploitation, but is insufficient to prove a plateau or local optimum.

### 3. Measure Improvement

Compare the baseline, previous snapshot, current leaderboard, and downloaded candidates:

- absolute and relative best-score improvement
- iterations since the last improvement
- score spread and duplicate-score frequency
- island representation in the Top results
- substantive code differences rather than renaming or constant changes

Preserve platform scores exactly. Do not claim improvement when the score direction or baseline is unknown.

### 4. Check Evaluator Exploitation

Inspect `evaluator.py` before executing downloaded code. Check candidates for:

- reading evaluator internals, expected answers, test labels, future data, or hidden outputs
- hard-coded results, fixed paths, environment assumptions, or output reuse
- bypassing required computation or constraints
- exploiting exceptions, timeouts, NaN/infinity, nondeterminism, filesystem state, subprocesses, or network access
- producing a high score while violating `problem.md`

When safe and supported by the local evaluator, re-evaluate downloaded candidates in an isolated temporary directory with a timeout. Report platform and reproduced scores separately. Never alter a candidate or evaluator to make the score reproduce.

### 5. Assess Local Convergence

Treat local-optimum risk as evidence-based, not certain. Strong signals require multiple snapshots and include:

- no meaningful best-score improvement across a substantial part of the iteration budget
- Top candidates converging to the same algorithm or nearly identical code
- very narrow score spread and low island diversity
- repeated superficial mutations without behavioral change
- continued budget consumption without new feasible regions or strategies

Distinguish convergence from a broken evaluator: identical scores, implausibly high scores, or invalid high-ranking code point first to evaluator weakness rather than a genuine local optimum.

## Report

Return one verdict:

- `HEALTHY`: meaningful progress with valid, diverse candidates
- `WATCH`: non-fatal plateau, weak diversity, or insufficient recent improvement
- `ABNORMAL`: platform failure, invalid candidates, evaluator exploitation, or broken scoring
- `INCONCLUSIVE`: missing artifacts, history, or reproducible evidence

Use this compact format:

```text
Overview
  Verdict:    <HEALTHY|WATCH|ABNORMAL|INCONCLUSIVE>
  Experiment: <id>  <status>  iteration <current>/<max>
  Summary:    <one-sentence diagnosis>

Score and candidates
  Baseline:   <score>
  Previous:   <score>
  Current:    <score>
  Change:     <absolute and relative delta>
  Candidates: <validity and diversity>
  Island分布:  <id>: best <score>, Top占比 <x/y>; ...

Risks
  Evaluator:  <low|medium|high> — <evidence>
  Local-opt:  <low|medium|high> — <evidence>

Recommendation
  Action:     <continue, inspect evaluator, adjust prompt/budget, or restart>
  Reason:     <supporting evidence and tradeoff>
  Evidence:   <snapshot directory or N/A>
```

Explain each assessment with concrete evidence rather than returning labels alone. In particular, state why the evaluator risk has its assigned level and which score trends, candidate similarities, diversity signals, or historical snapshots support the local-optimum risk.

Recommendations must explain the evidence and tradeoff. Suggest prompt or budget changes only when the evaluator remains trustworthy. If the evaluator or task contract is broken, recommend fixing the artifacts and starting a new experiment because an in-place experiment update cannot replace the evaluator.

For a continuous-diagnosis request, repeat only at the user-specified interval or meaningful iteration milestones and stop at the requested horizon or terminal state. Do not start an unbounded monitor.

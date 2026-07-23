# Component — Deep Solving

**Input**: `evaluator.py`, `init.py`, `prompt.md`
**Output**: Best `init.py` + score

---

## Famou Deep Solving

Use the `famou-experiment-manager` skill and follow its complete workflow.

Do not manually generate `config.yaml` in this step. Experiment submission and task management must be handled through the `famou-experiment-manager` skill.

The three core inputs for the Famou task:

```
experiment/
├── evaluator.py     ← fixed scoring interface (READONLY)
├── init.py          ← this is what Famou evolves
└── prompt.md        ← guides LLM mutation
```

Prepare these artifacts, then invoke the `famou-experiment-manager` skill to submit the experiment. Let that skill decide how the experiment should be packaged and submitted.

After submission, inform the user:

*"Experiment submitted — Famou jobs can take a while. I'll check status periodically and run a read-only diagnosis every 20 evolution rounds by default; feel free to do other things. You can also ask me to diagnose the experiment at any time."*

If the user requests diagnosis, invoke the `famou-experiment-diagnosis` skill with the current `experiment_id` and experiment directory. Diagnosis is read-only and must not interrupt or modify the running experiment.

**Status polling** — use the `famou-experiment-manager` skill to query status every 20 seconds until the job completes. Report progress at each check:

```
⏳ [HH:MM] Experiment <id> — status: running | iterations: 42/200 | best_score: 0.1234
```

**Periodic diagnosis** — during status polling, invoke the `famou-experiment-diagnosis` skill once every 20 completed evolution rounds by default, using the current `experiment_id` and experiment directory. Continue status polling after reporting the diagnosis.

Once complete, use the `famou-experiment-manager` skill to retrieve results and proceed to the Result Report.

---

## Result Report

Upon completion, display:

```
📊 Results
─────────────────────────────────────
Engine:         Famou
Baseline score: {init_score:.6f}
Best score:     {best_score:.6f}
Improvement:    {improvement:+.2f}%
─────────────────────────────────────
Best solution:  init.py
```

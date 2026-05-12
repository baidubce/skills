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

After submission, inform the user: *"Experiment submitted — Famou jobs can take a while. I'll check status periodically; feel free to do other things."*

**Status polling** — use the `famou-experiment-manager` skill to query status every 20 seconds until the job completes. Report progress at each check:

```
⏳ [HH:MM] Experiment <id> — status: running | iterations: 42/200 | best_score: 0.1234
```

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

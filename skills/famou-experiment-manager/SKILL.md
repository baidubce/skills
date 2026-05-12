---
name: famou-experiment-manager
description: Workflow skill for managing famou evolutionary experiment tasks, including public normal mode and public pro hybrid mode. Use this skill when the user mentions "submit experiment", "check experiment status", "delete experiment", "get experiment results", "account info", "quota", "credits", "famou experiment", "upload experiment", "config.yaml experiment", "hybrid mode", or needs to use famou-ctl to manage experiment tasks. Even if the user just says "submit" or "run experiment", trigger this skill whenever the context involves the famou platform.
metadata:
  author: famou-group
  version: "4.0"
---

# Famou Experiment Manager

A complete workflow for submitting and managing experiment tasks via `famou-ctl-sdk`.

---

## Prerequisites

### 1.1 Check famou-ctl-sdk Version

```bash
famou-ctl --version
```

- Required version: `famou-ctl-sdk >= 1.1.0`.
- If the installed version is lower than `1.1.0`, upgrade it: `famou-ctl upgrade`
- If the command is not found, install it: `pip install famou-sdk`

After installation or upgrade, verify again with `famou-ctl --version`. If it still fails or the version is still lower than `1.1.0`, stop and ask the user to check their Python environment, pip source configuration, or `famou-ctl` installation path.

### 1.2 Check and Configure API Settings

Use the helper script `scripts/config.py` to read and configure API settings.

**Read API config:**

```bash
python3 scripts/config.py read
```

| Result | Action |
|--------|--------|
| `status: "ok"` | Config is complete, skip configuration |
| `status: "missing"` | Prompt user to enter API key |

**Configure API:**

Ask the user to provide a valid **API_KEY**, then run:

```bash
python3 scripts/config.py write <YOUR_API_KEY>
```

---

## Submitting a Famou Experiment

### 2.1 Choose Submission Mode

Use the `ask_user` or `question` tool to let the user choose the submission mode before searching for or creating `config.yaml`:

- **Normal mode** — submit directly to the cloud (`cloud_type` omitted)
- **Hybrid mode** — run local test first, then submit, then start a local evaluator worker (`cloud_type: "hybrid"`)

### 2.2 Find config.yaml

Recursively search for all `config.yaml` files under the current working directory:

```bash
find . -name "config.yaml" -type f 2>/dev/null | sort
```

**Handle results:**

| Case | Action |
|------|--------|
| Exactly 1 found | Use it directly; inform the user of the path and proceed |
| Multiple found | Use `ask_user` tool to let the user choose |
| None found | Report to the user and provide the template for the selected mode |

`config.yaml` template:

```yaml
evolve_config:
  max_iterations: 100
  population_size: 100
  num_islands: 4
initial_program: "init.py"
evaluator: "evaluator.py"
system_message: "prompt.md"
```

Mode-specific `cloud_type` rule:

- Normal mode: omit `cloud_type`. If an existing config contains `cloud_type: "hybrid"`, do not treat it as normal mode.
- Hybrid mode: add `cloud_type: "hybrid"` before local test or submission.

### 2.3 Confirm Experiment Directory

Use the parent directory of the selected `config.yaml` (as an absolute path) as the experiment directory:

```bash
# Example: if config.yaml is at ./experiments/my_exp/config.yaml,
# the experiment directory is /absolute/path/to/experiments/my_exp
realpath $(dirname <path-to-config.yaml>)
```

### 2.4 Setting Experiment Name

Use the `ask_user` or `question` tool or ask the user in conversation to provide an `experiment_name`. **Remind the user that the experiment name may only contain letters, numbers, and underscores, and must not exceed 20 characters.**

### 2.5 Dry-run Before Creating the Experiment

Before any real experiment creation, run a dry-run from the experiment directory to estimate cost and verify credits:

```bash
famou-ctl experiment create \
  --config ./config.yaml \
  --experiment-name <experiment_name> \
  --dry-run \
  --json
```

- If credits are sufficient, tell the user the estimated cost and **ask whether to submit the experiment now using the `ask_user` or `question` tool**.
- If credits are insufficient, stop and tell the user the estimated cost, available credits if shown, and that they need to recharge.

### 2.6 Normal Mode: Submit the Experiment

First complete **2.5 Dry-run Before Creating the Experiment**. Only proceed if credits are sufficient and the user confirms submission.

```bash
famou-ctl experiment create \
  --config <absolute-path-to-config.yaml> \
  --experiment-name <experiment_name> \
  -y \
  --json
```

**Handle output:**
- Command succeeds: Parse the JSON output and display key information such as experiment ID and status.
- Poll experiment status every 30 seconds until online validation finishes.
- Validation passed: Continue polling until the experiment has completed 1 to 2 evolution rounds, then print the experiment status and stop polling.
- Validation failed: Show the failure details, fix the evaluator and initial solution as needed, delete the failed experiment, then resubmit.
- Command fails: Show the error message and prompt the user to check their configuration or network connection.

### 2.7 Hybrid Mode: Submit the Experiment

Cloud generates code; local evaluator worker evaluates and pushes results back. Start the worker once after the experiment is created.

#### 2.7.1 Run local test

Run the local test from the experiment directory. If the user did not specify a timeout, use a reasonable default such as `300`.

```bash
famou-ctl test --config ./config.yaml --timeout <timeout_seconds>
```

Handle output:

- Test succeeds: continue to submission.
- Test fails: stop submission, show the relevant error, fix `evaluator.py`, `init.py`, `prompt.md`, or `config.yaml` as needed, then rerun the local test.

#### 2.7.2 Submit the experiment

First complete **2.5 Dry-run Before Creating the Experiment**. Only proceed if credits are sufficient and the user confirms submission.

```bash
famou-ctl experiment create \
  --config <absolute-path-to-config.yaml> \
  --experiment-name <experiment_name> \
  -y \
  --json
```

On success, parse and keep the `experiment_id`. The evaluator worker and monitoring steps require this ID.

#### 2.7.3 Start local evaluator worker

From the experiment directory, create `.famou/`, clear any previous `.famou/eval_trace`, then start the evaluator as a background process. Redirect all output to `.famou/eval_trace` and save the process ID.

```bash
mkdir -p .famou
: > .famou/eval_trace
nohup famou-ctl evaluator start \
  --experiment-id <experiment_id> \
  --evaluator-path ./evaluator.py \
  --max-concurrent=1 \
  > .famou/eval_trace 2>&1 &
echo $! > .famou/evaluator.pid
```

If the runtime provides a built-in background shell/session mechanism, prefer it, but still redirect the evaluator output to `.famou/eval_trace`.

After starting the worker:

- Confirm `.famou/eval_trace` exists.
- Check `.famou/evaluator.pid` and verify the process is alive when the local environment supports PID checks.

#### 2.7.4 Monitor evaluator worker

Poll experiment status until online validation passes and the experiment has completed 1 to 3 evolution rounds. After that, stop polling experiment status and continue monitoring only the local evaluator worker.

Recommended check behavior:

- Poll experiment status every 30 seconds until online validation finishes.
- If validation fails, fix the evaluator and initial solution as needed, delete the failed experiment, then resubmit.
- If validation passes, continue polling until 3 to 5 evolution rounds have completed, then stop polling experiment status.
- Read the last 50 to 100 lines of `.famou/eval_trace`.
- Detect obvious evaluator errors, crashes, authentication failures, or repeated upload failures.
- Verify the evaluator process is still alive if `.famou/evaluator.pid` exists and PID checks are available.

For worker health checks, use a modest interval, for example every 1 to 5 minutes. Avoid starting multiple evaluator workers for the same experiment.

### 2.8 Experiment Status JSON Parsing

When parsing `famou-ctl experiment status <experiment-id> --json`, keep the outer and inner `status` fields separate. Do not flatten or overwrite fields with the same name.

- Outer `status`: indicates the overall experiment is active/running on the Famou cloud.
- Inner `status`: indicates the current Famou cloud stage.
- Inner `status: "INITIALING"`: the experiment is validating input. The progress value is validation progress. Continue polling until validation finishes.
- Inner `status: "RUNNING"`: the experiment has entered the evolution stage. The progress value is evolution progress. Continue polling until the desired 3 to 5 evolution rounds have completed.

When reporting status to the user, label these values distinctly, for example as overall status, current stage, stage progress, and evolution rounds.

---

## Other Experiment Operations

### Step 1: Confirm required inputs

- For `list`, no experiment ID is required. If the user asks for a status-specific list, use the requested status filter.
- For `status`, `pause`, `resume`, `cancel`, `delete`, `logs`, `results`, and `report`, look for `experiment-id` in the conversation context and use it directly.
- If an experiment ID is required but not available, use the `ask_user` tool to request it from the user.
- For `logs`, `results`, and `report`, if the user asks to save output but does not provide a file path, ask for the desired output path.

### Step 2: Run the appropriate command

**When informing the user of available capabilities, do NOT display the raw commands — just describe what each capability does.**

```bash
famou-ctl experiment list    --status <status> --json                                      # List experiments, optionally filtered by status
famou-ctl experiment status  <experiment-id> --json                                        # Check experiment status
famou-ctl experiment pause   <experiment-id> --json                                        # Pause running experiment
famou-ctl experiment resume  <experiment-id> --json                                        # Resume paused experiment
famou-ctl experiment cancel  <experiment-id> --json                                        # Cancel experiment
famou-ctl experiment delete  <experiment-id> --json                                        # Delete experiment
famou-ctl experiment logs    <experiment-id> --follow/-f --output <file-path> --json       # View and save experiment logs
famou-ctl experiment results <experiment-id> --output <file-path> --json                   # View experiment results
famou-ctl experiment report  <experiment-id> --output <file-path> --json                   # Download experiment report in PDF format
```

**Handle output:**
- Command succeeds: Parse JSON output using the status parsing rule above, then clearly display overall status, current stage, progress, creation time, and other key information.
- If the response includes credit or remaining allowance fields, display them exactly as returned, including numbers, units, and expiration dates; do not modify, omit, or merge them.
- Command fails: Show the error message and prompt the user to verify the `experiment-id` or check their network connection.

---

## Account Operations

When the user asks about account details, quota, credits, balance, usage, or remaining allowance, run:

```bash
famou-ctl account info
```

**Handle output:**
- Command succeeds: Summarize the account identity and quota/credit fields shown by the command. Preserve exact numbers, units, and expiration dates if present.
- Command fails: For authentication or configuration errors, ask the user to verify API settings using the configuration workflow above. For network or server errors, show the relevant error and suggest retrying later or checking network connectivity.

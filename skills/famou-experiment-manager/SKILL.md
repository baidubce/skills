---
name: famou-experiment-manager
description: 'Manage public and hybrid Famou experiments via famou-ctl: submit config.yaml tasks; inspect status, manifests, leaderboards, logs, and reports; fetch ranked or top results; pause, resume, update, continue, cancel, or delete runs; and check account quota or credits. Use for Famou experiment lifecycle and result-management requests, including short requests such as "submit", "run experiment", or "download the top result".'
metadata:
  author: famou-group
  version: "5.0"
---
# Famou Experiment Manager

Manage public and hybrid Famou experiments through `famou-ctl-sdk`.

## Prerequisites

Run `famou-ctl --version`. Require `famou-ctl-sdk >= 2.0.0`; use `famou-ctl upgrade` for an older version or `pip install famou-sdk==2.0.0` when missing, then verify again. If verification still fails, stop and ask the user to check the active Python environment, pip source, and executable path.

Read API configuration. Resolve `<skill-path>` to the absolute path of this skill directory:

```bash
python3 <skill-path>/scripts/config.py read
```

- If `status` is `ok`, continue.
- If `status` is `missing`, ask for an API key and run `python3 <skill-path>/scripts/config.py write <API_KEY>`.

## Submit an Experiment

### 1. Resolve Mode, Config, and Name

Before searching for or creating `config.yaml`, use the available `ask_user` or `question` tool to let the user choose:

- **Normal**: submit directly to the cloud (`cloud_type` omitted)
- **Hybrid**: run local test first, then submit, then start a local evaluator worker (`cloud_type: "hybrid"`)

Search recursively from the working directory:

```bash
find . -name "config.yaml" -type f 2>/dev/null | sort
```

Use the only match directly, use the available `ask_user` or `question` tool to choose among multiple matches, or report no match and provide this template:

```yaml
evolve_config:
  max_iterations: 50
  population_size: 50
  num_islands: 2
initial_program: "init.py"
evaluator: "evaluator.py"
system_message: "prompt.md"
```

Use the absolute parent directory of the selected config as the experiment directory. Use the available `ask_user` or `question` tool, or ask in conversation, for an `experiment_name`; it may contain only letters, numbers, and underscores and must be at most 20 characters.

### 2. Normal Mode

Use normal mode only when `cloud_type` is omitted. Do not treat a config containing `cloud_type: "hybrid"` as normal.

From the experiment directory, run a dry-run to estimate cost and verify credits:

```bash
famou-ctl experiment create \
  --config ./config.yaml \
  --experiment-name <experiment_name> \
  --dry-run \
  --json
```

- If credits are sufficient, tell the user the estimated cost and **ask whether to submit the experiment now using the `ask_user` or `question` tool**.
- If credits are insufficient, stop and tell the user the estimated cost, available credits if shown, and that they need to recharge.

Only after confirmation, create the experiment:

```bash
famou-ctl experiment create \
  --config <absolute-path-to-config.yaml> \
  --experiment-name <experiment_name> \
  -y \
  --json
```

On success, report the experiment ID and status. Poll status every 30 seconds until online validation finishes. If validation fails, show the details and stop. If it passes, continue until at least 1 to 2 evolution rounds complete, report status, and stop polling.

### 3. Hybrid Mode

Hybrid mode runs the evaluator locally while the cloud generates candidate code.

#### 3.1 Prepare and Test Locally

Add `cloud_type: "hybrid"` to `config.yaml`, keep `evaluator` for the local test, and run from the experiment directory:

**Optional evaluation timeouts:** The `timeouts` field may be omitted; when the user requests custom values, add or update it in `config.yaml` before testing:

```yaml
timeouts:
  heartbeat_wait_hours: 72   # Max wait after evaluator disconnect; default 48h, max 168h
  evaluation_wait_hours: 48  # Max duration of one evaluation; default 24h, max 48h
```

Omit `timeouts` to use the defaults. Values are in hours; reject `heartbeat_wait_hours > 168` or `evaluation_wait_hours > 48` and state the applicable limit. These values are validated and echoed by `famou-ctl test`, uploaded with `experiment create`, and cannot be changed after submission.

```bash
famou-ctl test --config ./config.yaml --timeout <timeout_seconds> --json
```

Default to a reasonable timeout such as `300`. On failure, stop submission, show the relevant error, fix the affected `evaluator.py`, `init.py`, `prompt.md`, or `config.yaml`, and rerun the test.

After the local test succeeds, remove the `evaluator` item from `config.yaml` before cloud submission. Keep the local `evaluator.py` file for the evaluator worker.

#### 3.2 Submit to Cloud

Follow the **Normal Mode** flow in Section 2 (dry-run, credit check, confirmation, and create), using the submission-ready hybrid config (with `evaluator` removed from the YAML). After creation, parse and keep the experiment ID for evaluator startup and monitoring.

#### 3.3 Start the Local Evaluator

**Before presenting the startup options, you must explicitly warn the user** that a worker started from the current session may be reclaimed on DuMate, WorkBuddy, QoderWork, TraeWork, and similar sandboxed platforms. If that happens, the evaluator must be restarted manually. Strongly recommend a manual start because it is less likely to be reclaimed. **Do not skip this warning.**

Require the user to explicitly choose one of the following using the available `ask_user` or `question` tool. **Do not start the local evaluator until a choice is received**:

- **Option-1 Manual start (strongly recommended):** reset the evaluator trace and PID, then guide the user through the Terminal steps below.
- **Option-2 Automatic start:** confirm the risk, then initialize and start the worker here.

For a manual start, tell the user to open a local Terminal, enter the absolute experiment directory, and run the macOS/Linux command below; on Windows, use an equivalent command to run the evaluator in the background, redirect output to `.famou/eval_trace`, and record/check its PID:

```bash
cd <absolute-experiment-directory>
mkdir -p .famou
: > .famou/eval_trace
nohup famou-ctl evaluator start \
  --experiment-id <experiment_id> \
  --evaluator-path ./evaluator.py \
  --max-concurrent=1 \
  > .famou/eval_trace 2>&1 &
echo $! > .famou/evaluator.pid
```

For an automatic start, create `.famou/`, clear `.famou/eval_trace`, and run the same `nohup` command from the experiment directory. If the runtime provides a built-in background shell/session mechanism, prefer it, but still redirect the evaluator output to `.famou/eval_trace`.

After either start method:

- Confirm `.famou/eval_trace` exists.
- Check `.famou/evaluator.pid` and verify the process is alive when the local environment supports PID checks.

#### 3.4 Validate and Monitor

Follow Normal Mode's polling flow in Section 2. After at least 1 to 2 evolution rounds complete, stop experiment status polling and continue monitoring only the local evaluator worker:

- Read the last 50 to 100 lines of `.famou/eval_trace`.
- Detect obvious evaluator errors, crashes, authentication failures, or repeated upload failures.
- Verify the evaluator process is still alive if `.famou/evaluator.pid` exists and PID checks are available.

For worker health checks, use a modest interval, for example every 1 to 5 minutes. Avoid starting multiple evaluator workers for the same experiment.

#### 3.5 Manual Recovery Mode

Use this flow when a previously started local evaluator has stopped, including after a sandbox or session reclaims the process. Do not clear `.famou/eval_trace` during recovery; append new output so the prior failure remains inspectable.

Use the macOS/Linux commands below; on Windows, use equivalent commands to check the recorded PID and restart the evaluator in the background with output appended to `.famou/eval_trace`.

1. Open a terminal.
2. Enter the experiment directory and check the evaluator process:

```bash
cd <absolute-experiment-directory>
if [ -f .famou/evaluator.pid ] && kill -0 "$(cat .famou/evaluator.pid)" 2>/dev/null; then
  echo "Evaluator is running (PID $(cat .famou/evaluator.pid))"
else
  echo "Evaluator is not running"
fi
```

3. Only if it is not running, restart it:

```bash
nohup famou-ctl evaluator start \
  --experiment-id <experiment_id> \
  --evaluator-path ./evaluator.py \
  --max-concurrent=1 \
  >> .famou/eval_trace 2>&1 &
echo $! > .famou/evaluator.pid
```

Do not run the restart command when Step 2 reports that the evaluator is running. Each hybrid experiment must have only one evaluator process.

## JSON Handling

All `--json` commands return either `success: true` with `data`, or `success: false` with `msg` and `error_type`. Never read `data` from a failed response.

For experiment status, read state from `data.status`. Report `current_iteration`, `max_iterations`, `progress`, `progress_stage`, `progress_status`, and `progress_message` separately when present; do not use the obsolete outer/inner status interpretation.

Handle errors as follows:

- `INVALID_ARGUMENT`: correct the request.
- `AUTH_ERROR`: ask the user to log in or verify API configuration.
- `PERMISSION_ERROR`: report the permission problem.
- `SYSTEM_NETWORK`: suggest retrying.
- `API_ERROR`: preserve the backend message.

For every operation, report relevant warnings, ignored changes, costs, and output paths. Preserve credit and remaining-allowance values exactly, including numbers, units, and expiration dates.

## Other Experiment Operations

### Step 1: Confirm required inputs

- For `list`, no experiment ID is required. If the user asks for a status-specific list, use the requested status filter.
- For `status`, `pause`, `resume`, `update`, `continue`, `cancel`, `delete`, `logs`, `leaderboard`, `results`, `manifest`, and `report`, look for `experiment-id` in the conversation context and use it directly.
- If an experiment ID is required but not available, use the `ask_user` tool to request it from the user.
- For `logs` and `report`, if the user asks to save output but does not provide a file path, ask for it. For `results`, use the SDK default output directory unless the user provides one.

### Step 1.5: Hybrid Evaluator Check

For a known running hybrid experiment, before lifecycle operations, check whether the local evaluator worker is alive. If it is absent, tell the user to restart it manually using Section 3.5; do not start a new worker automatically.

Request manual restart only for `RUNNING` experiments; do not request it for `PAUSED`, terminal, cancelled, or deleted experiments.

### Step 2: Run the appropriate command

**When informing the user of available capabilities, do NOT display the raw commands — just describe what each capability does.**

```bash
famou-ctl experiment list    --status <status> --json                                      # List experiments, optionally filtered by status
famou-ctl experiment status  <experiment-id> --json                                        # Check experiment status
famou-ctl experiment pause   <experiment-id> --json                                        # Pause running experiment
famou-ctl experiment resume  <experiment-id> --json                                        # Resume paused experiment
famou-ctl experiment update  <experiment-id> --config <path> --dry-run --json              # Preview prompt or budget changes
famou-ctl experiment update  <experiment-id> --config <path> -y --json                     # Apply confirmed changes
famou-ctl experiment continue <experiment-id> --iterations <N> -y --json                   # Continue a completed experiment
famou-ctl experiment cancel  <experiment-id> --json                                        # Cancel experiment
famou-ctl experiment delete  <experiment-id> --json                                        # Delete experiment
famou-ctl experiment logs    <experiment-id> --follow/-f --output <file-path> --json       # View and save experiment logs; default output: ./results
famou-ctl experiment leaderboard <experiment-id> --json                                    # View leaderboard metadata without downloading code
famou-ctl experiment results <experiment-id> --rank <N> --output <dir> --json              # Download one ranked solution; default output: ./results
famou-ctl experiment results <experiment-id> --top <N> --output <dir> --json               # Download the top N solutions; default output: ./results
famou-ctl experiment manifest <experiment-id> --json                                       # View the submitted file receipt
famou-ctl experiment report  <experiment-id> --output <file-path> --json                   # Download experiment report in PDF format; default output: ./results
```

1. `leaderboard` is read-only; it returns ranking metadata and does not download code.
2. For `results`, `--rank <N>` downloads the N-th ranked solution and `--top <N>` downloads the current top N; they are mutually exclusive. Default to rank 1 when neither is requested.
3. `pause` requires `RUNNING`; `resume` requires `PAUSED`. Hybrid pause does not stop, and resume does not start, the local evaluator.
4. `update` requires `RUNNING` or `PAUSED`. Run `--dry-run`, report `changes`, `ignored`, and cost, then use `-y` only after confirmation.
5. `continue` requires `COMPLETED`; confirm before using `-y`, and keep additional iterations within `[10, 500]`. Use `resume` for a paused experiment.
6. `manifest` is read-only and valid in every experiment state.
7. Obtain explicit confirmation before `cancel` or `delete`.

Handle every response according to **JSON Handling**. On failure, preserve the relevant error and ask the user to verify the request, experiment ID, authentication, permissions, or network as appropriate.

---

## Account Operations

When the user asks about account details, quota, credits, balance, usage, or remaining allowance, run:

```bash
famou-ctl account info
```

**Handle output:**

- Command succeeds: Summarize the account identity and quota/credit fields shown by the command. Preserve exact numbers, units, and expiration dates if present.
- Command fails: For authentication or configuration errors, ask the user to verify API settings using the configuration workflow above. For network or server errors, show the relevant error and suggest retrying later or checking network connectivity.

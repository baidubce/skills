# Hybrid Mode Submission

### 1. Resolve Config and Name

Search recursively from the working directory:

```bash
find . -name "config.yaml" -type f 2>/dev/null | sort
```

Use the only match directly, use the available `ask_user` or `question` tool to choose among multiple matches, or report no match and provide this template:

```yaml
evolve_config:
  max_iterations: 50
cloud_type: "hybrid"
initial_program: "init.py"
system_message: "prompt.md"
# timeouts:
#   heartbeat_wait_hours: 48          # 心跳等待超时 (1~168h, 默认 48h)
#   evaluation_wait_hours: 24         # 评估等待超时 (1~48h, 默认 24h)
# project_id: "existing-project-id"   # 仅本地校验，项目归属由 OpenAPI 决定
# project_name: "项目名称"             # 仅本地校验，与 project_id 二选一
```

**Optional configuration notes:**
- `timeouts.heartbeat_wait_hours` sets the heartbeat wait timeout (up to 168 hours); `timeouts.evaluation_wait_hours` sets the timeout for a single evaluation (up to 48 hours). The default values are usually sufficient.
- `project_id` and `project_name` are mutually exclusive. The final project assignment is determined by OpenAPI.

Use the absolute parent directory of the selected config as the experiment directory. Use the available `ask_user` or `question` tool, or ask in conversation, for an `experiment_name`; it may contain only letters, numbers, and underscores and must be at most 20 characters.

### 2. Prepare and Test Locally

Add `cloud_type: "hybrid"` to `config.yaml`, keep `evaluator` for the local test, and run from the experiment directory:

```bash
famou-ctl test --config ./config.yaml --timeout <timeout_seconds> --json
```

Default to a reasonable timeout such as `300`. On failure, stop submission, show the relevant error, fix the affected `evaluator.py`, `init.py`, `prompt.md`, or `config.yaml`, and rerun the test.

After the local test succeeds, remove the `evaluator` item from `config.yaml` before cloud submission. Keep the local `evaluator.py` file for the evaluator worker.

### 3. Submit to Cloud

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

On success, report and keep the experiment ID and status for evaluator startup and monitoring.

### 4. Start the Local Evaluator

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

### 5. Validate and Monitor

Poll status every 30 seconds until online validation finishes. If validation fails, show the details and stop. If it passes, continue until at least 1 to 2 evolution rounds complete, report status, and stop experiment status polling. Then continue monitoring only the local evaluator worker:

- Read the last 50 to 100 lines of `.famou/eval_trace`.
- Detect obvious evaluator errors, crashes, authentication failures, or repeated upload failures.
- Verify the evaluator process is still alive if `.famou/evaluator.pid` exists and PID checks are available.

For worker health checks, use a modest interval, for example every 1 to 5 minutes. Avoid starting multiple evaluator workers for the same experiment.

### 6. Manual Recovery Mode

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

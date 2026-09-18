---
name: famou-experiment-manager
description: 'Manage hybrid Famou experiments via famou-ctl: run local evaluators, submit config.yaml tasks, inspect status, manifests, leaderboards, logs, and reports; fetch ranked or top results; pause, resume, update, continue, cancel, or delete runs; and check account quota or credits. Public-mode submission is removed and must be handled by the newer industrial decision platform.'
metadata:
  author: famou-group
  version: "6.1"
---
# Famou Experiment Manager

> Manage Famou experiments using `famou-sdk` (pip package) through its `famou-ctl` CLI.

## Scope

This skill supports hybrid-mode experiments only. The public submission mode has been removed from this skill. If the user requests a public-mode experiment, direct the task to the newer industrial decision platform `https://www.famou.com/` and do not submit it through this skill.

## 1. Prerequisites

Run `famou-ctl --version`. Require `famou-sdk == 2.5.0`; if it is missing or a different version is installed, run `pip install famou-sdk==2.5.0`, then verify again. If verification still fails, stop and ask the user to check the active Python environment, pip source, and executable path.

Read API configuration. Resolve `<skill-path>` to the absolute path of this skill directory:

```bash
python3 <skill-path>/scripts/config.py read
```

- If `status` is `ok`, continue.
- If `status` is `missing`, ask for an API key and run `python3 <skill-path>/scripts/config.py write <API_KEY>`.

## 2. Submit a Hybrid Experiment

### Resolve Mode and Route

Before every submission, verify that the task is hybrid mode (`cloud_type: "hybrid"`) and read and follow `references/hybrid-submit.md`. If the user asks for public mode, tell the user: “普通模式任务需要前往新版的伐谋产业决策平台提交。” Then stop and do not submit it through this skill. After a hybrid submission, return to this skill for shared JSON handling and experiment lifecycle operations.

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

## 3. Other Experiment Operations

### Step 1: Confirm required inputs

- For `list`, no experiment ID is required. If the user asks for a status-specific list, use the requested status filter.
- For `status`, `pause`, `resume`, `update`, `continue`, `cancel`, `delete`, `logs`, `leaderboard`, `results`, `manifest`, and `report`, look for `experiment-id` in the conversation context and use it directly.
- If an experiment ID is required but not available, use the `ask_user` tool to request it from the user.
- For `logs` and `report`, if the user asks to save output but does not provide a file path, ask for it. For `results`, use the SDK default output directory unless the user provides one.
- For a known running hybrid experiment, before lifecycle operations, check whether the local evaluator worker is alive. If it is absent, tell the user to restart it manually using [Manual Recovery Mode](references/hybrid-submit.md#6-manual-recovery-mode); do not start a new worker automatically. Request manual restart only for `RUNNING` experiments; do not request it for `PAUSED`, terminal, cancelled, or deleted experiments.

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

## 4 Account Operations

When the user asks about account details, quota, credits, balance, usage, or remaining allowance, run:

```bash
famou-ctl account info
```

**Handle output:**

- Command succeeds: Summarize the account identity and quota/credit fields shown by the command. Preserve exact numbers, units, and expiration dates if present.
- Command fails: For authentication or configuration errors, ask the user to verify API settings using the configuration workflow above. For network or server errors, show the relevant error and suggest retrying later or checking network connectivity.

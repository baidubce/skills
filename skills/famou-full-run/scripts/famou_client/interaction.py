"""Translate observed cloud state into state-driven, host-independent interaction decisions."""
import datetime
import hashlib
import json

from .protocol import split_blocks


PHASE_LABELS = {
    "processing": "伐谋正在处理任务", "solving": "伐谋正在求解", "validating": "伐谋正在核验结果",
    "reporting": "伐谋正在整理报告", "clarification": "需要补充业务信息", "approval": "方案待确认",
    "evolution_initializing": "演化提交或初始化尚未确认完成",
    "evolution_running": "已确认演化在云端启动", "evolution_completed": "演化已结束",
    "evolution_failed": "演化失败", "evolution_cancelled": "演化已停止",
    "turn_complete": "伐谋本轮已结束", "failed": "伐谋本轮失败", "cancelled": "伐谋本轮已取消",
    "syncing": "正在恢复会话记录，尚未确认最新状态",
}

STEP_ICONS = {"done": "[✓]", "active": "[●]", "pending": "[ ]", "skipped": "[–]", "failed": "[✗]", "cancelled": "[■]"}


def _parse_iso(ts):
    """Parse an ISO-8601 UTC timestamp string safely, returning None on invalid input."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def _elapsed_text(turn):
    """Format elapsed duration of the current cloud turn from event timestamps."""
    start = _parse_iso(turn.started_at)
    if not start:
        return ""
    end = _parse_iso(turn.last_event_at) if turn.done else datetime.datetime.now(datetime.timezone.utc)
    if not end:
        return ""
    secs = max(0, int((end - start).total_seconds()))
    mins, rem = divmod(secs, 60)
    return f"{mins}分{rem:02d}秒" if mins else f"{rem}秒"


def _build_workflow_steps(turn, status, phase, files, pending, evolution, clarify=None):
    """Compute cross-turn workflow steps so any host can show the full pipeline cleanly."""
    m = turn.milestones
    latest = turn.progress[-1] if turn.progress else ""
    clarify_status = "done" if m["clarify_asked"] else "skipped"
    evolve_active = m["evolve_triggered"] or bool(evolution) or phase.startswith("evolution_")

    steps = [
        {"id": "intake", "label": "数据核查与理解", "status": "pending", "detail": ""},
        {"id": "clarify", "label": "业务澄清", "status": clarify_status, "detail": ""},
        {"id": "plan", "label": "方案制定与确认", "status": "pending", "detail": ""},
        {"id": "solve", "label": "执行求解与核验", "status": "pending", "detail": ""},
        {"id": "deliver", "label": "报告与结果交付", "status": "pending", "detail": ""},
    ]
    by_id = {s["id"]: s for s in steps}

    if status == "needs_clarification":
        q_list = clarify.get("questions") if isinstance(clarify, dict) else None
        q_count = len(q_list) if isinstance(q_list, list) else 0
        by_id["intake"]["status"] = "done"
        by_id["clarify"]["status"] = "active"
        by_id["clarify"]["detail"] = f"等待用户回答 {q_count} 个澄清问题" if q_count else "等待补充业务口径"
    elif status == "awaiting_approval" and pending and pending.get("name") == "evolve_create":
        for key in ("intake", "plan", "solve", "deliver"):
            by_id[key]["status"] = "done"
        by_id["clarify"]["status"] = clarify_status
        steps.append({"id": "evolve", "label": "深度演化", "status": "active", "detail": "等待确认启动深度演化"})
    elif status == "awaiting_approval":
        by_id["intake"]["status"] = "done"
        by_id["clarify"]["status"] = clarify_status
        by_id["plan"].update(status="active", detail="方案已就绪，等待确认执行")
    elif evolve_active and (phase.startswith("evolution_") or (turn.done and evolution)):
        for key in ("intake", "plan", "solve", "deliver"):
            by_id[key]["status"] = "done"
        by_id["clarify"]["status"] = clarify_status
        state = (evolution or {}).get("state")
        evo_status = {"completed": "done", "failed": "failed", "cancelled": "cancelled"}.get(state, "active")
        evo_detail = latest or PHASE_LABELS.get(phase, "")
        if state == "running" and isinstance((evolution or {}).get("progress"), (int, float)):
            evo_detail = f"持续优化中（进度 {evolution['progress']:.0%}）"
        steps.append({"id": "evolve", "label": "深度演化", "status": evo_status, "detail": evo_detail})
    elif phase == "reporting" or m["reporter_dispatched"] or (turn.done and (m["delivered_artifacts"] or files)) or (
        turn.done and not turn.abnormal and m["solver_dispatched"]
    ):
        for key in ("intake", "plan", "solve"):
            by_id[key]["status"] = "done"
        by_id["clarify"]["status"] = clarify_status
        by_id["deliver"]["status"] = "done" if (turn.done and not turn.abnormal) else "active"
        if by_id["deliver"]["status"] == "active":
            by_id["deliver"]["detail"] = latest or "正在整理报告与交付文件"
        elif files:
            by_id["deliver"]["detail"] = f"已生成 {len(files)} 个产物文件"
    elif phase in ("solving", "validating") or m["solver_dispatched"] or m["evaluator_dispatched"]:
        by_id["intake"]["status"] = "done"
        by_id["clarify"]["status"] = clarify_status
        by_id["plan"]["status"] = "done"
        if m["solver_finished"] and not m["evaluator_finished"] and not latest:
            detail = "求解已完成，评估器核验中"
        else:
            detail = latest or ("评估器核验中" if phase == "validating" else "求解与核验进行中")
        by_id["solve"].update(status="active", detail=detail)
    elif m["plan_prepared"] or (turn.done and m["turn_count"] >= 2 and not m["solver_dispatched"]):
        by_id["intake"]["status"] = "done"
        by_id["clarify"]["status"] = clarify_status
        by_id["plan"].update(
            status="active",
            detail="方案已整理，等待确认执行" if turn.done else (latest or "正在整理执行方案"),
        )
    elif turn.done and not turn.abnormal:
        by_id["intake"]["status"] = "done"
        for key in ("clarify", "plan", "solve"):
            by_id[key]["status"] = "skipped"
        by_id["deliver"]["status"] = "done"
    else:
        by_id["clarify"]["status"] = "pending" if not m["clarify_asked"] else "done"
        by_id["intake"].update(status="active", detail=latest or "正在检查数据与任务要求")

    if turn.abnormal in ("failed", "cancelled"):
        active = next((s for s in reversed(steps) if s["status"] == "active"), None)
        target = active or next((s for s in reversed(steps) if s["status"] == "done"), steps[0])
        target["status"] = turn.abnormal
        if turn.error and turn.abnormal == "failed":
            target["detail"] = str(turn.error)[:80]
    return steps


def _render_status_markdown(steps, elapsed, incomplete):
    """Render a clean, host-independent markdown workflow checklist."""
    header = "**伐谋云端进度**" + (f"（本轮已运行 {elapsed}）" if elapsed else "")
    lines = [header]
    if incomplete:
        lines.append("> 会话记录仍在补齐，以下为目前已观测到的阶段。")
    for idx, step in enumerate(steps, 1):
        icon = STEP_ICONS.get(step["status"], "[ ]")
        suffix = f" — {step['detail']}" if step.get("detail") else ""
        if step["status"] == "skipped" and not suffix:
            suffix = "（无需补充，已跳过）"
        lines.append(f"- {icon} {idx}. {step['label']}{suffix}")
    return "\n".join(lines)


def _render_clarification_markdown(clarify):
    """Render structured clarification JSON into complete, host-ready Chinese Markdown."""
    if clarify is None:
        return ""
    if isinstance(clarify, str):
        text = clarify.strip()
        return f"### 待确认问题\n{text}" if text else ""
    if not isinstance(clarify, dict):
        return f"### 待确认问题\n{json.dumps(clarify, ensure_ascii=False)}"
    title = str(clarify.get("title") or "请确认以下业务问题").strip()
    questions = clarify.get("questions")
    if not isinstance(questions, list) or not questions:
        return f"### {title}"
    lines = [f"### {title}"]
    for idx, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            lines.append(f"{idx}. {q}")
            continue
        label = str(q.get("label") or q.get("question") or f"问题 {idx}").strip()
        tag = "（多选）" if q.get("multi") is True else ("（单选）" if q.get("multi") is False else "")
        lines.append(f"{idx}. **{label}**{tag}")
        options = q.get("options")
        if isinstance(options, list) and options:
            opt_texts = []
            for opt in options:
                if isinstance(opt, dict):
                    text = str(opt.get("text") or opt.get("label") or "").strip()
                    if text:
                        opt_texts.append(text)
                elif opt:
                    opt_texts.append(str(opt).strip())
            if opt_texts:
                lines.append("   - 可选项：" + " / ".join(opt_texts))
        if q.get("default") not in (None, "", []):
            default_val = q["default"]
            if isinstance(default_val, list):
                default_val = "、".join(str(v) for v in default_val)
            lines.append(f"   - 默认参考（须由用户确认，不可代答）：{default_val}")
    return "\n".join(lines)


def _tool_description(steps, phase):
    """Suggest a concise Chinese tool description matching the active workflow step."""
    if phase == "syncing":
        return "继续同步伐谋会话进度"
    for idx, step in enumerate(steps, 1):
        if step["status"] == "active":
            return f"等待伐谋{step['label']}（第{idx}/{len(steps)}步）"
    return "查询伐谋任务进度"


def observation(ctx):
    """Convert replay turn state into a structured v2 observation and host action."""
    turn = ctx.turn
    done = turn.done and not ctx.history_incomplete
    say, clarify, artifacts = split_blocks(turn.final_text())
    pending = dict(turn.pending) if turn.pending else None
    if ctx.history_incomplete:
        say, clarify, artifacts, pending = "", None, [], None
    # The wire status remains compatible; phase describes work, interaction describes the host.
    status = (turn.abnormal or ("awaiting_approval" if pending else "needs_clarification"
                               if clarify is not None else "turn_complete")) if done else "waiting"
    evolution = turn.evolution.snapshot()
    phase = {"awaiting_approval": "approval", "needs_clarification": "clarification"}.get(status, status)
    if status in ("waiting", "turn_complete"):
        phase = turn.phase_hint if not done else "turn_complete"
        if evolution and (evolution["observed_in_current_turn"] or
                          (done and evolution["state"] in ("created", "initializing", "running"))):
            state = evolution["state"]
            if state in ("created", "initializing"):
                phase = "evolution_initializing"
            elif state in ("running", "completed", "failed", "cancelled"):
                phase = "evolution_" + state
        if turn.phase_hint == "reporting" and not done:
            phase = "reporting"
    if ctx.history_incomplete:
        phase = "syncing"

    if status in ("awaiting_approval", "needs_clarification"):
        action = "ask_user"
        reason = "approval_required" if pending else "clarification_required"
    elif status in ("failed", "cancelled"):
        action, reason = "report_error", status
    elif phase in ("evolution_failed", "evolution_cancelled") and done:
        action, reason = "report_error", phase
    elif ctx.interrupted:
        action, reason = "return_to_user", "host_interrupted"
    elif done and (phase == "evolution_running" or (phase == "evolution_initializing" and evolution)):
        action = "continue_wait" if ctx.mode == "follow" else "return_to_user"
        reason = "cloud_evolution_started" if phase == "evolution_running" else "cloud_initialization_pending"
    elif done:
        action, reason = "deliver", "turn_finished"
    elif ctx.mode == "peek":
        action, reason = "return_to_user", "interactive_wait_finished"
    else:
        action, reason = "continue_wait", "awaiting_cloud_reply"

    summary = PHASE_LABELS.get(phase, PHASE_LABELS["processing"])
    if status == "needs_clarification":
        q_list = clarify.get("questions") if isinstance(clarify, dict) else None
        if isinstance(q_list, list) and q_list:
            summary = f"伐谋需要你确认 {len(q_list)} 个业务问题后才能继续"
    if phase == "evolution_running" and evolution and not evolution["observed_in_current_turn"]:
        summary = "上次回执确认演化在云端运行，本轮没有更新实验状态"
    if phase == "evolution_failed" and not done:
        summary = "演化检查出现问题，伐谋仍在处理本轮任务"
    files = [{"name": item.get("name") or item.get("description") or "文件", "file_id": item.get("fileId")}
             for item in artifacts if isinstance(item, dict)]
    steps = _build_workflow_steps(turn, status, phase, files, pending, evolution, clarify)
    status_markdown = _render_status_markdown(steps, _elapsed_text(turn), ctx.history_incomplete)
    clarification_markdown = _render_clarification_markdown(clarify)
    messages = list(turn.business_messages)
    # Keep volatile URLs/timestamps/elapsed seconds out of the change detector.
    stable = {"status": status, "phase": phase, "message": say, "clarification": clarify,
              "error": turn.error if not ctx.history_incomplete else None,
              "pending": pending, "artifacts": files, "progress": list(turn.progress),
              "workflow_steps": steps, "messages": messages,
              "evolution": {k: v for k, v in (evolution or {}).items() if k != "observed_at"}}
    fingerprint = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    changed = fingerprint != ctx.previous.get("observation_fingerprint")
    tool_desc = _tool_description(steps, phase)
    resume = (ctx.continuation(automatic=action == "continue_wait", tool_description=tool_desc)
              if ctx.session_id else None)
    return {
        "schema_version": 2, "session_id": ctx.session_id, "status": status, "phase": phase,
        "turn_complete": done, "history_incomplete": ctx.history_incomplete, "message": say, "clarification": clarify,
        "clarification_markdown": clarification_markdown,
        "error": turn.error if not ctx.history_incomplete else None,
        "pending_approval": pending, "artifacts": files, "evolution": evolution,
        "workflow_steps": steps, "status_markdown": status_markdown,
        "messages": messages,
        "recent_replies": list(turn.recent_replies),
        "subtask_results": list(turn.subtask_results.values()),
        "progress": list(turn.progress) if changed and not ctx.history_incomplete else [],
        "update": {"changed": changed, "fingerprint": fingerprint},
        "interaction": {"action": action, "reason": reason, "summary": summary,
                        "mode": ctx.mode, "notification_scheduled": False},
        "requires_user_input": action == "ask_user",
        "next_action": {"continue_wait": "wait", "ask_user": "confirm_or_append" if pending else "append"}.get(action),
        "continuation": resume if action == "continue_wait" else None,
        "resume": resume, "request_id": ctx.request_id,
    }


def follow_cloud_evolution(ctx):
    """An idle chat may still have an independent experiment; follow mode observes future turns."""
    snapshot = ctx.turn.evolution.snapshot()
    return (ctx.mode == "follow" and not ctx.interrupted and not ctx.turn.abnormal
            and not ctx.turn.pending and split_blocks(ctx.turn.final_text())[1] is None
            and bool(snapshot and snapshot["state"] in ("created", "initializing", "running")))

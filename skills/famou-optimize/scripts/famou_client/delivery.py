"""Named file links and portable rendering. Ticket issuance is only for delivery boundaries."""
import re

import famou_config


LINK_FAILED_NOTICE = "查看链接生成失败，请稍后重新获取"


def result_link(name, url):
    """Escape markdown special characters in filenames and format a clickable link."""
    label = re.sub(r"\s+", " ", str(name)).strip() or "查看文件"
    label = re.sub(r"([\\`*_\[\]<>])", r"\\\1", label)
    return f"[{label}]({url})"


def delivery_links(transport, session_id, pending=None, artifacts=None):
    """Issue fresh one-time panel links for plan, delivered artifacts and the task workspace."""
    if not session_id:
        return [], 0
    entries, seen = [], set()
    if pending and pending.get("plan_file_id"):
        seen.add(pending["plan_file_id"])
        entries.append(("plan", pending.get("plan_file_name") or "PLAN.md", pending["plan_file_id"]))
    for artifact in artifacts or []:
        file_id = artifact.get("file_id")
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)
        entries.append(("artifact", artifact.get("name") or "查看文件", file_id))
    entries.append(("task", "查看工作空间与演化面板", None))
    links, failed = [], 0
    for kind, label, file_id in entries:
        ticket = transport.issue_login_ticket()
        if not ticket:
            # If the ticket service is unavailable, avoid N sequential 15s waits.
            failed = len(entries) - len(links)
            break
        url = (famou_config.file_panel_url(session_id, file_id, ticket) if file_id
               else famou_config.session_panel_url(session_id, ticket))
        link = {"kind": kind, "label": label, "url": url}
        if file_id:
            link["file_id"] = file_id
        links.append(link)
    return links, failed


def add_links(result, transport, enabled=True):
    """Attach signed delivery links and markdown rendering to a structured payload."""
    pending, files = result.get("pending_approval"), result.get("artifacts", [])
    links, failed = delivery_links(transport, result.get("session_id"), pending, files) if enabled else ([], 0)
    by_id = {link["file_id"]: link["url"] for link in links if link.get("file_id")}
    for item in files:
        item["url"] = by_id.get(item.get("file_id"))
    if pending:
        pending["plan_url"] = by_id.get(pending.get("plan_file_id"))
    open_url = (pending or {}).get("plan_url") or next((item.get("url") for item in files if item.get("url")), None)
    result.update({
        "links": links,
        "session_url": next((link["url"] for link in links if link["kind"] == "task"), None),
        "link_error": LINK_FAILED_NOTICE if failed else None,
        "link_note": None,
        "panel_contents": ["workspace", "evolution"],
        "delivery_markdown": "\n".join(
            ["- " + result_link(link["label"], link["url"]) for link in links]
            + (["- " + LINK_FAILED_NOTICE] if failed else [])
        ),
        "open_url": open_url,
    })
    return result


def text_output(result):
    """Render the same state decision as JSON; never maintain a second workflow in text mode."""
    lines = ["[伐谋] " + (result.get("error") or result.get("interaction", {}).get("summary", ""))]
    if result.get("status_markdown"):
        lines += ["", result["status_markdown"]]
    if result.get("message"):
        lines += ["", result["message"]]
    else:
        lines += ["", "\n\n".join(result.get("messages") or [])] if result.get("messages") else []
    if result.get("clarification_markdown"):
        lines += ["", result["clarification_markdown"]]
    elif result.get("clarification") is not None:
        import json
        lines += ["", json.dumps(result["clarification"], ensure_ascii=False, indent=2)]
    if result.get("pending_approval"):
        pending = result["pending_approval"]
        lines += ["", "待确认事项：" + pending["id"]]
    lines += result.get("evolution_estimate") or []
    lines += result.get("progress") or []
    if result.get("continuation"):
        import shlex
        lines += ["", "继续查询：" + shlex.join(result["continuation"]["argv"])]
    elif result.get("resume") and result.get("interaction", {}).get("action") == "return_to_user":
        lines += ["", "任务在云端继续；之后可查询进展。"]
    if result.get("delivery_markdown"):
        lines += ["", result["delivery_markdown"]]
    return "\n".join(lines)

"""SSE decoding and turn state. No network requests or local persistence."""
import collections
import http.client
import json
import os
import re
import socket

from .transport import FamouError
from .evolution import Evolution

PROGRESS_ITEMS = 6
TAG_BLOCKS = ("clarify", "artifacts", "evolve", "plan", "project")
STATUS_EVENTS = ("status", "session/status")


def set_read_timeout(resp, secs):
    """把这条连接后续读操作的超时设成 secs（inf = 一直阻塞）。拿不到底层 socket 就算了。"""
    try:
        resp.fp.raw._sock.settimeout(None if secs == float("inf") else max(0.5, secs))
    except Exception:
        pass


def read_events(resp, timeout_fn, result):
    """逐条产出 (id, type, data)。

    每次读之前调 timeout_fn() 决定这次最多等几秒。结束原因写进 result["end"]：
      "eof"     连接结束（伐谋一轮结束后会主动关流；约 400 秒也会断一次）
      "timeout" 这次读等到了时限
      "error"   读出错
    连接断在一条事件中间（收到了 id，data 不完整）时，这条事件的 id 写进 result["cut_id"]。

    ⚠ 读超时只能用来"到点停"，不能"超时了接着读"：Python 的 http 响应对象一旦发生过
      读超时就永久不可用（再读抛 "cannot read from timed out object"）。
    """
    cur = {}
    while True:
        secs = timeout_fn()
        if secs <= 0:
            result["end"] = "timeout"
            return
        set_read_timeout(resp, secs)
        try:
            line = resp.readline()
        except (socket.timeout, TimeoutError):
            result["end"] = "timeout"
            return
        except (ConnectionError, OSError, http.client.HTTPException):
            result["end"] = "error"
            yield from _flush_cut(cur, result)
            return
        if not line:
            result["end"] = "eof"
            yield from _flush_cut(cur, result)
            return
        line = line.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            if "data" in cur:
                try:
                    data = json.loads(cur["data"])
                except ValueError:
                    raise FamouError("事件流包含无法解析的 JSON；保留会话号，用 wait 续查，不重发操作") from None
                if not isinstance(data, dict):
                    raise FamouError("事件流 data 应为对象；请用 wait 续查")
                yield cur.get("id"), cur.get("type"), data
            cur = {}
            continue
        if line.startswith(":"):
            continue
        k, _, v = line.partition(":")
        v = v[1:] if v.startswith(" ") else v
        # ⚠ 字段名是 event_type，不是标准 SSE 的 event（文档 4.1.5）
        if k in ("event_type", "event"):
            cur["type"] = v
        elif k == "data":
            cur["data"] = (cur["data"] + "\n" + v) if "data" in cur else v
        elif k == "id":
            cur["id"] = v


def _flush_cut(cur, result):
    """Emit a complete final event; leave partial events for replay from the last complete cursor."""
    if not cur.get("id"):
        return
    try:
        data = json.loads(cur["data"]) if "data" in cur else None
    except ValueError:
        data = None
    if isinstance(data, dict):
        yield cur.get("id"), cur.get("type"), data
    else:
        result["cut_id"] = cur["id"]


def result_text(p):
    """Extract text blocks from a tool-result payload."""
    return "".join(i.get("text", "") for i in p.get("content") or [] if isinstance(i, dict))


def content_text(p):
    """Read message text from content blocks or the legacy text field."""
    c = p.get("content")
    if isinstance(c, list):
        c = "".join(i.get("text", "") for i in c if isinstance(i, dict))
    if not isinstance(c, str) or not c:
        c = p.get("text") if isinstance(p.get("text"), str) else ""
    return c


def describe_tool(p):
    """Map primary tools to business progress; don't expose shell commands or raw reasoning."""
    inp = p.get("input") or {}
    if not isinstance(inp, dict):
        return ""
    tool = p.get("tool", "")
    if tool == "evolve_create":
        return "正在准备提交深度演化"
    if tool == "evolve_status":
        return "正在核对深度演化状态"
    if tool == "evolve_sync":
        return "正在同步演化结果"
    agent = str(inp.get("agent_type") or "")
    if "solver" in agent:
        return "正在派发求解器构建并求解方案"
    if "evaluat" in agent:
        return "正在派发评估器建立独立核验"
    if "report" in agent:
        return "正在派发报告助手整理报告与图表"
    if "data" in agent or tool in ("read", "glob", "grep", "hitgene_prepare"):
        return "正在检查任务数据"
    if tool in ("project_list", "project_attribution"):
        return "正在关联项目归属信息"
    if tool.startswith("memory-cards"):
        return "正在检索或更新任务记忆"
    if tool in ("apply_patch", "write", "edit", "multiedit"):
        return "正在整理方案或交付说明"
    if tool == "agent_wait":
        return "正在等待云端求解与核验完成"
    if tool in ("agent_send", "bash", "hitgene_evaluate", "hitgene_job"):
        return "正在执行数据检查或核验"
    return "正在处理任务"


def describe_sub_tool(p, phase_hint, parallel_solve_eval=False):
    """Map subagent tool usage to safe Chinese progress without exposing shell args or paths."""
    tool = p.get("tool") or ""
    inp = p.get("input") if isinstance(p.get("input"), dict) else {}
    if tool == "skill":
        name = str(inp.get("name") or "").lower()
        if "data" in name or "spreadsheet" in name:
            return "正在核查与整理数据", "data"
        if "evaluator" in name:
            return "评估器正在构建独立核验规则", "validating"
        if "visualization" in name or "task-report" in name or "evolve-report" in name:
            return "报告助手正在制作报告与图表", "reporting"
        if "evolve-analysis" in name:
            return "正在分析深度演化结果", "reporting"
        if "evolve-experiment-submit" in name:
            return "正在准备深度演化提交包", "evolution_initializing"
        if "or-knowledge" in name or "ml-knowledge" in name or "runtime-budget" in name:
            return "求解器正在依据领域知识建模", "solving"
        return "", None
    if tool in ("apply_patch", "write", "edit", "multiedit"):
        if phase_hint == "reporting":
            return "报告助手正在生成并调整页面", None
        if parallel_solve_eval:
            return "求解器与评估器正在并行编写程序", None
        if phase_hint == "validating":
            return "评估器正在编写核验程序", None
        if phase_hint == "solving":
            return "求解器正在编写求解程序", None
        return "子任务正在编写程序与产物", None
    if tool == "bash":
        if phase_hint == "reporting":
            return "报告助手正在校验页面排版与图表", None
        if parallel_solve_eval:
            return "求解器与评估器正在并行运行计算与核验", None
        if phase_hint == "validating":
            return "评估器正在执行独立核验", None
        if phase_hint == "solving":
            return "求解器正在运行计算与自检", None
        return "子任务正在运行检查与计算", None
    return "", None


class Turn:
    """一轮里的内容。遇到用户消息就重新开始 —— 所以回放整段历史，最后剩下的就是最后一轮。"""

    def __init__(self):
        """Initialize an empty turn before consuming session events."""
        self.evolution = Evolution()
        self.tool_calls = {}
        self.recent_replies = collections.deque(maxlen=3)
        self.subtask_results = {}
        self.milestones = {
            "turn_count": 0,
            "has_files": False,
            "data_checked": False,
            "clarify_asked": False,
            "clarify_answered": False,
            "plan_prepared": False,
            "plan_confirmed": False,
            "solver_dispatched": False,
            "solver_finished": False,
            "evaluator_dispatched": False,
            "evaluator_finished": False,
            "reporter_dispatched": False,
            "delivered_artifacts": False,
            "evolve_triggered": False,
        }
        self.reset(None)

    def reset(self, started_at):
        """Clear prior-turn state and record the new turn start time."""
        if hasattr(self, "business_messages") and self.business_messages:
            self.recent_replies.append({"started_at": self.started_at,
                                        "messages": list(self.business_messages)})
        self.started_at = started_at
        self.last_event_at = started_at
        self.evolution.begin_turn()
        self.phase_hint = "processing"
        self.done = False
        # 这一轮没有正常完成时的原因："failed"（异常中断）/ "cancelled"（被取消）；正常结束为 None
        self.abnormal = None
        self.error = None
        self.title = None
        # 主 agent 的 text 事件；遇到主 agent 工具调用就清空 ——
        # 只保留「最后一次工具调用之后」的话，续跑子 agent 混进来的内容都在前面（3.1）
        self.tail_text = []
        self.business_messages = collections.deque(maxlen=8)
        self.pending = None
        # 主 agent 最近一次 evolve_create 的参数（轮数、是否用 GPU），用来估算深度演化要冻结的积分
        self.evolve_property = None
        # 只保留粗粒度业务活动，不转发模型思考或命令参数。
        self.progress = collections.deque(maxlen=PROGRESS_ITEMS)

    def _record_progress(self, desc):
        """Append a deduplicated coarse Chinese activity label."""
        if desc and (not self.progress or self.progress[-1] != desc):
            self.progress.append(desc)

    def _observe_sub_tool(self, p):
        """Extract safe coarse progress from subagent tool usage without affecting turn completion."""
        m = self.milestones
        parallel = (
            m["solver_dispatched"]
            and m["evaluator_dispatched"]
            and not m["solver_finished"]
            and not m["evaluator_finished"]
        )
        desc, role_hint = describe_sub_tool(p, self.phase_hint, parallel_solve_eval=parallel)
        if role_hint == "data":
            self.milestones["data_checked"] = True
        elif role_hint == "validating":
            self.milestones["evaluator_dispatched"] = True
            if self.phase_hint == "processing":
                self.phase_hint = "validating"
        elif role_hint == "reporting":
            self.milestones["reporter_dispatched"] = True
            if not self.phase_hint.startswith("evolution_"):
                self.phase_hint = "reporting"
        elif role_hint == "solving" and self.phase_hint == "processing":
            self.phase_hint = "solving"
        self._record_progress(desc)

    def feed(self, etype, data):
        """Apply one session event while separating primary-agent output from child progress."""
        p = data.get("payload") or {}
        if not isinstance(p, dict):
            return
        ts = data.get("created_at") or p.get("created_at")
        if ts:
            self.last_event_at = ts
        etype = p.get("type", etype) if etype in ("session/event", None) else etype
        # Child statuses cannot end the primary turn or grant a primary approval.
        sub = bool(p.get("parentId") or p.get("parent_id"))
        if sub:
            if etype == "tool_use":
                self._observe_sub_tool(p)
            return
        if etype == "user/message":
            # ⚠ 后台触发的轮次（演化事件）也有一条用户消息，只是正文为空（3.37）
            msgs = p.get("messages") or []
            has_text = False
            for m in msgs if isinstance(msgs, list) else []:
                for item in (m.get("content") or []) if isinstance(m, dict) else []:
                    if isinstance(item, dict):
                        if item.get("type") == "file":
                            self.milestones["has_files"] = True
                        if item.get("type") == "text" and str(item.get("text") or "").strip():
                            has_text = True
            if has_text or not self.milestones["turn_count"]:
                self.milestones["turn_count"] += 1
            if self.milestones["clarify_asked"] and has_text:
                self.milestones["clarify_answered"] = True
            self.reset(ts)
            return
        if etype in STATUS_EVENTS:
            st = p.get("status")
            # 实测三种结尾：正常 idle（stopReason=session.idle）；CancelSession 后 idle（stopReason=cancelled）；
            # 异常中断 status=failed（_meta 为空，没有 error 事件、没有原因）。ended / cancelled 是文档里的会话终态
            if st == "idle":
                self.done = True
                self.abnormal = ("cancelled" if (p.get("_meta") or {}).get("stopReason") == "cancelled"
                                 else "failed" if self.error else None)
            elif st in ("failed", "ended", "cancelled"):
                self.done = True
                self.abnormal = "cancelled" if st == "cancelled" else "failed"
            elif st in ("starting", "running", "active"):
                self.done = False
                self.abnormal = None
                self.error = None
            return
        if etype == "title" and p.get("title"):
            self.title = p["title"]
            return
        if etype == "error":
            self.error = p.get("message") or p.get("error") or "云端本轮执行出错"
            self.abnormal, self.done = "failed", True
            return

        if etype == "tool_use":
            self._record_progress(describe_tool(p))
            tool = p.get("tool")
            inp = p.get("input") if isinstance(p.get("input"), dict) else {}
            if p.get("id"):
                self.tool_calls[p["id"]] = tool
            agent = str(inp.get("agent_type") or "")
            if tool in ("evolve_create", "evolve_status"):
                self.phase_hint = "evolution_initializing"
                self.milestones["evolve_triggered"] = True
            elif tool == "evolve_sync" or "report" in agent:
                self.phase_hint = "reporting"
                self.milestones["reporter_dispatched"] = True
                if tool == "evolve_sync":
                    self.milestones["evolve_triggered"] = True
            elif "evaluat" in agent:
                self.phase_hint = "validating"
                self.milestones["evaluator_dispatched"] = True
                self.milestones["evaluator_finished"] = False
                self.milestones["plan_confirmed"] = True
            elif "solver" in agent or tool in ("agent_wait", "hitgene_evaluate"):
                self.phase_hint = "solving"
                if "solver" in agent or tool == "hitgene_evaluate":
                    self.milestones["solver_dispatched"] = True
                    self.milestones["solver_finished"] = False
                    self.milestones["plan_confirmed"] = True
            elif "data" in agent or (tool == "skill" and "data" in str(inp.get("name") or "")):
                self.milestones["data_checked"] = True
            elif tool in ("project_attribution", "apply_patch", "write"):
                self.milestones["plan_prepared"] = True
        if etype == "tool_use":
            self.tail_text = []
            if p.get("tool") == "evolve_create":
                self.evolve_property = (p.get("input") or {}).get("property") or {}
        elif etype == "tool_result":
            self.tail_text = []
            result = result_text(p)
            tool_name = p.get("tool") or self.tool_calls.get(p.get("id"))
            if tool_name in ("agent", "agent_wait"):
                for match in re.finditer(r'<worker_result\s+([^>]+)>(.*?)</worker_result>', result, re.S):
                    attrs = dict(re.findall(r'(\w+)="([^"]*)"', match[1]))
                    body = re.search(r'<result>(.*?)</result>', match[2], re.S)
                    title = re.search(r'<description>(.*?)</description>', match[2], re.S)
                    if attrs.get("worker_id") and body:
                        title_text = title[1].strip() if title else "子任务结果"
                        self.subtask_results[attrs["worker_id"]] = {
                            "title": title_text,
                            "status": attrs.get("status"), "report": body[1].strip(),
                            "scope": "subtask_only_not_final_delivery"}
                        if "核验" in title_text or "评估" in title_text or "evaluat" in title_text.lower():
                            self.milestones["evaluator_finished"] = True
                        elif "报告" in title_text or "可视化" in title_text or "report" in title_text.lower():
                            pass
                        elif self.milestones["solver_dispatched"]:
                            self.milestones["solver_finished"] = True
                        if len(self.subtask_results) > 4:
                            del self.subtask_results[next(iter(self.subtask_results))]
            self.evolution.observe(tool_name, result, ts)
            if "<approval_granted" in result:
                self.pending = None
                self.milestones["plan_confirmed"] = True
            elif "<approval_rejected" in result:
                self.pending = None
            pend = parse_pending(result)
            if pend:
                self.pending = pend
                if pend.get("name") == "evolve_create":
                    self.milestones["evolve_triggered"] = True
                else:
                    self.milestones["plan_prepared"] = True
        elif etype == "text":
            c = content_text(p)
            if c:
                self.tail_text.append(c)
                visible, clarify, artifacts = split_blocks(c)
                if clarify is not None:
                    self.milestones["clarify_asked"] = True
                if artifacts:
                    self.milestones["delivered_artifacts"] = True
                if visible and (not self.business_messages or self.business_messages[-1] != visible):
                    self.business_messages.append(visible)

    def final_text(self):
        """Return primary-agent text collected since its last tool call."""
        return "\n\n".join(t.strip() for t in self.tail_text if t.strip())


def parse_pending(text):
    """Extract a pending approval ID and optional plan-file metadata from tool output."""
    m = re.search(r"<approval_pending\s+([^>]*?)\s*/?>", text)
    if not m:
        return None
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    if not attrs.get("id"):
        return None
    plan = {}
    pm = re.search(r"<approval_plan>\s*(.*?)\s*</approval_plan>", text, re.S)
    if pm:
        try:
            items = json.loads(pm.group(1))
            plan = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
        except (ValueError, IndexError, AttributeError):
            plan = {}
    return {
        "id": attrs["id"],
        "kind": attrs.get("kind"),
        "name": attrs.get("name"),
        "plan_file_id": plan.get("fileId"),
        "plan_file_name": os.path.basename(plan.get("path") or "") or "PLAN.md",
    }


def split_blocks(text):
    """拆出 <clarify> / <artifacts>，其余作为说的话。"""
    clarify = None
    m = re.search(r"<clarify>\s*(.*?)\s*</clarify>", text, re.S)
    if m:
        try:
            clarify = json.loads(m.group(1))
        except ValueError:
            clarify = m.group(1)
    artifacts = []
    for am in re.finditer(r"<artifacts>\s*(.*?)\s*</artifacts>", text, re.S):
        try:
            parsed = json.loads(am.group(1))
            if isinstance(parsed, list):
                artifacts += [a for a in parsed if isinstance(a, dict)]
        except ValueError:
            pass
    say = text
    for tag in TAG_BLOCKS:
        say = re.sub(rf"<{tag}>.*?</{tag}>", "", say, flags=re.S)
    say = re.sub(r"\n{3,}", "\n\n", say).strip()
    return say, clarify, artifacts

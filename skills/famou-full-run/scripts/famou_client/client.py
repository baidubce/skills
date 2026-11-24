"""CLI orchestration: one mutation, bounded observation, then an explicit host action."""
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

import famou_config
from .delivery import add_links, text_output
from .interaction import observation, follow_cloud_evolution
from .protocol import Turn, STATUS_EVENTS, read_events
from .state import Context, ReceiptStore
from .transport import CONNECT_TIMEOUT, ContentUnsafeError, FamouError, QuotaError, Transport


AGENT_TYPE = "opencode/studio"
QUIET_SECONDS = 3.0


class Client:
    """Orchestrate CLI actions, bounded SSE consumption and receipt persistence."""

    def __init__(self, transport=None, receipts=None):
        """Initialize the CLI client with HTTP transport and local receipt storage."""
        self.transport = transport or Transport()
        self.receipts = receipts or ReceiptStore()
        self.context = None

    def consume(self, ctx, resp, probe=False, replaying=False):
        """Replay fully before deciding. Reconnect only the read-only subscription."""
        delay, seen = 1.0, set()
        attempted_gaps = set()
        pending_gap = False
        deadline_limited = False
        last_event_at = None

        def timeout_fn():
            """Compute the socket read timeout for the next SSE line."""
            nonlocal deadline_limited
            left = ctx.deadline - time.monotonic()
            snapshot = ctx.turn.evolution.snapshot()
            done = ctx.turn.done and not follow_cloud_evolution(ctx)
            quiet = probe or done
            deadline_limited = not quiet or left <= QUIET_SECONDS
            return min(QUIET_SECONDS, left) if quiet else left

        while True:
            result, got = {}, 0
            recover_gap = False
            try:
                for eid, etype, data in read_events(resp, timeout_fn, result):
                    got += 1
                    last_event_at = time.monotonic()
                    if etype == "error" and "payload" not in data:
                        raise FamouError(f"事件订阅失败：{data.get('code', '')} {data.get('message', '')}")
                    if etype == "resync":
                        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
                        from_seq = data.get("from_seq") if data.get("from_seq") is not None else payload.get("from_seq")
                        to_seq = data.get("to_seq") if data.get("to_seq") is not None else payload.get("to_seq")
                        gap = (from_seq, to_seq)
                        if gap not in attempted_gaps and len(attempted_gaps) < 2:
                            attempted_gaps.add(gap)
                            recover_gap = True
                            break
                        pending_gap = True
                        continue
                    payload = data.get("payload")
                    if isinstance(payload, dict) and etype in (None, "session/event"):
                        etype = payload.get("type", etype)
                    if eid and etype not in STATUS_EVENTS:
                        if eid in seen:
                            continue
                        seen.add(eid)
                        ctx.cursor = eid
                    if etype == "user/message":
                        # A missing event in an earlier turn doesn't invalidate the latest turn.
                        pending_gap = False
                    ctx.turn.feed(etype, data)
            finally:
                resp.close()
            if recover_gap:
                if time.monotonic() >= ctx.deadline:
                    ctx.history_incomplete = True
                    return
                resp = self.transport.subscribe(ctx.session_id, ctx.cursor)
                continue
            if replaying:
                # A deadline reached while historical events are still arriving is not
                # proof that an old idle/approval belongs to the current turn.
                recent_events = last_event_at is None or time.monotonic() - last_event_at < QUIET_SECONDS
                ctx.history_incomplete = bool(pending_gap or result.get("cut_id") or result.get("end") == "error" or
                                              (result.get("end") == "timeout" and deadline_limited and recent_events))
            elif pending_gap:
                ctx.history_incomplete = True
            if (
                result.get("end") == "timeout"
                or probe
                or (ctx.turn.done and not follow_cloud_evolution(ctx) and not ctx.history_incomplete)
            ):
                return
            if replaying and pending_gap and ctx.turn.done and result.get("end") == "eof":
                return
            if got:
                delay = 1.0
            if ctx.deadline - time.monotonic() <= delay + CONNECT_TIMEOUT:
                if replaying:
                    ctx.history_incomplete = True
                return
            time.sleep(delay)
            delay = min(delay * 2, 10.0)
            resp = self.transport.subscribe(ctx.session_id, ctx.cursor)

    def replay(self, ctx, probe=False):
        """Replay session events from the start in read-only mode."""
        ctx.turn = Turn()
        self.consume(ctx, self.transport.subscribe(ctx.session_id), probe=probe, replaying=True)

    def payload(self, ctx):
        """Build the structured JSON observation, optional cost estimate and delivery links."""
        ctx.request_id = self.transport.last_request_id
        result = observation(ctx)
        pending = result["pending_approval"]
        result["evolution_estimate"] = (
            self.transport.evolve_estimate(ctx.turn.evolve_property or {})
            if pending and pending.get("name") == "evolve_create" and not ctx.interrupted
            else None
        )
        # Most polls don't need a ticket. Tickets expire while the host is still polling.
        enabled = not ctx.interrupted and (ctx.links == "all" or
                  (ctx.links == "auto" and result["interaction"]["action"] != "continue_wait"))
        return add_links(result, self.transport, enabled)

    def report(self, ctx):
        """Build, persist and print the current session observation."""
        result = self.payload(ctx)
        self.receipts.save(ctx, result)
        self.emit(ctx, result)
        return result

    @staticmethod
    def emit(ctx, result):
        """Print the observation payload in JSON or plain-text mode."""
        text = json.dumps(result, ensure_ascii=False) if ctx.output_format == "json" else text_output(result)
        print(text, flush=True)

    def report_error(self, kind, error, requires_user_input=None):
        """Emit a redacted structured error payload without signing tickets."""
        ctx = self.context or Context()
        message = str(error)
        try:
            key = famou_config.get_api_key(required=False)
        except famou_config.ApiKeyError:
            key = None
        if key:
            message = message.replace(key, "[REDACTED]")
        ctx.request_id = self.transport.last_request_id
        self.receipts.save(ctx)
        need_input = (kind == "quota_error") if requires_user_input is None else bool(requires_user_input)
        result = {"schema_version": 2, "status": kind, "phase": "error", "error": message,
                  "session_id": ctx.session_id, "request_id": ctx.request_id,
                  "retry_mutation": False, "requires_user_input": need_input,
                  "interaction": {"action": "report_error", "reason": kind,
                                  "notification_scheduled": False},
                  "continuation": None, "resume": ctx.continuation() if ctx.session_id else None}
        # Error delivery must not wait on another network service or expose tickets in diagnostics.
        add_links(result, self.transport, enabled=False)
        self.emit(ctx, result)

    def execute(self, args):
        """Dispatch one CLI command using adaptive or explicit SSE observation windows."""
        sid = getattr(args, "session", None)
        previous = self.receipts.load(sid)
        explicit_wait = args.wait_seconds is not None
        if explicit_wait:
            wait_seconds = args.wait_seconds
        elif args.mode == "peek":
            wait_seconds = 15
        elif args.cmd in ("start", "append", "confirm"):
            wait_seconds = 60
        else:
            wait_seconds = previous.get("next_wait_seconds") or 120
        ctx = Context(sid, args.cmd, mode=args.mode, wait_seconds=wait_seconds,
                      explicit_wait=explicit_wait, poll_budget=args.poll_budget,
                      output_format=args.format, links=args.links)
        self.context = ctx
        ctx.previous = previous
        if args.cmd == "doctor":
            url, headers = famou_config.request_config()
            result = {"status": "configured", "transport": "direct", "api_url": url,
                      "credential_present": bool(headers), "network_verified": False,
                      "channel": famou_config.CHANNEL, "skill_version": famou_config.SKILL_VERSION,
                      "state_directory": str(self.receipts.root)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.cmd == "sessions":
            print(json.dumps({"sessions": self.receipts.sessions()}, ensure_ascii=False, indent=2))
            return
        if args.cmd == "cancel":
            data = self.transport.request_json("/api/v1/sessions?Action=CancelSession", {"sessionId": ctx.session_id})
            remote_status = data.get("status") if isinstance(data, dict) else None
            valid_statuses = ("cancelled", "ended", "failed", "idle")
            if (
                not isinstance(data, dict)
                or data.get("sessionId") != ctx.session_id
                or remote_status not in valid_statuses
            ):
                raise FamouError("停止请求已返回，但未取得匹配的会话停止回执；不重复发送，先核实状态。")
            final_status = "cancelled" if remote_status == "cancelled" else "turn_complete"
            result = {
                "schema_version": 2, "session_id": ctx.session_id, "status": final_status,
                "phase": "cancelled", "turn_complete": True, "requires_user_input": False,
                "message": "服务端已确认停止当前会话回合；对话和已有文件保留。",
                "cancellation": {
                    "scope": "session_turn",
                    "remote_status": remote_status,
                    "experiments_cancelled": False,
                },
                "request_id": self.transport.last_request_id, "continuation": None,
                "interaction": {"action": "deliver", "summary": "远程会话已停止", "notification_scheduled": False},
                "update": {"fingerprint": "cancel:" + remote_status},
            }
            self.receipts.save(ctx, result)
            add_links(result, self.transport, enabled=args.links == "all")
            self.emit(ctx, result)
            return result
        if args.cmd == "links":
            names = args.file_name or args.file_id
            result = {"schema_version": 2, "session_id": ctx.session_id, "status": "links",
                      "phase": "links", "requires_user_input": False, "continuation": None,
                      "interaction": {"action": "deliver", "summary": "伐谋任务与文件查看入口",
                                      "notification_scheduled": False},
                      "artifacts": [{"file_id": fid, "name": name} for fid, name in zip(args.file_id, names)]}
            add_links(result, self.transport)
            self.emit(ctx, result)
            return

        if args.cmd == "wait":
            self.replay(ctx)
            return self.report(ctx)

        if args.cmd == "confirm":
            self.replay(ctx, probe=True)
            if ctx.history_incomplete:
                raise FamouError("会话回放尚未完成，无法核准当前审批；先用wait完整续查，不发送确认。")
            pending = ctx.turn.pending
            if not pending:
                raise FamouError("当前没有可确认的事项；先 wait 查看状态，业务答复用 append。")
            if args.approval_id != pending["id"]:
                raise FamouError("待确认项已变化；先 wait 查看当前方案，再确认对应 ID")
            try:
                resp, _ = self.transport.open_stream("/api/v1/sessions?Action=ConfirmApproval",
                                                      {"sessionId": ctx.session_id, "approvalId": pending["id"]})
            except FamouError as error:
                if "ErrApprovalAlreadyConfirmed" in str(error):
                    raise FamouError("该事项已经确认，勿再次确认；用 wait 查询原会话。") from None
                raise
        else:
            files = args.file or []
            images = args.image or []
            all_paths = [*files, *images]
            if all_paths:
                print("[伐谋] 正在上传任务附件。", file=sys.stderr, flush=True)
            pregen, uploaded = self.transport.upload(all_paths, ctx.session_id) if all_paths else (None, [])
            file_urls, image_urls = uploaded[:len(files)], uploaded[len(files):]
            body = {"messages": self.transport.user_message(args.text, file_urls, image_urls)}
            if args.cmd == "start":
                body["config"] = {"agentType": AGENT_TYPE}
                if pregen:
                    body["id"] = pregen
                resp, sid = self.transport.open_stream("/api/v1/sessions?Action=CreateSession", body)
                if not sid:
                    resp.close()
                    raise FamouError("创建请求已返回但缺少 X-Session-ID；保留 request_id 排查，不重复创建。")
                ctx.session_id = sid
            else:
                body["sessionId"] = ctx.session_id
                try:
                    resp, _ = self.transport.open_stream("/api/v1/sessions?Action=AppendMessages", body)
                except FamouError as error:
                    if "ErrSessionBusy" in str(error):
                        raise FamouError("消息未发出：伐谋正在处理原会话，请用 wait 查询；不要重复发送。") from None
                    raise
        ctx.request_id = self.transport.last_request_id
        self.receipts.save(ctx)
        ctx.deadline = time.monotonic() + ctx.wait_seconds
        previous_evolution = ctx.turn.evolution
        previous_milestones = dict(ctx.turn.milestones)
        ctx.turn = Turn()
        if args.cmd == "confirm":
            ctx.turn.evolution = previous_evolution
            ctx.turn.evolution.begin_turn()
            ctx.turn.milestones.update(previous_milestones)
            ctx.turn.milestones["plan_confirmed"] = True
            ctx.turn.phase_hint = "evolution_initializing" if pending.get("name") == "evolve_create" else "solving"
        elif args.cmd == "append":
            for key in previous.get("milestones") or ():
                if key in ctx.turn.milestones:
                    ctx.turn.milestones[key] = True
            if previous.get("status") == "needs_clarification":
                ctx.turn.milestones["clarify_asked"] = True
                ctx.turn.milestones["clarify_answered"] = True
        self.consume(ctx, resp)
        return self.report(ctx)


def parser():
    """Build the CLI argument parser for all public-skill subcommands."""
    ap = argparse.ArgumentParser(prog="famou.py", description="调用伐谋并返回可交互的云端任务状态")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("start", "创建一次任务"), ("append", "发送业务需求或澄清答复")):
        item = sub.add_parser(name, help=help_text)
        if name == "append":
            item.add_argument("session")
        item.add_argument("text", nargs="?")
        item.add_argument("--text-file", help="UTF-8 需求文件，替代 text")
        item.add_argument("--file", action="append", default=[])
        item.add_argument("--image", action="append", default=[], help="随消息发送的图片附件，支持多传")
    item = sub.add_parser("confirm", help="确认准确的审批事项")
    item.add_argument("session")
    item.add_argument("--approval-id", required=True)
    item = sub.add_parser("wait", help="只读查询会话；退出查询不会取消云端任务")
    item.add_argument("session")
    item = sub.add_parser("cancel", help="真正停止远端会话当前回合，保留对话和文件")
    item.add_argument("session")
    item = sub.add_parser("links", help="重新签发查看链接，不向会话发消息")
    item.add_argument("session")
    item.add_argument("--file-id", action="append", default=[])
    item.add_argument("--file-name", action="append", default=[], help="与--file-id按顺序对应的展示文件名")
    sub.add_parser("doctor", help="本机配置检查，不访问网络")
    sub.add_parser("sessions", help="找回当前环境的本机会话记录")
    for item in sub.choices.values():
        item.add_argument("--format", choices=("text", "json"), default="text")
        item.add_argument("--mode", choices=("interactive", "follow", "peek"), default="interactive",
                          help="interactive跟随云端完成本轮交互；follow跟到演化交付；peek只查一次")
        item.add_argument("--wait-seconds", type=int,
                          help="单次观察10–540秒，未指定时按60→120→180→240秒自适应；peek默认15秒")
        item.add_argument("--poll-budget", type=int, default=1, help=argparse.SUPPRESS)
        item.add_argument("--links", choices=("auto", "all", "none"), default="auto",
                          help="auto仅在交付/交还控制权时签链接；none不签发")
    return ap


def main(argv=None):
    """Parse CLI arguments, install interruption protection and dispatch one action."""
    ap = parser()
    args = ap.parse_args(argv)
    if args.wait_seconds is not None and not 10 <= args.wait_seconds <= 540:
        ap.error("--wait-seconds 必须在 10–540 之间")
    if not 0 <= args.poll_budget <= 1:
        ap.error("--poll-budget 必须为0或1，请沿用 continuation 中的值")
    if hasattr(args, "session") and not ReceiptStore.valid_id(args.session):
        ap.error("无效会话号")
    if args.cmd == "links" and args.file_name and len(args.file_name) != len(args.file_id):
        ap.error("--file-name数量须与--file-id一致")
    if args.cmd in ("start", "append"):
        if bool(args.text) == bool(args.text_file):
            ap.error("必须且只能提供 text 或 --text-file")
        if args.text_file:
            try:
                args.text = Path(args.text_file).expanduser().read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                ap.error("无法读取 UTF-8 需求文件")
        if not args.text.strip():
            ap.error("需求为空")
    client = Client()

    def interrupted(signum, frame):
        """Persist a local resume handle immediately on SIGINT or SIGTERM."""
        # No network operation in a signal handler. Save a resume handle before exiting.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        ctx = client.context
        if ctx is not None:
            ctx.interrupted = True
            if ctx.session_id:
                client.report(ctx)
            else:
                client.report_error("request_error", "本地请求被中断，尚未取得真实会话号；保留request_id排查，不重复创建。")
        os._exit(0)

    old = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in old:
            signal.signal(sig, interrupted)
        client.execute(args)
        return 0
    except QuotaError as error:
        client.report_error("quota_error", error)
    except ContentUnsafeError as error:
        client.report_error("request_error", error, requires_user_input=True)
    except (FamouError, famou_config.ApiKeyError) as error:
        client.report_error("request_error", error)
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)
    return 1

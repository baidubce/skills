"""Public API operations. Writes are sent once; the stream reader owns reconnects."""
import http.client
import io
import json
import mimetypes
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid

import famou_config

CONNECT_TIMEOUT = 30
MAX_UPLOAD_FILES = 30
QUOTA_CODES = ("ErrInsufficientQuota", "BusinessQuotaNotEnterprise", "InsufficientQuota")
QUOTA_REASONS = {
    "business_quota_not_enterprise": "当前账号还没有开通伐谋企业版，开通后才能继续使用",
    "insufficient_business_quota": "账号的伐谋可用额度已经用完，需要联系管理员增加额度，或等额度恢复",
    "member_quota_exceeded": "这个账号本周期能用的团队额度已经用完，需要联系管理员调整，或等下个周期",
}


class FamouError(Exception):
    """Report a client configuration, transport or protocol failure."""

    pass


class QuotaError(FamouError):
    """额度不足：发起一轮（start / append / confirm）时冻结额度失败。"""


class ContentUnsafeError(FamouError):
    """输入文本或图片未通过内容安全审核，需修改内容后再提交。"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward account credentials or replay POSTs through redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject redirects so credentials and mutating requests stay on the original endpoint."""
        return None


class Transport:
    """Direct HTTPS client for public-cloud session, upload, billing and ticket APIs."""

    def __init__(self):
        """Initialize a no-redirect HTTP opener and request-ID tracker."""
        self.http = urllib.request.build_opener(NoRedirect())
        self.last_request_id = None

    def make_request(self, path, data, extra_headers=None):
        """构造公有云 API Key 直连请求。"""
        try:
            base_url, auth = famou_config.request_config()
        except famou_config.ApiKeyError as e:
            raise FamouError(str(e))
        h = famou_config.client_headers()
        h["x-bce-request-id"] = f"famou-skill-{uuid.uuid4()}"
        if extra_headers:
            h.update(extra_headers)
        h.update(auth)
        return urllib.request.Request(base_url + path, data=data, method="POST", headers=h)

    def api_error(self, raw):
        """接口在流建立前出错时返回统一 JSON：{code, message, requestId}。"""
        try:
            d = json.loads(raw)
        except ValueError:
            return f"接口返回了无法解析的内容：{raw[:200]!r}"
        if not isinstance(d, dict):
            return None
        code = d.get("code")
        if code in QUOTA_CODES:
            reason = (d.get("data") or {}).get("reason")
            msg = QUOTA_REASONS.get(reason) or d.get("message") or "资源点不足，请及时充值"
            raise QuotaError(f"{msg}（{code}）")
        if code == "ErrContentUnsafe":
            msg = d.get("message") or "输入内容未通过安全审核"
            raise ContentUnsafeError(
                f"{msg}；请修改需求描述或附件后再试，不要原样重发（{code}，requestId={d.get('requestId')}）"
            )
        if code not in (None, "0", 0):
            rid = d.get("requestId")
            msg = d.get("message")
            if code in ("InvalidAPIKey", "InvalidHTTPAuthHeader"):
                return f"API Key 无效或缺失，请检查本机配置（{code}，requestId={rid}）"
            if code == "AccessDenied":
                return f"{code}: 该接口或参数仅限会话内云端调用，不可通过 API Key 直接请求（{msg}，requestId={rid}）"
            if code == "ErrRequestParamInvalid":
                return f"请求或上传参数校验失败：{msg}（{code}，requestId={rid}）"
            return f"{code}: {msg}（requestId={rid}）"
        return None

    def open_stream(self, path, body):
        """POST 一个 SSE 接口。成功返回 (响应, 会话号)；流前出错抛 FamouError。"""
        req = self.make_request(
            path,
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        self.last_request_id = req.get_header("X-bce-request-id")
        try:
            resp = self.http.open(req, timeout=CONNECT_TIMEOUT)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            fallback = "鉴权失败（HTTP 401）：请检查本机 API Key 是否有效" if e.code == 401 else f"HTTP {e.code}"
            raise FamouError(self.api_error(raw) or fallback)
        except (urllib.error.URLError, socket.timeout, http.client.HTTPException) as e:
            raise FamouError(
                f"请求结果未确认（{type(e).__name__}）；服务端可能已接收。"
                "不要自动重发创建、消息或确认；已有会话用 wait 续查，缺少会话号时用 request_id 排查"
            ) from None
        if "event-stream" not in resp.headers.get("Content-Type", ""):
            try:
                raw = resp.read().decode("utf-8", "replace")
            finally:
                resp.close()
            raise FamouError(self.api_error(raw) or f"接口没有返回事件流：{raw[:200]!r}")
        sid = resp.headers.get("X-Session-ID")
        # ⚠ 流前出错也可能是 200 + text/event-stream + 一段错误 JSON（实测额度不足时如此，带 Content-Length）。
        #   真正的事件流是分块传输、没有 Content-Length；有长度就整体读出来，先当错误 JSON 解析一次
        if resp.headers.get("Content-Length"):
            try:
                raw = resp.read()
            finally:
                resp.close()
            if raw.lstrip().startswith(b"{"):
                err = self.api_error(raw.decode("utf-8", "replace"))
                if err:
                    raise FamouError(err)
            resp = io.BytesIO(raw)
        return resp, sid

    def subscribe(self, sid, after=None):
        """Open a read-only event subscription, optionally resuming after an event ID."""
        body = {"sessionId": sid}
        if after:
            body["afterEventId"] = after
        return self.open_stream("/api/v1/sessions?Action=SubscribeEvents", body)[0]

    def request_json(self, path, body):
        """Send one JSON request; ambiguous writes are never retried here."""
        req = self.make_request(path, json.dumps(body, ensure_ascii=False).encode(),
                                {"Content-Type": "application/json"})
        self.last_request_id = req.get_header("X-bce-request-id")
        try:
            with self.http.open(req, timeout=CONNECT_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            raise FamouError(self.api_error(error.read().decode("utf-8", "replace")) or f"HTTP {error.code}") from None
        except (urllib.error.URLError, socket.timeout, http.client.HTTPException, OSError) as error:
            raise FamouError(f"请求结果未确认（{type(error).__name__}）；勿重复停止请求，先查询远端状态。") from None
        problem = self.api_error(raw)
        if problem:
            raise FamouError(problem)
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise FamouError("接口回执无法解析，操作结果尚未确认；先查询远端状态，不重复操作。") from None
        if not isinstance(parsed, dict) or "data" not in parsed:
            raise FamouError("接口未返回明确的操作回执，远端状态尚未确认。")
        return parsed["data"]

    def upload(self, paths, sid=None):
        """multipart 上传。返回 (会话号, [fileUrl])。"""
        if len(paths) > MAX_UPLOAD_FILES:
            raise FamouError(f"单次最多上传 {MAX_UPLOAD_FILES} 个文件，请分批或打包后重试")
        boundary = uuid.uuid4().hex
        parts = []
        if sid:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="sessionId"\r\n\r\n{sid}\r\n'.encode())
        for p in paths:
            # 提问工具、对话附件给的可能是 file:// URL，转成本地路径
            if p.startswith("file://"):
                p = urllib.parse.unquote(urllib.parse.urlparse(p).path)
            p = os.path.expanduser(p)
            if not os.path.isfile(p):
                raise FamouError(f"文件不存在：{p}")
            name = os.path.basename(p).replace('"', '%22').replace('\r', '%0D').replace('\n', '%0A')
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n".encode()
            )
            with open(p, "rb") as file:
                parts.append(file.read())
            parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = self.make_request(
            "/api/v1/sessions/files?Action=UploadSessionFile",
            b"".join(parts),
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        self.last_request_id = req.get_header("X-bce-request-id")
        try:
            raw = self.http.open(req, timeout=300).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            raise FamouError("上传失败：" + (self.api_error(raw) or f"HTTP {e.code}"))
        except (urllib.error.URLError, socket.timeout) as e:
            raise FamouError(f"上传失败，连不上伐谋接口：{e}")
        err = self.api_error(raw)
        if err:
            raise FamouError("上传失败：" + err)
        data = json.loads(raw)["data"]
        return data["sessionId"], [f["fileUrl"] for f in data["files"]]

    def user_message(self, text, file_urls, image_urls=None):
        """Build one user message containing the supplied text, files and optional images."""
        content = [{"type": "text", "text": text}]
        content += [{"type": "file", "url": u} for u in file_urls]
        content += [{"type": "image", "url": u} for u in (image_urls or ())]
        return [{"role": "user", "content": content}]

    def evolve_estimate(self, prop):
        """查深度演化要冻结的积分（4.3.8 withholding_fee，只估价、不冻结）。返回给【待确认】的几行文字。

        ⚠ evolveConfig 要和伐谋生成的 config.yaml 同构：轮数放在 evolve_config.max_iterations 下。
          按文档示例写在顶层，估价恒为 0（实测）。轮数和 GPU 取自 master 调 evolve_create 的 property。
        """
        iters, gpu = prop.get("max_iterations"), bool(prop.get("gpu"))
        lines = [f"  演化轮数：{iters if iters else '未知'} · GPU：{'使用' if gpu else '不使用'}"]
        if not iters:
            return lines + ["  预计冻结积分：查询失败（没有拿到演化轮数），以伐谋计费为准"]
        cfg = {"evolve_config": {"max_iterations": iters}, "gpu": gpu}
        try:
            req = self.make_request(
                "/api/v1/bill/withholding_fee",
                json.dumps({"evolveConfig": json.dumps(cfg)}).encode("utf-8"),
                {"Content-Type": "application/json"},
            )
            raw = self.http.open(req, timeout=15).read().decode("utf-8", "replace")
            d = json.loads(raw)
            if d.get("code") not in (None, "0", 0):
                raise ValueError(f"{d.get('code')}: {d.get('message')}")
            data = d.get("data") or {}
            cost = int(data["estimatedCost"])
        except Exception as e:
            return lines + [f"  预计冻结积分：查询失败（{e}），以伐谋计费为准"]
        # Cost estimation is not proof of an available balance or successful settlement.
        lines.append(f"  预计冻结积分：{cost:,}")
        available = data.get("availableCredits")
        if type(available) in (int, float):
            lines.append(f"  当前可用资源点：{int(available):,}")
        shortfall = data.get("shortfallCredits")
        recharge = data.get("rechargeUrl")
        if type(shortfall) in (int, float) and shortfall > 0:
            suffix = f"（充值：{recharge}）" if isinstance(recharge, str) and recharge else ""
            lines.append(f"  可用资源点缺口：{int(shortfall):,}{suffix}")
        return lines

    def issue_login_ticket(self):
        """签一张一次性网页登录 ticket（5 分钟有效、只能用一次）；签发失败返回 None，不影响主流程。"""
        try:
            req = self.make_request("/api/v1/users?Action=CreateLoginTicket", b"")
            d = json.loads(self.http.open(req, timeout=15).read().decode("utf-8", "replace"))
        except Exception:
            return None
        if not isinstance(d, dict) or d.get("code") not in (None, "0", 0):
            return None
        ticket = (d.get("data") or {}).get("ticket")
        return ticket if isinstance(ticket, str) and ticket else None

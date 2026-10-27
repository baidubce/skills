#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baidu Unified Document Parser — 标准版 Pipeline 4.0 + PaddleOCR-VL 1.6 统一入口

子命令:
  parse   解析文档；按文件/场景选路（或 --engine 指定），结果写入本地缓存并生成索引
  index   从已缓存的解析结果重建索引（身份/目录/页/要素/检索/门牌）
  search  在已缓存索引里按关键词检索正文，回到 页 + 门牌

鉴权: 环境变量 BAIDU_DOC_AI_API_KEY / BAIDU_DOC_AI_SECRET_KEY（AK/SK 换 access_token）
"""

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

OAUTH_URL = "https://aip.baidubce.com/oauth/2.0/token"

# ---- 引擎定义 ---------------------------------------------------------------
# standard = 文档解析标准版（Pipeline 4.0）；vlm = PaddleOCR-VL 1.6 多模态大模型
ENGINES: Dict[str, Dict[str, Any]] = {
    "standard": {
        "submit": "https://aip.baidubce.com/rest/2.0/brain/online/v2/parser/task",
        "query": "https://aip.baidubce.com/rest/2.0/brain/online/v2/parser/task/query",
        # bool 参数以字符串 True/False 下发
        "bool_params": (
            "recognize_formula", "analysis_chart", "angle_adjust",
            "parse_image_layout", "html_table_format",
        ),
        "str_params": ("language_type", "switch_digital_width", "version"),
    },
    "vlm": {
        "submit": "https://aip.baidubce.com/rest/2.0/brain/online/v2/paddle-vl-parser/task",
        "query": "https://aip.baidubce.com/rest/2.0/brain/online/v2/paddle-vl-parser/task/query",
        # 公式/图片/语种 VL 默认开启，无需下发
        "bool_params": (
            "analysis_chart", "merge_tables", "relevel_titles", "recognize_seal",
            "return_span_boxes", "erase_seal", "erase_watermark", "unwarp", "angle_adjust",
        ),
        "str_params": (),
    },
}
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
# 标准版支持格式（版式 + 流式）
STANDARD_EXTS = frozenset({
    ".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".ofd", ".ppt", ".pptx",
    ".doc", ".docx", ".txt", ".xls", ".xlsx", ".wps", ".html", ".mhtml",
})
# VL 支持格式（注意：不含 xls/xlsx）
VLM_EXTS = frozenset({
    ".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".ofd",
    ".doc", ".docx", ".txt", ".wps", ".ppt", ".pptx",
})
OFFICE_FLOW_EXTS = frozenset({
    ".doc", ".docx", ".txt", ".xls", ".xlsx", ".wps", ".ppt", ".pptx", ".html", ".mhtml",
})

FILE_DATA_LIMIT = 50 * 1024 * 1024   # base64 直传上限；更大走 file_url
SHORT_DOC_PAGES = 5                   # 页数 ≤ 该值视为短文，索引可内联正文
DEFAULT_POLL_INTERVAL = 5
DEFAULT_MAX_POLL_TIME = 300
RATE_LIMIT_RETRIES = 4                # 限流时同一任务重试次数（不重新提交）
# 索引/解析逻辑版本：进缓存签名，升级改逻辑时 +1，旧缓存自动失效、不残留旧结果
INDEX_SCHEMA_VERSION = "2"


# ---- 结构化错误：失败必须带 code / message / user_prompt ----------------------
# 约定：禁止只回「解析失败」，禁止 Agent 用散文猜，禁止静默换解析器/换引擎。
ERROR_PROMPTS: Dict[str, str] = {
    "AUTH_FORBIDDEN": "当前账号没有文档解析接口的调用权限，多为创建应用时未勾选相关文字识别接口。"
                      "请登录百度智能云控制台，找到对应应用→编辑→勾选文字识别相关接口后重新调用，"
                      "也可用权限额度诊断工具自助诊断：https://console.bce.baidu.com/tools/#/aiInterfacePermissions"
                      "（错误码说明 https://cloud.baidu.com/doc/OCR/s/wlqc0cfdq）。",
    "CREDENTIALS_REQUIRED": "没有可用的 API Key 或 Key 无效。请到 "
                            "https://console.bce.baidu.com/iam/#/iam/apikey/list 创建 API Key"
                            "（勾选「AI 开放能力」），拿到后把整串发回来；也可参考快速入门 "
                            "https://cloud.baidu.com/doc/OCR/s/Olpjnv9u9 。无效 Key 则请重新创建，不要改用其它方式读 PDF。",
    "FILE_NOT_FOUND": "找不到这个文件。请确认还在、给的是完整路径，或重新拖进对话。",
    "UNSUPPORTED_TYPE": "目前支持 PDF / Word / PPT / Excel / txt / 常见图片等。请换成其中一种，或先另存为 PDF。",
    "FILE_TOO_LARGE": "文件超过接口上限。可以：压缩后再传、改用文件 URL、或告诉我只要哪几页（例如 1–20 页）。",
    "PAGE_RANGE_INVALID": "页码超出范围。请改成实际页数内的区间。",
    "NOT_CACHED": "这份文件还没解析。请先对它跑一次 parse，再检索或取结果。",
    "QUOTA_EXCEEDED": "账号额度用完了。请到控制台开通或充值后再说一声："
                      "https://console.bce.baidu.com/ai/#/ai/ocr/overview/index",
    "RATE_LIMIT": "当前请求较多，我过几秒自动再试，不用重新上传。",
    "TIMEOUT": "这份文件比较大，还在处理。请稍等；或告诉我先看哪几页。",
    "BACKEND_UNAVAILABLE": "云端解析暂时没成功。可以稍后重试，或换一种解析方式（办公件走标准版，扫描件走 VL）。",
    "TASK_FAILED": "打不开这份文件（有时是加密或损坏）。请确认能正常打开，或导出一份未加密 PDF 再试。",
}

# 百度 API error_code → 本技能 code（未命中默认 BACKEND_UNAVAILABLE）
API_CODE_MAP: Dict[str, str] = {
    # 6=无 API 访问权限；282006=用户权限校验失败（账号未开通该能力）——都归引导开通
    "6": "AUTH_FORBIDDEN", "282006": "AUTH_FORBIDDEN",
    "14": "CREDENTIALS_REQUIRED", "100": "CREDENTIALS_REQUIRED",
    "110": "CREDENTIALS_REQUIRED", "111": "CREDENTIALS_REQUIRED",
    "17": "QUOTA_EXCEEDED", "19": "QUOTA_EXCEEDED", "282005": "QUOTA_EXCEEDED",
    "4": "RATE_LIMIT", "18": "RATE_LIMIT", "282018": "RATE_LIMIT",
    "216200": "FILE_NOT_FOUND",
    "216201": "UNSUPPORTED_TYPE",
    "216202": "FILE_TOO_LARGE", "282114": "FILE_TOO_LARGE",
    "282111": "FILE_NOT_FOUND", "282112": "FILE_NOT_FOUND", "282113": "FILE_NOT_FOUND",
}


class SkillError(Exception):
    """带下一步的失败：code 给 Agent 分支，message 给 Agent，user_prompt 给人看。"""

    def __init__(self, code: str, message: str, details: Optional[dict] = None,
                 user_prompt: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.user_prompt = user_prompt or ERROR_PROMPTS.get(code, message)
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"ok": False, "code": self.code, "message": self.message,
                "user_prompt": self.user_prompt, "details": self.details}


def api_error(action: str, code: Any, msg: str, log_id: Any = None) -> SkillError:
    skill_code = API_CODE_MAP.get(str(code), "BACKEND_UNAVAILABLE")
    message = f"{action}: {msg} (error_code={code}" + (f", log_id={log_id})" if log_id else ")")
    return SkillError(skill_code, message, {"api_error_code": str(code), "log_id": log_id})


def log(msg: str) -> None:
    print(msg, file=sys.stderr)



def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def cache_root() -> Path:
    base = os.environ.get("BAIDU_DOC_PARSER_CACHE")
    return Path(base) if base else (Path.home() / ".cache" / "baidu-doc-parser")


def decide_engine(ext: str, explicit: Optional[str]) -> str:
    """选路：用户点名以用户为准；否则按文件类型粗选。

    图片 → VL；Office/流式 → 标准；PDF/OFD → 默认标准（可编辑件）。
    扫描 PDF、需版面框/行坐标/印章等场景由 SKILL.md 指引 Agent 显式传 --engine vlm。
    """
    if explicit and explicit != "auto":
        if explicit not in ENGINES:
            raise ValueError(f"未知引擎 '{explicit}'，可选 standard / vlm / auto")
        return explicit
    if ext in IMAGE_EXTS:
        return "vlm"
    return "standard"


def validate_format(ext: str, engine: str) -> None:
    allowed = STANDARD_EXTS if engine == "standard" else VLM_EXTS
    if ext not in allowed:
        if engine == "vlm" and ext in {".xls", ".xlsx"}:
            raise SkillError("UNSUPPORTED_TYPE",
                             f"PaddleOCR-VL 不支持 Excel（{ext}），Excel 请用 --engine standard",
                             {"ext": ext, "engine": engine})
        raise SkillError("UNSUPPORTED_TYPE",
                         f"引擎 {engine} 不支持格式 '{ext}'，支持: {', '.join(sorted(allowed))}",
                         {"ext": ext, "engine": engine})


def fetch_token(api_key: str, secret_key: str) -> str:
    resp = requests.post(
        OAUTH_URL,
        params={"grant_type": "client_credentials", "client_id": api_key, "client_secret": secret_key},
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        # invalid_client / unknown client id 等都是凭据问题
        raise SkillError("CREDENTIALS_REQUIRED",
                         f"获取 access_token 失败: {data.get('error_description') or data}",
                         {"oauth_error": data.get("error")})
    return data["access_token"]


def resolve_auth() -> tuple:
    """鉴权二选一，返回 (mode, cred)：

    - 配 AK + SK（BAIDU_DOC_AI_API_KEY + BAIDU_DOC_AI_SECRET_KEY）→ OAuth 换 access_token，
      ('token', access_token)，调用时拼 ?access_token=。
    - 只配 API Key（BAIDU_DOC_AI_API_KEY，不配 SK；或显式 BAIDU_DOC_AI_BEARER_TOKEN）→
      新版统一鉴权，('bearer', api_key)，调用时带 Authorization: Bearer。
    """
    bearer = os.getenv("BAIDU_DOC_AI_BEARER_TOKEN")
    if bearer:
        return ("bearer", bearer)
    api_key = os.getenv("BAIDU_DOC_AI_API_KEY")
    secret_key = os.getenv("BAIDU_DOC_AI_SECRET_KEY")
    if api_key and secret_key:
        return ("token", fetch_token(api_key, secret_key))
    if api_key:  # 只给了单串 API Key → 当 Bearer 用
        return ("bearer", api_key)
    raise SkillError("CREDENTIALS_REQUIRED",
                     "未配置鉴权：请提供 AK/SK（BAIDU_DOC_AI_API_KEY + BAIDU_DOC_AI_SECRET_KEY）"
                     "或 API Key（BAIDU_DOC_AI_API_KEY / BAIDU_DOC_AI_BEARER_TOKEN）其一")


def apply_auth(base_url: str, auth: tuple) -> tuple:
    """按鉴权模式返回 (请求 url, 额外请求头)。"""
    mode, cred = auth
    if mode == "token":
        return f"{base_url}?access_token={cred}", {}
    return base_url, {"Authorization": f"Bearer {cred}"}



def submit_task(engine: str, auth: tuple, file_name: str,
                file_data: Optional[str], file_url: Optional[str],
                extra: Dict[str, Any]) -> str:
    cfg = ENGINES[engine]
    url, auth_headers = apply_auth(cfg['submit'], auth)
    params: Dict[str, str] = {"file_name": file_name}
    if file_data:
        params["file_data"] = file_data
    elif file_url:
        params["file_url"] = file_url
    else:
        raise SkillError("BACKEND_UNAVAILABLE", "file_data / file_url 必须二选一")
    for key, value in extra.items():
        if value is None:
            continue
        if isinstance(value, bool):
            params[key] = "True" if value else "False"
        elif isinstance(value, (dict, list)):
            params[key] = json.dumps(value, ensure_ascii=False)
        else:
            params[key] = str(value)
    resp = requests.post(url, data=params,
                         headers={"Content-Type": "application/x-www-form-urlencoded", **auth_headers},
                         timeout=DEFAULT_MAX_POLL_TIME)
    result = resp.json()
    code = result.get("error_code", 0)
    if code not in (0, "0"):
        raise api_error("提交任务失败", code, result.get("error_msg", "unknown"), result.get("log_id"))
    task_id = (result.get("result") or {}).get("task_id")
    if not task_id:
        raise SkillError("BACKEND_UNAVAILABLE", "提交任务未返回 task_id")
    return task_id


def submit_with_retry(engine: str, auth: tuple, file_name: str,
                      file_data: Optional[str], file_url: Optional[str],
                      extra: Dict[str, Any]) -> str:
    """提交任务；仅在 RATE_LIMIT 时退避重试，其它错误原样抛出。"""
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            return submit_task(engine, auth, file_name, file_data, file_url, extra)
        except SkillError as err:
            if err.code != "RATE_LIMIT" or attempt == RATE_LIMIT_RETRIES:
                raise
            wait = DEFAULT_POLL_INTERVAL * attempt
            log(f"[限流] 提交被限流，{wait}s 后重试（{attempt}/{RATE_LIMIT_RETRIES}）")
            time.sleep(wait)
    raise SkillError("RATE_LIMIT", "提交任务持续被限流")

def poll_task(engine: str, auth: tuple, task_id: str,
              interval: int = DEFAULT_POLL_INTERVAL,
              max_poll_time: int = DEFAULT_MAX_POLL_TIME) -> Dict[str, Any]:
    cfg = ENGINES[engine]
    url, auth_headers = apply_auth(cfg['query'], auth)
    time.sleep(interval)
    start = time.time()
    while time.time() - start < max_poll_time:
        resp = requests.post(url, data={"task_id": task_id},
                             headers={"Content-Type": "application/x-www-form-urlencoded", **auth_headers},
                             timeout=DEFAULT_MAX_POLL_TIME)
        payload = resp.json()
        code = payload.get("error_code", 0)
        if code not in (0, "0"):
            err = api_error("查询任务失败", code, payload.get("error_msg", "unknown"), payload.get("log_id"))
            # 限流只是查询被挡，任务还在：等一下用同一任务再查，绝不重新提交
            if err.code == "RATE_LIMIT":
                log(f"[限流] 查询被限流，{interval}s 后用同一任务重试")
                time.sleep(interval)
                continue
            err.details["task_id"] = task_id
            raise err
        result = payload.get("result") or {}
        status = result.get("status")
        if status == "success":
            return result
        if status == "failed" or result.get("task_error"):
            raise SkillError("TASK_FAILED", f"解析失败: {result.get('task_error') or status}",
                             {"task_id": task_id, "engine": engine, "task_error": result.get("task_error")})
        log(f"状态: {status}（已等待 {int(time.time() - start)}s）")
        time.sleep(interval)
    raise SkillError("TIMEOUT", f"轮询超时：超过 {max_poll_time} 秒",
                     {"task_id": task_id, "engine": engine})



def download(url: str) -> str:
    resp = requests.get(url, timeout=DEFAULT_MAX_POLL_TIME)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def markdown_from_pages(pages: List[dict]) -> str:
    parts = []
    for page in sorted((p for p in pages if isinstance(p, dict)),
                       key=lambda p: p.get("page_num", 0)):
        text = (page.get("markdown") or page.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def fetch_outputs(result: Dict[str, Any]) -> (str, dict):
    """返回 (markdown, parse_result_json)。markdown 缺失时用逐页 JSON 兜底。"""
    raw: dict = {}
    detail_url = result.get("parse_result_url")
    if detail_url:
        try:
            raw = json.loads(download(detail_url))
        except (ValueError, AttributeError):
            raw = {}
    markdown = ""
    md_url = result.get("markdown_url")
    if md_url:
        markdown = download(md_url).strip()
    if not markdown and isinstance(raw.get("pages"), list):
        markdown = markdown_from_pages(raw["pages"])
    if not markdown and not raw:
        raise SkillError("BACKEND_UNAVAILABLE",
                         "接口报成功但 markdown_url / parse_result_url 都取不到内容")
    return markdown, raw


# ---- 索引构建 ---------------------------------------------------------------
# 目录只收真标题；页眉/页脚/页码/目录页不进索引正文与目录（约定：假标题、页眉页脚不进目录）
TITLE_TYPES = frozenset({"title", "doc_title", "paragraph_title"})
FORMULA_TYPES = frozenset({"formula", "display_formula", "inline_formula", "formula_number"})
SKIP_TYPES = frozenset({"head_tail", "header", "footer", "header_image",
                        "footer_image", "number", "contents", "content"})
IMAGE_TYPES = frozenset({"image", "chart"})


def _door(engine: str, h12: str, page_num: int, block: str) -> str:
    """门牌：引擎#内容哈希:p页码:块（约定两份结果并存时带引擎前缀）。"""
    return f"{engine}#{h12}:p{page_num}:{block}"


def _title_level(sub_type: str, type_: str) -> int:
    if type_ == "doc_title":
        return 1
    digits = "".join(ch for ch in (sub_type or "") if ch.isdigit())
    if digits:
        return int(digits)
    return 2


def _clip(text: str, limit: int = 1000) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def build_index(raw: dict, identity: dict) -> dict:
    engine = identity["engine"]
    h12 = identity["content_hash"][:12]
    pages = [p for p in (raw.get("pages") or []) if isinstance(p, dict)]
    pages.sort(key=lambda p: p.get("page_num", 0))

    # Excel 多 Sheet：云端对每个 sheet 返回一页，但 page_num 都是 0。
    # 页号重复时按顺序重新编号（0 基），让每个 sheet/页都能被门牌唯一定位。
    raw_nums = [p.get("page_num", 0) for p in pages]
    renumber = len(set(raw_nums)) < len(raw_nums)

    toc: List[dict] = []
    page_flags: List[dict] = []
    elements: List[dict] = []
    search: List[dict] = []

    for idx, page in enumerate(pages):
        pn = idx if renumber else page.get("page_num", 0)
        layouts = page.get("layouts") or []
        tables = page.get("tables") or []
        images = page.get("images") or []
        flags = {"page_num": pn, "has_text": False, "has_table": bool(tables),
                 "has_image": bool(images), "has_formula": False, "has_seal": False}

        # Excel：每个 sheet 对应一页，sheet 名作为一级目录，便于按 sheet 名定位
        sheet_name = ((page.get("meta") or {}).get("sheet_name") or "").strip()
        if sheet_name:
            toc.append({"title": _clip(sheet_name, 200), "level": 1, "page_num": pn,
                        "door_id": _door(engine, h12, pn, "sheet"), "kind": "sheet"})

        for lay in layouts:
            t = lay.get("type")
            st = lay.get("sub_type") or ""
            lid = lay.get("layout_id") or f"layout-{len(search)}"
            text = (lay.get("text") or "").strip()
            if t in SKIP_TYPES:
                continue
            door = _door(engine, h12, pn, lid)
            if t in TITLE_TYPES:
                flags["has_text"] = True
                toc.append({"title": _clip(text, 200), "level": _title_level(st, t),
                            "page_num": pn, "door_id": door})
            if t in FORMULA_TYPES:
                flags["has_formula"] = True
                elements.append({"kind": "formula", "page_num": pn,
                                 "door_id": door, "desc": _clip(text, 120)})
            if t == "seal":
                flags["has_seal"] = True
                elements.append({"kind": "seal", "page_num": pn,
                                 "door_id": door, "desc": _clip(text, 120) or "印章"})
            if t in IMAGE_TYPES:
                flags["has_image"] = True
            if text and t not in TITLE_TYPES:
                flags["has_text"] = True
                search.append({"door_id": door, "page_num": pn, "type": t, "text": _clip(text)})

        for tb in tables:
            lid = tb.get("layout_id") or f"table-{len(elements)}"
            md = (tb.get("markdown") or "").strip()
            first = md.splitlines()[0] if md else "表格"
            desc = _clip(first, 120)
            if tb.get("merge_table"):
                desc = f"[跨页-{tb['merge_table']}] " + desc
            elements.append({"kind": "table", "page_num": pn,
                             "door_id": _door(engine, h12, pn, lid), "desc": desc})
        for im in images:
            lid = im.get("layout_id") or f"image-{len(elements)}"
            idesc = (im.get("image_description") or "").strip()
            kind = "chart" if idesc else "image"
            elements.append({"kind": kind, "page_num": pn,
                             "door_id": _door(engine, h12, pn, lid),
                             "desc": _clip(idesc, 160) or "图片"})

        page_flags.append(flags)

    identity = {**identity, "page_count": len(pages)}
    index = {
        "identity": identity,         # 身份：哈希/文件名/页数/引擎/页范围/解析时间
        "toc": toc,                   # 目录：标题/层级/页码/门牌
        "pages": page_flags,          # 页：每页有无 字/表/图/公式/章
        "elements": elements,         # 要素：表/图/公式/印章/图表 的页码+短描述+门牌
        "search": search,             # 检索：正文片段 → 页 + 门牌
        "notes": {
            "convention": "按文件内容认文件；门牌带引擎前缀；仅已解析页可检索；页眉页脚假标题不入目录",
            "short_doc": len(pages) <= SHORT_DOC_PAGES,
        },
    }
    return index
# ---- 缓存与选参 -------------------------------------------------------------
def content_hash_of(file_path: Optional[str], file_url: Optional[str]) -> str:
    if file_path:
        h = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    return "url-" + hashlib.sha256((file_url or "").encode("utf-8")).hexdigest()


def parse_page_range(spec: Optional[str]) -> Optional[List[int]]:
    """'1-10' / '3' / '1-3,7' → 升序页码列表（1 基）。None 表示全文。"""
    if not spec:
        return None
    pages: set = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return sorted(p for p in pages if p > 0)


def build_extra(engine: str, args: argparse.Namespace) -> Dict[str, Any]:
    """按引擎收集该引擎支持的参数（None 的不下发）。"""
    cfg = ENGINES[engine]
    allowed = set(cfg["bool_params"]) | set(cfg["str_params"])
    extra: Dict[str, Any] = {}
    for name in allowed:
        val = getattr(args, name, None)
        if val is not None:
            extra[name] = val
    if getattr(args, "chunk", False):
        extra["return_doc_chunks"] = {"switch": True, "split_type": "chunk", "chunk_size": -1}
    return extra


def cache_key(content_hash: str, engine: str, page_range: Optional[List[int]],
              extra: Dict[str, Any]) -> str:
    ident = json.dumps({"v": INDEX_SCHEMA_VERSION, "pr": page_range, "ex": extra},
                       sort_keys=True, ensure_ascii=False)
    sig = hashlib.sha256(ident.encode("utf-8")).hexdigest()[:10]
    return f"{content_hash[:12]}_{engine}_{sig}"
def slice_pages(raw: dict, page_range: Optional[List[int]]) -> dict:
    """按 1 基页码裁剪 raw.pages（page_num 为 0 基）。无交集则原样返回全文。"""
    if not page_range:
        return raw
    wanted = {p - 1 for p in page_range}
    pages = [p for p in (raw.get("pages") or []) if p.get("page_num", 0) in wanted]
    if not pages:
        return raw
    return {**raw, "pages": pages}


def _page_has_text(page: dict) -> bool:
    """页是否有正文：先看页级 text，再回退到任一 layout 的 text。"""
    if (page.get("text") or page.get("markdown") or "").strip():
        return True
    return any((lay.get("text") or "").strip() for lay in (page.get("layouts") or []))


def scan_hint(engine: str, raw: dict) -> Optional[dict]:
    """标准版遇疑似扫描件/空正文 → 返回 LOW_TEXT_QUALITY 警告（不是失败，不自动换引擎）。"""
    if engine != "standard":
        return None
    pages = raw.get("pages") or []
    if not pages:
        return None
    scanned = sum(1 for p in pages if (p.get("meta") or {}).get("is_scan"))
    textful = sum(1 for p in pages if _page_has_text(p))
    if scanned >= max(1, len(pages) // 2) or textful == 0:
        return {
            "code": "LOW_TEXT_QUALITY",
            "message": "标准版检测到疑似扫描件/正文偏空（未自动换引擎）",
            "user_prompt": "这页文字很少或像扫描件。如果结果不对，说一声我改用 VL 再解析一次。",
        }
    return None



def do_parse(args: argparse.Namespace) -> dict:
    file_path = args.file_path
    file_url = args.file_url
    if bool(file_path) == bool(file_url):
        raise SkillError("FILE_NOT_FOUND", "必须且只能提供 file_path 或 file_url 之一")

    file_name = args.file_name or (os.path.basename(file_path) if file_path
                                   else os.path.basename(urlparse(file_url).path) or "document.pdf")
    ext = os.path.splitext(file_name)[1].lower()
    engine = decide_engine(ext, args.engine)
    validate_format(ext, engine)

    # 本地文件：先确认存在/非空/未超限（哈希与直传都依赖它）
    if file_path:
        if not os.path.isfile(file_path):
            raise SkillError("FILE_NOT_FOUND", f"本地文件不存在: {file_path}", {"file_path": file_path})
        size = os.path.getsize(file_path)
        if size == 0:
            raise SkillError("FILE_NOT_FOUND", f"本地文件为空: {file_path}", {"file_path": file_path})
        if size > FILE_DATA_LIMIT:
            raise SkillError("FILE_TOO_LARGE",
                             f"文件 {size/1024/1024:.1f}M 超过 50M 直传上限，请改用 file_url",
                             {"size_mb": round(size / 1024 / 1024, 1)})

    try:
        page_range = parse_page_range(args.page_range)
    except (ValueError, TypeError):
        raise SkillError("PAGE_RANGE_INVALID", f"页范围格式错误: {args.page_range}",
                         {"page_range": args.page_range})

    extra = build_extra(engine, args)
    chash = content_hash_of(file_path, file_url)
    key = cache_key(chash, engine, page_range, extra)
    cdir = cache_root() / key
    index_file = cdir / "index.json"

    # 一次解析，多次使用：同内容+同引擎+同页范围+同参数命中缓存直接读本地
    if index_file.exists() and not args.force and not args.resume_task:
        log(f"[缓存命中] {cdir}")
        index = json.loads(index_file.read_text(encoding="utf-8"))
        index["identity"]["reused"] = True
        return {"ok": True, "cache_dir": str(cdir), "index": index,
                "warnings": index.get("warnings", []),
                "markdown_file": str(cdir / "markdown.md")}

    auth = resolve_auth()
    if args.resume_task:
        task_id = args.resume_task
        log(f"复用已有任务（不重新提交）: {task_id}")
    else:
        file_data = None
        if file_path:
            with open(file_path, "rb") as fh:
                file_data = base64.b64encode(fh.read()).decode("ascii")
        log(f"引擎={engine} 文件={file_name} 参数={extra or '默认'}")
        task_id = submit_with_retry(engine, auth, file_name, file_data, file_url, extra)
        log(f"任务已提交: {task_id}")

    result = poll_task(engine, auth, task_id)
    markdown, raw = fetch_outputs(result)
    warnings = [w for w in [scan_hint(engine, raw)] if w]

    page_count = len(raw.get("pages") or [])
    if page_range and page_count and all(p > page_count for p in page_range):
        raise SkillError("PAGE_RANGE_INVALID",
                         f"页码 {args.page_range} 超出文档实际 {page_count} 页",
                         {"page_count": page_count, "requested": args.page_range})
    raw = slice_pages(raw, page_range)
    if page_range:
        markdown = markdown_from_pages(raw.get("pages") or []) or markdown

    identity = {
        "content_hash": chash,
        "file_name": file_name,
        "engine": engine,
        "page_range": page_range or "all",
        "parse_time": now_iso(),
        "cache_key": key,
    }
    index = build_index(raw, identity)
    index["warnings"] = warnings

    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "markdown.md").write_text(markdown, encoding="utf-8")
    (cdir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (cdir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[已缓存] {cdir}")
    for w in warnings:
        log(f"[警告 {w['code']}] {w['message']}")
    return {"ok": True, "cache_dir": str(cdir), "index": index, "warnings": warnings,
            "markdown_file": str(cdir / "markdown.md"), "markdown": markdown}


def resolve_cache_dir(spec: str) -> Path:
    p = Path(spec)
    if p.exists():
        return p
    return cache_root() / spec


def do_index(args: argparse.Namespace) -> dict:
    cdir = resolve_cache_dir(args.cache)
    raw_file = cdir / "raw.json"
    if not raw_file.exists():
        raise SkillError("NOT_CACHED", f"未找到缓存 raw.json：{cdir}", {"cache": args.cache})
    raw = json.loads(raw_file.read_text(encoding="utf-8"))
    meta_file = cdir / "index.json"
    old = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    identity = old.get("identity") or {
        "content_hash": cdir.name.split("_")[0], "file_name": raw.get("file_name", ""),
        "engine": cdir.name.split("_")[1] if "_" in cdir.name else "standard",
        "page_range": "all", "parse_time": now_iso(), "cache_key": cdir.name,
    }
    index = build_index(raw, identity)
    index["warnings"] = old.get("warnings", [])
    meta_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "cache_dir": str(cdir), "index": index}


def do_search(args: argparse.Namespace) -> dict:
    cdir = resolve_cache_dir(args.cache)
    index_file = cdir / "index.json"
    if not index_file.exists():
        raise SkillError("NOT_CACHED", f"未找到缓存索引：{cdir}（请先 parse）", {"cache": args.cache})
    index = json.loads(index_file.read_text(encoding="utf-8"))
    q = args.query.lower()
    hits = [{"page_num": s["page_num"], "door_id": s["door_id"],
             "snippet": _clip(s["text"], 160)}
            for s in index.get("search", []) if q in (s.get("text") or "").lower()]

    return {"ok": True, "query": args.query, "count": len(hits), "hits": hits}


def _str_to_bool(value: str) -> bool:
    low = value.lower()
    if low in ("true", "1", "yes"):
        return True
    if low in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"需要布尔值，收到 '{value}'")


def add_parse_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--file_path", help="本地文件路径（带后缀）")
    sp.add_argument("--file_url", help="公网文件 URL（带后缀）")
    sp.add_argument("--file_name", help="文件名（含后缀）；缺省时从路径/URL 推断")
    sp.add_argument("--engine", choices=["auto", "standard", "vlm"], default="auto",
                    help="选路：auto 按文件类型；standard 标准版 4.0；vlm PaddleOCR-VL 1.6")
    sp.add_argument("--page_range", help="页范围，如 '1-10' 或 '1-3,7'（1 基）")
    sp.add_argument("-o", "--output", dest="output", help="将 Markdown 正文写入该文件")
    sp.add_argument("--emit", choices=["index", "markdown", "both"], default="index",
                    help="stdout 输出：index 索引(默认)/markdown 正文/both")
    sp.add_argument("--force", action="store_true", help="忽略缓存强制重解析")
    sp.add_argument("--resume_task", help="复用已有 task_id（限流/超时后重查结果，不重新提交）")
    sp.add_argument("--chunk", action="store_true", help="开启 RAG 文档分块")
    # 通用/标准版参数
    sp.add_argument("--recognize_formula", type=_str_to_bool, help="[标准版] 公式识别")
    sp.add_argument("--analysis_chart", type=_str_to_bool, help="[通用] 统计图表解析")
    sp.add_argument("--angle_adjust", type=_str_to_bool, help="[通用] 角度矫正")
    sp.add_argument("--parse_image_layout", type=_str_to_bool, help="[标准版] 返回图片位置")
    sp.add_argument("--html_table_format", type=_str_to_bool, help="[标准版] 表格转 HTML")
    sp.add_argument("--language_type", help="[标准版] 语种，默认 CHN_ENG")
    sp.add_argument("--switch_digital_width", help="[标准版] 数字全半角 auto/half/full")
    sp.add_argument("--version", help="[标准版] 接口版本")
    # VL 参数
    sp.add_argument("--merge_tables", type=_str_to_bool, help="[VL] 跨页表格合并")
    sp.add_argument("--relevel_titles", type=_str_to_bool, help="[VL] 标题分级")
    sp.add_argument("--recognize_seal", type=_str_to_bool, help="[VL] 识别印章")
    sp.add_argument("--return_span_boxes", type=_str_to_bool, help="[VL] 返回行坐标")
    sp.add_argument("--erase_seal", type=_str_to_bool, help="[VL] 擦章（会改画面，核章时勿开）")
    sp.add_argument("--erase_watermark", type=_str_to_bool, help="[VL] 擦水印")
    sp.add_argument("--unwarp", type=_str_to_bool, help="[VL] 弯折矫正")
def main() -> None:
    parser = argparse.ArgumentParser(
        description="百度文档解析统一入口（标准版 4.0 + PaddleOCR-VL 1.6），自动选路 + 索引 + 缓存复用")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp_parse = sub.add_parser("parse", help="解析文档并生成索引（结果写入本地缓存）")
    add_parse_args(sp_parse)

    sp_index = sub.add_parser("index", help="从已缓存 raw.json 重建索引")
    sp_index.add_argument("--cache", required=True, help="缓存目录或 cache_key")

    sp_search = sub.add_parser("search", help="在已缓存索引里按关键词检索正文")
    sp_search.add_argument("--cache", required=True, help="缓存目录或 cache_key")
    sp_search.add_argument("--query", required=True, help="检索关键词")

    args = parser.parse_args()
    try:
        if args.cmd == "parse":
            out = do_parse(args)
            md = out.get("markdown")
            if md is None and os.path.isfile(out["markdown_file"]):
                md = Path(out["markdown_file"]).read_text(encoding="utf-8")
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(md or "", encoding="utf-8")
                log(f"Markdown 已写入: {args.output}")
            payload = {"ok": True, "cache_dir": out["cache_dir"],
                       "markdown_file": out["markdown_file"],
                       "warnings": out.get("warnings", []), "index": out["index"]}
            if args.emit == "markdown":
                print(md or "")
            elif args.emit == "both":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                print("\n---- MARKDOWN ----\n")
                print(md or "")
            else:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.cmd == "index":
            print(json.dumps(do_index(args), ensure_ascii=False, indent=2))
        elif args.cmd == "search":
            print(json.dumps(do_search(args), ensure_ascii=False, indent=2))
    except SkillError as err:
        # 失败一律结构化：code 给 Agent 分支、message 给 Agent、user_prompt 给人看
        print(json.dumps(err.to_dict(), ensure_ascii=False, indent=2))
        log(f"[{err.code}] {err.message}")
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        err = SkillError("BACKEND_UNAVAILABLE", f"网络请求失败: {exc}")
        print(json.dumps(err.to_dict(), ensure_ascii=False, indent=2))
        log(f"[{err.code}] {err.message}")
        sys.exit(1)
    except Exception as exc:
        err = SkillError("BACKEND_UNAVAILABLE", f"未预期错误: {exc}", {"type": type(exc).__name__})
        print(json.dumps(err.to_dict(), ensure_ascii=False, indent=2))
        log(f"[{err.code}] {err.message}")
        sys.exit(1)



if __name__ == "__main__":
    main()










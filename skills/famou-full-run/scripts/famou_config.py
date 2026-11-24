"""Portable Famou public-cloud configuration; no host-specific defaults."""

import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

DEFAULT_BASE_URL = "https://pro-service.famou.com"
DEFAULT_FRONTEND_URL = "https://www.famou.com"
CHANNEL = "workstation"
SKILL_VERSION = "2.1.0"
SKILL_VERSION_PATTERN = re.compile(r"^([A-Za-z]+-)?[0-9]+[.][0-9]+[.][0-9]+(-[A-Za-z]+)?$")
STATE_DIRECTORY = "famou-skill"


class ApiKeyError(Exception):
    """Configuration or credential loading failed."""


def setting(name, default=""):
    """Read a public-client setting from FAMOU environment variables."""
    return os.environ.get("FAMOU_" + name) or default


def checked_url(value):
    """Keep credentials on HTTPS; allow HTTP only for local fixture servers."""
    parsed = urlsplit(value)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        raise ApiKeyError("接口地址须为 HTTPS 且不能带账号、查询参数或片段；本机测试允许 loopback HTTP")
    return value.rstrip("/")


def base_url():
    """Return the validated public API base URL."""
    return checked_url(setting("BASE_URL", DEFAULT_BASE_URL))


def frontend_url():
    """Return the validated frontend URL used for result links."""
    return checked_url(setting("FRONTEND_URL", DEFAULT_FRONTEND_URL))


def session_panel_url(session_id, ticket):
    """Build a view-only task link that logs the browser in with a one-time ticket."""
    return (
        f"{frontend_url()}/chat/{quote(session_id, safe='')}"
        f"?panelOnly=1&login_ticket={quote(str(ticket), safe='')}"
    )


def file_panel_url(session_id, file_id, ticket):
    """Build a view-only single-file link; every link needs its own ticket."""
    return session_panel_url(session_id, ticket) + "&fileid=" + quote(str(file_id), safe="")


def get_api_key(required=True):
    """Load a key from FAMOU settings or the default private file."""
    key = os.environ.get("FAMOU_API_KEY", "").strip()
    if key:
        return key
    filename = os.environ.get("FAMOU_API_KEY_FILE", "").strip()
    if filename:
        try:
            key = Path(filename).expanduser().read_text(encoding="utf-8").strip()
        except OSError:
            raise ApiKeyError("无法读取 API Key 文件，请检查路径和权限") from None
        if key:
            return key
        raise ApiKeyError("API Key 文件为空")
    default = Path.home() / ".config" / "famou" / "public-api-key"
    if default.is_file():
        try:
            key = default.read_text(encoding="utf-8").strip()
        except OSError:
            raise ApiKeyError("无法读取本机伐谋 Key 文件") from None
        if key:
            return key
    if required:
        raise ApiKeyError("请在本机配置 FAMOU_API_KEY_FILE 或 FAMOU_API_KEY；不要将 Key 写入对话或技能包")
    return None


def request_config():
    """Resolve the public API endpoint and API-key authorization header."""
    return base_url(), {"x-famou-authorization": "Bearer " + get_api_key()}


def client_headers():
    """Build client headers required by the public sessions API."""
    if not SKILL_VERSION_PATTERN.fullmatch(SKILL_VERSION):
        raise ApiKeyError(f"无效的 skill-version 格式：{SKILL_VERSION}")
    # Ordinary users declare the workstation channel rather than an enterprise identity header.
    return {
        "x-client-type": f"famou-public-skill@{SKILL_VERSION}",
        "skill-version": SKILL_VERSION,
        "X-Famou-Channel": CHANNEL,
    }

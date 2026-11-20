"""Private session receipts. No conversation bodies, API keys or signed links on disk."""
import datetime
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import famou_config
from .protocol import Turn


class Context:
    """Per-invocation runtime context, wait-window schedule and continuation builder."""

    def __init__(self, session_id=None, operation="wait", *, mode="interactive",
                 wait_seconds=None, explicit_wait=None, poll_budget=1, entrypoint=None,
                 output_format="json", links="auto"):
        """Initialize an invocation context with adaptive or explicit observation windows."""
        self.session_id = session_id
        self.operation = operation
        self.mode = mode
        self.explicit_wait = (wait_seconds is not None) if explicit_wait is None else bool(explicit_wait)
        if wait_seconds is None:
            wait_seconds = 15 if mode == "peek" else (60 if operation in ("start", "append", "confirm") else 120)
        self.wait_seconds = wait_seconds
        self.poll_budget = poll_budget
        self.output_format = output_format
        self.links = links
        self.entrypoint = str(entrypoint or Path(__file__).resolve().parents[1] / "famou.py")
        self.cursor = None
        self.turn = Turn()
        self.deadline = time.monotonic() + wait_seconds
        self.interrupted = False
        self.request_id = None
        self.previous = {}
        self.history_incomplete = False

    def next_wait_seconds(self):
        """Return the bounded window for the next wait step (60 -> 120 -> 180 -> 240s)."""
        if self.explicit_wait:
            return self.wait_seconds
        if self.mode == "peek":
            return 15
        if self.operation in ("start", "append", "confirm"):
            return 120
        if self.wait_seconds < 180:
            return 180
        return 240

    def continuation(self, automatic=False, tool_description=None):
        """Build a host-executable wait command with Chinese tool label and timeout budget."""
        seconds = self.next_wait_seconds()
        argv = [sys.executable, self.entrypoint, "wait", self.session_id,
                "--format", self.output_format, "--mode", self.mode, "--links", self.links]
        if self.explicit_wait:
            argv += ["--wait-seconds", str(seconds)]
        payload = {"action": "wait", "session_id": self.session_id, "argv": argv,
                   "wait_seconds": seconds, "tool_timeout_seconds": seconds + 60,
                   "requires_user_input": False, "automatic": automatic}
        if tool_description:
            payload["tool_description"] = tool_description
        return payload


class ReceiptStore:
    """Atomic, 0600 local receipt persistence stripped of user text, keys and signed URLs."""

    def __init__(self, root=None):
        """Bind receipt storage to FAMOU_STATE_DIR or the environment's default state directory."""
        default = Path.home() / ".local/share" / famou_config.STATE_DIRECTORY
        self.root = Path(root or os.environ.get("FAMOU_STATE_DIR", str(default))).expanduser()

    @staticmethod
    def valid_id(session_id):
        """Validate session and experiment IDs before touching filesystem paths."""
        return isinstance(session_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", session_id) is not None

    def load(self, session_id):
        """Read safe metadata for one session matching the active API base URL."""
        if not self.valid_id(session_id):
            return {}
        try:
            record = json.loads((self.root / (session_id + ".json")).read_text(encoding="utf-8"))
            if (
                isinstance(record, dict)
                and record.get("session_id") == session_id
                and record.get("base_url") == famou_config.base_url()
            ):
                allowed = (
                    "session_id", "base_url", "updated_at", "request_id",
                    "status", "phase", "observation_fingerprint",
                )
                out = {key: record[key] for key in allowed if isinstance(record.get(key), str)}
                nws = record.get("next_wait_seconds")
                if type(nws) is int and 10 <= nws <= 540:
                    out["next_wait_seconds"] = nws
                ms = record.get("milestones")
                if isinstance(ms, list) and all(isinstance(k, str) for k in ms):
                    out["milestones"] = ms
                return out
        except (OSError, ValueError, UnicodeError):
            pass
        return {}

    def save(self, ctx, result=None):
        """Persist non-sensitive receipt metadata atomically."""
        if not self.valid_id(ctx.session_id):
            return
        record = {"session_id": ctx.session_id, "base_url": famou_config.base_url(),
                  "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "request_id": ctx.request_id,
                  "next_wait_seconds": ctx.next_wait_seconds()}
        if result:
            flags = [k for k, v in ctx.turn.milestones.items() if v is True and k != "turn_count"]
            record.update({"status": result["status"], "phase": result["phase"],
                           "observation_fingerprint": result["update"]["fingerprint"],
                           "milestones": flags})
        else:
            # A recovery checkpoint must not erase the previous observation fingerprint.
            previous = self.load(ctx.session_id)
            for key in ("status", "phase", "observation_fingerprint", "milestones"):
                if key in previous:
                    record[key] = previous[key]
        temp = None
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            temp = self.root / (uuid.uuid4().hex + ".tmp")
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(record, file, ensure_ascii=False)
            os.replace(temp, self.root / (ctx.session_id + ".json"))
        except OSError:
            print("[伐谋] 无法保存本机会话记录，请保留 session_id。", file=sys.stderr)
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass

    def sessions(self):
        """List saved session receipts matching the active API endpoint, newest first."""
        records = [self.load(path.stem) for path in self.root.glob("*.json")]
        return sorted((record for record in records if record),
                      key=lambda row: row.get("updated_at", ""), reverse=True)

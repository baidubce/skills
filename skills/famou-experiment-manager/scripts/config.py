#!/usr/bin/env python3
"""Famou configuration and project file management tool."""
import argparse
import json
import os
import sys

SETTINGS_PATH = os.path.expanduser("~/.famou-ctl/settings.json")
DEFAULT_API_URL = "https://pro-service.famou.com"
DEFAULT_USER_ID = "default"


def mask(s: str) -> str:
    """Mask a sensitive string while preserving short edge fragments."""
    return s[:3] + "***" + s[-3:] if len(s) > 6 else "***"


def load_settings() -> dict:
    """Load Famou settings from disk, returning an empty mapping on failure."""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH) as f:
            return json.load(f)
    except Exception as e:
        print(f"WARNING: Failed to parse settings file: {e}", file=sys.stderr)
        return {}


def cmd_read():
    """Read settings and check whether api_url and api_key are complete."""
    settings = load_settings()
    api_url = settings.get("api_url", "").strip()
    api_key = settings.get("api_key", "").strip()

    missing = []
    if not api_url:
        missing.append("api_url")
    if not api_key:
        missing.append("api_key")

    result = {
        "status": "ok" if not missing else "missing",
        "api_url": api_url,
        "masked_key": mask(api_key) if api_key else "",
        "missing": missing
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_write(api_key: str):
    """Write API key using the default api_url and user_id."""
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)

    settings = {
        "api_url": DEFAULT_API_URL,
        "api_key": api_key.strip(),
        "user_id": DEFAULT_USER_ID
    }

    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(settings, f, indent=2)
        result = {
            "success": True,
            "message": "Settings saved",
            "config": {
                "api_url": settings["api_url"],
                "masked_key": mask(settings["api_key"])
            }
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        result = {
            "success": False,
            "error": str(e)
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)


def main():
    """Parse command-line arguments and dispatch the requested config action."""
    parser = argparse.ArgumentParser(description="Famou configuration and project file management tool")
    parser.add_argument("command", choices=["read", "write"], help="Command: read or write")
    parser.add_argument("api_key", nargs="?", help="API key (required only for write command)")
    
    args = parser.parse_args()

    if args.command == "read":
        cmd_read()
    elif args.command == "write":
        if not args.api_key:
            parser.error("write command requires an api_key argument")
        cmd_write(args.api_key)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""AUSTR.AI Desktop App — pywebview UI with local anonymization."""

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import webview

from austrai_proxy.core import get_engine

UI_FILE = Path(__file__).parent / "ui.html"
PROXY_PID_FILE = Path.home() / ".austrai" / "proxy.pid"


class AustraiAPI:
    """Python API exposed to JavaScript via pywebview."""

    def __init__(self):
        self._session_id = None
        self._mappings = {}

    def protect(self, text):
        engine = get_engine()
        result = engine.anonymize(text)
        self._session_id = result.session_id
        self._mappings = result.mappings
        _copy_to_clipboard(result.anonymized_text)
        return {
            "anonymized_text": result.anonymized_text,
            "mappings": result.mappings,
            "session_id": result.session_id,
            "entity_count": len(result.mappings),
        }

    def restore(self, text):
        if not self._mappings:
            return {"restored_text": text, "replacements": 0}
        engine = get_engine()
        restored = engine.rehydrate(text, self._mappings)
        count = sum(1 for k in self._mappings if k in text)
        _copy_to_clipboard(restored)
        return {"restored_text": restored, "replacements": count}

    def toggle_proxy(self):
        if _is_proxy_running():
            try:
                pid = int(PROXY_PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                PROXY_PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            return {"running": False}
        else:
            subprocess.Popen(
                [sys.executable, "-m", "austrai_proxy", "start", "-b"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            import time; time.sleep(2)
            return {"running": _is_proxy_running()}

    def get_status(self):
        return {
            "proxy_running": _is_proxy_running(),
            "session_active": self._session_id is not None,
            "entity_count": len(self._mappings),
        }

    def paste_clipboard(self):
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return result.stdout
        except Exception:
            return ""


def _is_proxy_running():
    if not PROXY_PID_FILE.exists():
        return False
    try:
        pid = int(PROXY_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        return False


def _copy_to_clipboard(text):
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
    except Exception:
        pass


def main():
    # Pre-init engine in background
    threading.Thread(target=lambda: get_engine(), daemon=True).start()

    api = AustraiAPI()
    webview.create_window(
        "AUSTR.AI — Privacy Firewall",
        str(UI_FILE),
        js_api=api,
        width=740,
        height=820,
        min_size=(520, 600),
        background_color="#06090f",
    )
    webview.start()


if __name__ == "__main__":
    main()

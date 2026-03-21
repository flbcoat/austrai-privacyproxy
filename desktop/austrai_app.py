#!/usr/bin/env python3
"""AUSTR.AI Desktop App — Menubar + Webview UI with local anonymization.

Runs as a macOS menubar app (next to the clock). Click the shield icon
to open the main window. Everything runs locally.
"""

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import rumps
import webview

from austrai_proxy.core import get_engine

UI_FILE = Path(__file__).parent / "ui.html"
PROXY_PID_FILE = Path.home() / ".austrai" / "proxy.pid"


# ---------------------------------------------------------------------------
# Webview API (exposed to JavaScript)
# ---------------------------------------------------------------------------

class WebviewAPI:
    """Python API exposed to the JavaScript frontend via pywebview."""

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


# ---------------------------------------------------------------------------
# Menubar App (macOS)
# ---------------------------------------------------------------------------

class AustraiMenubar(rumps.App):
    """macOS menubar app with shield icon."""

    def __init__(self):
        super().__init__(
            "AUSTR.AI",
            title="🛡",
            quit_button=None,
        )
        self.menu = [
            rumps.MenuItem("Fenster öffnen", callback=self.open_window),
            rumps.MenuItem("Proxy starten", callback=self.toggle_proxy),
            None,  # separator
            rumps.MenuItem("Status", callback=self.show_status),
            None,
            rumps.MenuItem("Beenden", callback=self.quit_app),
        ]
        self._webview_api = WebviewAPI()
        self._window = None
        self._update_proxy_menu()

        # Periodic proxy status check
        self._timer = rumps.Timer(self._check_proxy, 5)
        self._timer.start()

    def open_window(self, _=None):
        """Open the main webview window."""
        if self._window and self._window.uid:
            # Window exists, bring to front
            try:
                self._window.show()
                return
            except Exception:
                pass

        # Create new window in a thread (webview blocks)
        threading.Thread(target=self._create_window, daemon=True).start()

    def _create_window(self):
        self._window = webview.create_window(
            "AUSTR.AI",
            str(UI_FILE),
            js_api=self._webview_api,
            width=740,
            height=820,
            min_size=(520, 600),
            background_color="#06090f",
        )
        webview.start(debug=False)

    def toggle_proxy(self, sender=None):
        result = self._webview_api.toggle_proxy()
        self._update_proxy_menu()
        if result["running"]:
            rumps.notification("AUSTR.AI", "Proxy gestartet", "localhost:8282 — alle Apps geschützt")
        else:
            rumps.notification("AUSTR.AI", "Proxy gestoppt", "")

    def show_status(self, _=None):
        proxy = "aktiv" if _is_proxy_running() else "gestoppt"
        rumps.notification(
            "AUSTR.AI Status",
            f"Proxy: {proxy}",
            "Modus: Lokal — alles auf deinem Rechner",
        )

    def quit_app(self, _=None):
        # Stop proxy if running
        if _is_proxy_running():
            try:
                pid = int(PROXY_PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                PROXY_PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass
        rumps.quit_application()

    def _check_proxy(self, _=None):
        self._update_proxy_menu()

    def _update_proxy_menu(self):
        running = _is_proxy_running()
        try:
            self.menu["Proxy starten"].title = "Proxy stoppen" if running else "Proxy starten"
            self.title = "🛡" if running else "🛡️"  # subtle visual difference
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Pre-init engine in background (so first anonymize is fast)
    threading.Thread(target=lambda: get_engine(), daemon=True).start()

    # Check if rumps is available (macOS only)
    try:
        app = AustraiMenubar()
        app.run()
    except Exception:
        # Fallback: just open the webview window directly
        api = WebviewAPI()
        window = webview.create_window(
            "AUSTR.AI",
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

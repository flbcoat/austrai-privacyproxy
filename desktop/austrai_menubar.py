#!/usr/bin/env python3
"""AUSTR.AI Menubar — Shield-Icon in der macOS Menüleiste."""

import os
import signal
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

APP_SCRIPT = Path(__file__).parent / "austrai_app.py"
PROXY_PID = Path.home() / ".austrai" / "proxy.pid"


def create_icon():
    """Create a simple shield icon."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Shield shape
    draw.polygon([(32, 4), (58, 16), (54, 44), (32, 58), (10, 44), (6, 16)],
                 fill=(6, 182, 212, 255), outline=(255, 255, 255, 200))
    # Checkmark
    draw.line([(22, 32), (30, 40), (44, 22)], fill=(255, 255, 255, 255), width=4)
    return img


_app_proc = None


def open_app(icon, item):
    global _app_proc
    if _app_proc and _app_proc.poll() is None:
        return
    _app_proc = subprocess.Popen(
        [sys.executable, str(APP_SCRIPT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def toggle_proxy(icon, item):
    if _proxy_running():
        try:
            pid = int(PROXY_PID.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            PROXY_PID.unlink(missing_ok=True)
        except Exception:
            pass
    else:
        subprocess.Popen(
            [sys.executable, "-m", "austrai_proxy", "start", "-b"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def quit_app(icon, item):
    global _app_proc
    if _app_proc and _app_proc.poll() is None:
        _app_proc.terminate()
    if _proxy_running():
        try:
            pid = int(PROXY_PID.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            PROXY_PID.unlink(missing_ok=True)
        except Exception:
            pass
    icon.stop()


def proxy_label(item):
    return "Proxy stoppen" if _proxy_running() else "Proxy starten"


def _proxy_running():
    if not PROXY_PID.exists(): return False
    try:
        os.kill(int(PROXY_PID.read_text().strip()), 0)
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        return False


def main():
    icon = pystray.Icon(
        "austrai",
        create_icon(),
        "AUSTR.AI Privacy Firewall",
        menu=pystray.Menu(
            pystray.MenuItem("App öffnen", open_app, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(proxy_label, toggle_proxy),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", quit_app),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()

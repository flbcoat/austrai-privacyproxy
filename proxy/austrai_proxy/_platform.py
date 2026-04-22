"""Cross-platform helpers for AUSTR.AI.

macOS, Linux and Windows each need different approaches for clipboard access,
port management, background processes, signal handling, RAM detection and
terminal encoding. Centralising the platform branching here keeps the rest
of the codebase POSIX-flavoured and free of OS checks.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# stdio / terminal
# ---------------------------------------------------------------------------

def ensure_utf8_stdio() -> None:
    """Force UTF-8 on stdin/stdout/stderr.

    Windows-CMD defaults to cp1252 and explodes on the German umlauts and
    emoji used throughout AUSTR.AI's CLI output (``UnicodeEncodeError``).
    Python 3.7+ exposes ``reconfigure`` on the text streams; we call it
    best-effort and swallow errors so non-tty environments (pipes, IDE
    consoles) keep working.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# clipboard
# ---------------------------------------------------------------------------

def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success.

    All branches are best-effort: if the platform helper is missing or
    fails, the caller just continues without clipboard integration.
    """
    if not text:
        return False

    try:
        if IS_MACOS and shutil.which("pbcopy"):
            subprocess.run(
                ["pbcopy"], input=text.encode("utf-8"),
                check=True, timeout=5,
            )
            return True

        if IS_WINDOWS:
            # clip.exe ships with every modern Windows. It reads UTF-16-LE
            # on recent versions but also accepts UTF-8 with a BOM; we use
            # the legacy behaviour (raw bytes) which works for ASCII and
            # most Latin-1. For arbitrary unicode we fall through to
            # PowerShell's Set-Clipboard, which is UTF-8 clean.
            if shutil.which("clip"):
                try:
                    subprocess.run(
                        ["clip"], input=text.encode("utf-16-le"),
                        check=True, timeout=5,
                    )
                    return True
                except Exception:
                    pass
            if shutil.which("powershell"):
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
                    input=text.encode("utf-8"),
                    check=True, timeout=5,
                )
                return True
            return False

        if IS_LINUX:
            for cmd in (
                ["wl-copy"],                      # Wayland
                ["xclip", "-selection", "clipboard"],
                ["xsel", "-b", "-i"],
            ):
                if shutil.which(cmd[0]):
                    subprocess.run(
                        cmd, input=text.encode("utf-8"),
                        check=True, timeout=5,
                    )
                    return True
            return False
    except Exception:
        return False

    return False


# ---------------------------------------------------------------------------
# process control
# ---------------------------------------------------------------------------

def is_process_alive(pid: int) -> bool:
    """Check if a process with this PID exists.

    ``os.kill(pid, 0)`` is the POSIX idiom and has been implemented on
    Windows since Python 3.2 (it calls ``OpenProcess`` under the hood).
    Works uniformly on all supported platforms.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError, PermissionError):
        # PermissionError on Windows means the process exists but we cannot
        # signal it (different user / protected); for liveness we treat it
        # as alive.
        if IS_WINDOWS:
            try:
                # Re-check via taskkill --query style: if taskkill thinks
                # the PID is gone, it'll non-zero exit.
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                return str(pid) in result.stdout
            except Exception:
                return False
        return False


def terminate_process(pid: int) -> bool:
    """Politely ask a process to terminate. Returns True if the signal went out.

    On Unix we send SIGTERM. On Windows ``taskkill`` is the reliable option
    because ``os.kill`` with SIGTERM ends up calling ``TerminateProcess``
    directly — fine for most cases, but ``taskkill`` also handles the
    cases where the proxy was started as a detached process group.
    """
    if pid <= 0:
        return False
    try:
        if IS_WINDOWS:
            if shutil.which("taskkill"):
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True, timeout=5,
                )
                return True
            # Fallback if taskkill is stripped from the image (rare).
            os.kill(pid, signal.SIGTERM)
            return True
        os.kill(pid, signal.SIGTERM)
        return True
    except (ProcessLookupError, ValueError, PermissionError, OSError):
        return False


def kill_processes_on_port(port: int) -> int:
    """Kill whatever listens on ``port``. Returns count of killed PIDs.

    macOS / Linux use ``lsof``; Windows uses ``netstat -ano`` + ``taskkill``.
    Everything is wrapped so a missing helper never bubbles up.
    """
    killed = 0
    try:
        if IS_WINDOWS:
            # netstat -ano shows the owning PID in the last column. Grep-like
            # filtering for `:port` matches both LISTENING and connected
            # sockets; we only kill LISTENING entries to avoid collateral.
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10,
            )
            needle = f":{port}"
            pids_to_kill: set[int] = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5:
                    continue
                local = parts[1]
                state = parts[3] if len(parts) >= 4 else ""
                pid_str = parts[-1]
                if state == "LISTENING" and local.endswith(needle):
                    try:
                        pids_to_kill.add(int(pid_str))
                    except ValueError:
                        continue
            for pid in pids_to_kill:
                if terminate_process(pid):
                    killed += 1
        else:
            # macOS/Linux
            if not shutil.which("lsof"):
                return 0
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                for pid_str in result.stdout.strip().split("\n"):
                    try:
                        if terminate_process(int(pid_str)):
                            killed += 1
                    except ValueError:
                        continue
        if killed:
            # Give the OS a moment to release the socket before the caller
            # tries to bind to it.
            time.sleep(1)
    except Exception:
        return killed
    return killed


def start_detached_process(cmd: list[str]) -> subprocess.Popen:
    """Spawn a subprocess that survives the parent exiting.

    POSIX uses ``start_new_session=True`` so the child escapes the parent's
    controlling terminal. Windows uses ``DETACHED_PROCESS`` +
    ``CREATE_NEW_PROCESS_GROUP`` because passing POSIX-only kwargs would
    raise ``ValueError: start_new_session is not supported on this
    platform`` on some Python builds.
    """
    kwargs = dict(
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    if IS_WINDOWS:
        # These flags exist on subprocess since Python 3.7 on Windows.
        DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        CREATE_NEW_PROCESS_GROUP = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        # close_fds defaults to True on Windows when redirected; leave it.
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


# ---------------------------------------------------------------------------
# system info
# ---------------------------------------------------------------------------

def get_total_ram_gb() -> float:
    """Best-effort total physical RAM in GB, 0.0 if it can't be determined.

    Preferred path: ``psutil`` (cross-platform, dependency-light). Fallbacks
    cover macOS (sysctl), Linux (/proc/meminfo) and Windows
    (GlobalMemoryStatusEx via ctypes) so we never guess low on Windows and
    end up recommending the smallest model on a 32 GB workstation.
    """
    try:
        import psutil  # type: ignore
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except ImportError:
        pass

    try:
        if IS_MACOS:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return round(int(result.stdout.strip()) / (1024 ** 3), 1)
        elif IS_LINUX:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 1)
        elif IS_WINDOWS:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0

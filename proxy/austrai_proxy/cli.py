"""AUSTR.AI CLI — lokaler KI-Assistent mit eingebautem Datenschutz.

Usage:
  aai chat              Chat-UI starten (Hauptbefehl, blockt das Terminal)
  aai chat --open       Chat-UI starten und im Default-Browser öffnen
  aai chat --background Server im Hintergrund starten, Terminal wird frei
  aai --help            Hilfe anzeigen

Alle weiteren Einstellungen (API-Keys, Deny-/Allow-Listen, Providers,
Datei-Anonymisierung, Bildschwärzung, Audio-Transkription) werden direkt
in der Web-UI unter http://localhost:8282/chat vorgenommen.
"""

import json
import os
import socket
import subprocess
import sys
import time

import click

from . import __version__
from .config import ProxyConfig, CONFIG_DIR
from ._platform import (
    ensure_utf8_stdio,
    is_process_alive,
    kill_processes_on_port,
    start_detached_process,
)

# Windows-CMD defaults to cp1252 which cannot render the emoji and German
# umlauts the CLI prints. Reconfigure stdio to UTF-8 as early as possible —
# before the first click.echo — so we never hit UnicodeEncodeError.
ensure_utf8_stdio()


PROXY_PID_FILE = CONFIG_DIR / "proxy.pid"
UPDATE_CACHE_FILE = CONFIG_DIR / "last_update_check.json"
UPDATE_CHECK_INTERVAL = 24 * 3600  # once per day
PYPI_URL = "https://pypi.org/pypi/austrai/json"


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """AUSTR.AI — Lokaler KI-Assistent mit Datenschutz.

    Starte die Chat-UI mit `aai chat`. Alle Einstellungen (Modelle,
    API-Keys, Datenschutz-Regeln, Datei-Anonymisierung) sind direkt
    in der Web-UI verfügbar.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# -----------------------------------------------------------------------
# aai chat — THE main command.
# -----------------------------------------------------------------------

@main.command()
@click.option("--port", "-p", default=None, type=int, help="Port (Standard: 8282)")
@click.option("--open", "open_browser", is_flag=True,
              help="Im Default-Browser öffnen (Standard: nur URL anzeigen)")
@click.option("--background", "-b", is_flag=True,
              help="Server detached starten, Terminal bleibt frei")
@click.option("--no-update-check", is_flag=True, help="PyPI-Update-Check überspringen")
def chat(port, open_browser, background, no_update_check):
    """AUSTR.AI starten — alles wird automatisch eingerichtet."""
    import shutil
    config = ProxyConfig.load()
    if port:
        config.port = port

    click.echo("\n🛡  AUSTR.AI " + __version__ + "\n")

    # ── Update-Check (non-blocking, cached 24h) ────────────────
    if not no_update_check:
        latest = _check_for_update()
        if latest and latest != __version__ and _version_is_newer(latest, __version__):
            click.echo(f"  ⬆ Update {latest} verfügbar (installiert: {__version__})")
            click.echo(f"     pip install --upgrade austrai\n")

    # ── Auto-Setup: Sprachmodell + Erkennungsmodell pruefen ────
    first_run = not (CONFIG_DIR / "proxy.yaml").exists()
    needs_setup = first_run

    try:
        import spacy
        spacy.load("de_core_news_sm")
    except (OSError, ImportError):
        needs_setup = True

    if needs_setup:
        click.echo("  Erster Start — wird eingerichtet...\n")
        _auto_setup()
        click.echo("")

    # Tesseract hint (optional, non-blocking)
    if not shutil.which("tesseract"):
        click.echo("  Hinweis: Tesseract OCR nicht installiert (Bildschwärzung).")
        if sys.platform == "darwin":
            click.echo("    brew install tesseract\n")
        elif sys.platform.startswith("linux"):
            click.echo("    sudo apt install tesseract-ocr\n")
        else:
            click.echo("    https://github.com/tesseract-ocr/tesseract\n")

    url = f"http://localhost:{config.port}/chat"

    # ── Branch: Background vs Foreground ────────────────────────
    if background:
        if _is_proxy_running():
            click.echo(f"  ✓ Server läuft bereits.")
        else:
            _start_proxy_background(config)
            # Give uvicorn a moment to actually bind the port before we
            # report success. If it fails (port in use, import crash etc.)
            # we want to fail loudly, not silently.
            time.sleep(2)
            if not _is_proxy_running():
                click.echo("  ✗ Server konnte nicht im Hintergrund starten.")
                click.echo("     Starte im Vordergrund um den Fehler zu sehen:")
                click.echo("     aai chat\n")
                raise SystemExit(1)

        click.echo(f"""   ➜  Öffne im Browser deiner Wahl:
      {url}

   ⓘ  Die URL funktioniert in Safari, Chrome, Firefox und jedem anderen Browser.

   Zum Stoppen:  aai stop     (oder: kill {_read_pid() or '<PID>'})
""")
        if open_browser:
            _open_in_default_browser(url)
        return

    # Foreground: user sees everything, Ctrl+C wirkt wirklich.
    _pre_start_banner(config, url)
    if open_browser:
        # Open browser after a short delay so uvicorn has time to bind.
        # On macOS webbrowser.open spawns the browser asynchronously, so the
        # small delay is enough to avoid "connection refused" on first load.
        import threading
        threading.Timer(1.5, lambda: _open_in_default_browser(url)).start()

    _start_proxy_foreground(config)


def _pre_start_banner(config, url: str) -> None:
    """Print the before-we-block banner with clear next-step instructions."""
    anth = "✓" if config.anthropic_api_key else "—"
    oai = "✓" if config.openai_api_key else "—"
    mistral = "✓" if config.mistral_api_key else "—"

    click.echo(f"""   ➜  Öffne im Browser deiner Wahl:
      {url}

   ⓘ  Die URL funktioniert in Safari, Chrome, Firefox und jedem anderen Browser.
      Tipp: Wenn dein gewünschter Browser nicht automatisch aufgeht,
      einfach die Adresse oben kopieren und dort einfügen.

   KI-Anbieter:  Anthropic {anth}   OpenAI {oai}   Mistral {mistral}
   Deny-Liste:   {len(config.deny_list)} Begriff(e)

   Server läuft hier im Terminal. Zum Beenden: Ctrl+C
""")


# -----------------------------------------------------------------------
# aai stop — stop a background-started proxy.
# -----------------------------------------------------------------------

@main.command()
def stop():
    """Einen im Hintergrund laufenden AUSTR.AI-Server stoppen."""
    from ._platform import terminate_process
    pid = _read_pid()
    if pid and is_process_alive(pid):
        if terminate_process(pid):
            PROXY_PID_FILE.unlink(missing_ok=True)
            click.echo(f"✓ Server (PID {pid}) gestoppt.")
            return
        click.echo(f"✗ Konnte PID {pid} nicht beenden.")
        raise SystemExit(1)

    # PID-File exists but process is dead, or no PID-file at all.
    PROXY_PID_FILE.unlink(missing_ok=True)
    click.echo("ℹ Kein laufender Server gefunden.")


# -----------------------------------------------------------------------
# Hidden: aai start — used internally by `aai chat --background` to spawn
# the detached server process. Also a stable entry for power-users.
# -----------------------------------------------------------------------

@main.command(hidden=True)
@click.option("--port", "-p", default=None, type=int)
def start(port):
    """Server im Vordergrund starten (intern; von --background genutzt)."""
    config = ProxyConfig.load()
    if port:
        config.port = port
    _start_proxy_foreground(config, quiet_banner=True)


# -----------------------------------------------------------------------
# Server runners
# -----------------------------------------------------------------------

def _build_dual_stack_sockets(port: int) -> list:
    """Create separate IPv4 and IPv6 localhost sockets and return them.

    Binding to "127.0.0.1" alone leaves Chrome/Firefox users out when their
    localhost resolution prefers ::1 — they get "connection refused" and
    sometimes the fallback to 127.0.0.1 is slow or broken.

    Binding to "::" would solve dual-stack but also accepts external
    connections, which is wrong for a local privacy proxy.

    The correct answer is two separate localhost sockets, passed to
    uvicorn's Server.serve(sockets=...). Uvicorn multiplexes them cleanly.
    """
    sockets = []
    # IPv4 localhost
    try:
        s4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s4.bind(("127.0.0.1", port))
        s4.listen(128)
        s4.setblocking(False)
        sockets.append(s4)
    except OSError as e:
        click.echo(f"  ⚠ Konnte IPv4 127.0.0.1:{port} nicht binden: {e}")

    # IPv6 localhost (v6-only so it doesn't clobber the v4 socket)
    try:
        s6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        s6.bind(("::1", port))
        s6.listen(128)
        s6.setblocking(False)
        sockets.append(s6)
    except OSError as e:
        # On very old systems or restrictive docker containers IPv6 may be
        # unavailable; that's fine as long as IPv4 works.
        click.echo(f"  ⓘ IPv6-Bind übersprungen: {e}")

    return sockets


def _start_proxy_foreground(config, quiet_banner: bool = False) -> None:
    """Run uvicorn in the current process on dual-stack localhost.

    Blocks until Ctrl+C. Users see log output live. On Ctrl+C the
    KeyboardInterrupt bubbles out of asyncio.run and the sockets get
    cleaned up in the finally-block.
    """
    import asyncio
    import uvicorn
    from .server import create_app

    sockets = _build_dual_stack_sockets(config.port)
    if not sockets:
        click.echo(f"✗ Konnte weder IPv4 noch IPv6 an Port {config.port} binden.")
        raise SystemExit(1)

    app = create_app(config)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    if not quiet_banner:
        click.echo(f"   [OK] Hörbereit auf 127.0.0.1 + ::1 (Port {config.port}).\n")

    uv_config = uvicorn.Config(
        app=app,
        log_level="info",
        access_log=False,
        # host/port are ignored when we pass pre-bound sockets
    )
    server = uvicorn.Server(uv_config)

    try:
        asyncio.run(server.serve(sockets=sockets))
    except KeyboardInterrupt:
        click.echo("\n  Server beendet.")
    finally:
        for s in sockets:
            try:
                s.close()
            except Exception:
                pass
        PROXY_PID_FILE.unlink(missing_ok=True)


def _start_proxy_background(config) -> None:
    """Spawn the server as a detached subprocess.

    This is the --background mode. The child process runs the same code
    path as `aai start`, so it also gets dual-stack binding.
    """
    if _is_proxy_running():
        return

    # Port-Cleanup nur wenn wir sicher sind, dass der Process auf dem
    # Port ein alter AUSTR.AI-Zombie ist (unsere PID-Datei zeigt auf ihn).
    # Sonst würde `_kill_port` fremde User-Services killen (z.B. ein
    # paralleles localhost-Dev-Setup auf Port 8282). Lieber freundlich
    # fehlschlagen und dem User sagen was blockiert.
    import socket
    port_in_use = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        port_in_use = s.connect_ex(("127.0.0.1", config.port)) == 0
        s.close()
    except Exception:
        pass

    if port_in_use:
        # Nur killen wenn unser eigenes PID-File existiert und auf einen
        # toten Prozess zeigt — dann räumen wir unsere eigenen Reste auf.
        our_pid = _read_pid()
        if our_pid and not is_process_alive(our_pid):
            _kill_port(config.port)
            PROXY_PID_FILE.unlink(missing_ok=True)
        else:
            click.echo(
                click.style(
                    f"Port {config.port} ist von einem anderen Prozess belegt. "
                    "Beende ihn manuell oder nutze `aai chat --port <andere>`.",
                    fg="red",
                )
            )
            sys.exit(1)

    cmd = [sys.executable, "-m", "austrai_proxy", "start", "--port", str(config.port)]
    proc = start_detached_process(cmd)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_PID_FILE.write_text(str(proc.pid), encoding="utf-8")


# -----------------------------------------------------------------------
# Update check
# -----------------------------------------------------------------------

def _check_for_update():
    """Return latest version string from PyPI, or None on failure.

    Result is cached in ~/.austrai/last_update_check.json for 24 hours
    so we don't hammer PyPI on every CLI invocation. The fetch itself
    sends no user identification — it's a plain HTTP GET of a public
    JSON endpoint, same semantics as `pip list --outdated`.
    """
    now = time.time()
    if UPDATE_CACHE_FILE.exists():
        try:
            data = json.loads(UPDATE_CACHE_FILE.read_text(encoding="utf-8"))
            if now - float(data.get("checked_at", 0)) < UPDATE_CHECK_INTERVAL:
                return data.get("latest_version")
        except Exception:
            pass

    try:
        import urllib.request
        req = urllib.request.Request(
            PYPI_URL,
            headers={"User-Agent": f"austrai/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        latest = str(data["info"]["version"])
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            UPDATE_CACHE_FILE.write_text(
                json.dumps({"checked_at": now, "latest_version": latest}),
                encoding="utf-8",
            )
        except Exception:
            pass
        return latest
    except Exception:
        return None


def _version_is_newer(candidate: str, current: str) -> bool:
    """Return True if ``candidate`` is semver-newer than ``current``.

    Uses packaging.version if available (robust), else falls back to a
    tuple-of-ints comparison that handles the simple X.Y.Z case we ship.
    """
    try:
        from packaging.version import Version
        return Version(candidate) > Version(current)
    except Exception:
        def parts(v):
            out = []
            for p in v.split("."):
                digits = ""
                for ch in p:
                    if ch.isdigit():
                        digits += ch
                    else:
                        break
                out.append(int(digits) if digits else 0)
            return tuple(out)
        return parts(candidate) > parts(current)


# -----------------------------------------------------------------------
# Browser + helpers
# -----------------------------------------------------------------------

def _open_in_default_browser(url: str) -> None:
    """Open url in the system default browser. Best-effort."""
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def _auto_setup():
    """Automatisches Setup beim ersten Start."""
    try:
        import spacy
        try:
            spacy.load("de_core_news_sm")
            click.echo("  ✓ Sprachmodell geladen")
        except OSError:
            click.echo("  ↓ Sprachmodell wird heruntergeladen (15 MB)...")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "spacy", "download", "de_core_news_sm"],
                    capture_output=True, text=True, timeout=600,
                    encoding="utf-8", errors="replace",
                )
                if result.returncode == 0:
                    click.echo("  ✓ Sprachmodell installiert")
                else:
                    click.echo("  ⚠ Sprachmodell konnte nicht geladen werden")
                    click.echo("    python -m spacy download de_core_news_sm")
            except subprocess.TimeoutExpired:
                click.echo("  ⚠ Download dauert zu lange:")
                click.echo("    python -m spacy download de_core_news_sm")
    except ImportError:
        click.echo("  ⚠ spaCy nicht installiert")

    # GLiNER check
    gliner_ready = False
    try:
        from huggingface_hub import scan_cache_dir
        for repo in scan_cache_dir().repos:
            if "gliner" in repo.repo_id.lower() or "urchade" in repo.repo_id.lower():
                gliner_ready = True
                break
    except Exception:
        pass

    if gliner_ready:
        click.echo("  ✓ Erkennungsmodell geladen")
    else:
        click.echo("  ↓ Erkennungsmodell wird beim ersten Chat geladen (~1 GB)")
        click.echo("    Das dauert einmalig 1-2 Minuten.")

    # Dependencies
    missing = []
    for mod, name in [("fitz", "PyMuPDF"), ("docx", "python-docx"), ("PIL", "Pillow"),
                      ("cryptography", "cryptography")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(name)

    if missing:
        click.echo(f"  ⚠ Fehlend: {', '.join(missing)}")
        click.echo("    pip install austrai")
    else:
        click.echo("  ✓ Alle Pakete installiert")


def _read_pid() -> int | None:
    if not PROXY_PID_FILE.exists():
        return None
    try:
        return int(PROXY_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        PROXY_PID_FILE.unlink(missing_ok=True)
        return None


def _is_proxy_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    if is_process_alive(pid):
        return True
    PROXY_PID_FILE.unlink(missing_ok=True)
    return False


def _kill_port(port: int) -> None:
    kill_processes_on_port(port)


if __name__ == "__main__":
    main()

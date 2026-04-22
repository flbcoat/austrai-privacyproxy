"""AUSTR.AI CLI — lokaler KI-Assistent mit eingebautem Datenschutz.

Usage:
  aai chat              Chat-UI starten (Hauptbefehl, macht alles)
  aai --help            Hilfe anzeigen

Alle weiteren Einstellungen (API-Keys, Deny-/Allow-Listen, Providers,
Datei-Anonymisierung, Bildschwärzung, Audio-Transkription) werden direkt
in der Web-UI unter http://localhost:8282/chat vorgenommen.
"""

import os
import subprocess
import sys
import time

import click

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
@click.option("--no-browser", is_flag=True, help="Browser nicht automatisch oeffnen")
def chat(port, no_browser):
    """AUSTR.AI starten — alles wird automatisch eingerichtet."""
    import shutil
    config = ProxyConfig.load()
    if port:
        config.port = port

    click.echo("\n🛡  AUSTR.AI\n")

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

    # ── Server starten ─────────────────────────────────────────
    if not _is_proxy_running():
        _start_proxy_background(config)
        time.sleep(2)

    url = f"http://localhost:{config.port}/chat"
    click.echo(f"  Bereit: {url}")
    click.echo(f"  Zum Beenden: Ctrl+C\n")

    if not no_browser:
        import webbrowser
        webbrowser.open(url)


# -----------------------------------------------------------------------
# Hidden: aai start — used internally by `aai chat` to spawn the detached
# server process. Not meant for direct end-user use, but kept as a stable
# entry point so the detached subprocess can re-enter python with the same
# interpreter / environment.
# -----------------------------------------------------------------------

@main.command(hidden=True)
@click.option("--port", "-p", default=None, type=int)
@click.option("--host", "-h", default="127.0.0.1")
def start(port, host):
    """Server starten (intern; von `aai chat` aufgerufen)."""
    config = ProxyConfig.load()
    if port:
        config.port = port
    _start_proxy_foreground(config, host=host)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

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


def _start_proxy_foreground(config, host="127.0.0.1"):
    """Start proxy in foreground."""
    import uvicorn
    from .server import create_app

    app = create_app(config)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    port = config.port
    anth = "✓" if config.anthropic_api_key else "✗"
    oai = "✓" if config.openai_api_key else "✗"

    click.echo(f"""
🛡  AUSTR.AI Privacy Proxy

   http://{host}:{port}

   Anthropic: {anth}    OpenAI: {oai}
   Backend:   lokal
   Deny-List: {len(config.deny_list)} Begriffe

   Verbinde deine Apps auf http://{host}:{port}
   Ctrl+C zum Beenden
""")

    try:
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)
    finally:
        PROXY_PID_FILE.unlink(missing_ok=True)


def _start_proxy_background(config):
    """Start proxy as background process."""
    if _is_proxy_running():
        return

    _kill_port(config.port)

    cmd = [sys.executable, "-m", "austrai_proxy", "start", "--port", str(config.port)]
    proc = start_detached_process(cmd)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_PID_FILE.write_text(str(proc.pid), encoding="utf-8")


def _is_proxy_running() -> bool:
    if not PROXY_PID_FILE.exists():
        return False
    try:
        pid = int(PROXY_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        PROXY_PID_FILE.unlink(missing_ok=True)
        return False
    if is_process_alive(pid):
        return True
    PROXY_PID_FILE.unlink(missing_ok=True)
    return False


def _kill_port(port: int) -> None:
    kill_processes_on_port(port)


if __name__ == "__main__":
    main()

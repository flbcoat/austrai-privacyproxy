"""Unified CLI for AUSTR.AI — one command for everything.

Usage:
  aai claude          Start Claude Code through the privacy proxy
  aai start           Start the proxy (for custom apps/SDKs)
  aai app             Open the desktop app (clipboard tool)
  aai config          Configure API keys and settings
  aai status          Show proxy status
  aai stop            Stop the proxy
"""

import os
import signal
import subprocess
import sys
import time

import click

from .config import ProxyConfig, DEFAULT_PORT, CONFIG_DIR


PROXY_PID_FILE = CONFIG_DIR / "proxy.pid"
DESKTOP_APP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "desktop", "austrai_app.py",
)


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """AUSTR.AI — Schuetze deine Daten vor KI-Servern."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# -----------------------------------------------------------------------
# aai claude — Start Claude Code through proxy
# -----------------------------------------------------------------------

@main.command()
@click.argument("extra_args", nargs=-1)
def claude(extra_args):
    """Claude Code durch den Privacy Proxy starten."""
    config = ProxyConfig.load()
    if not config.anthropic_api_key:
        click.echo("Kein Anthropic API Key konfiguriert.")
        click.echo("  aai config")
        raise SystemExit(1)

    _ensure_proxy_running(config)

    click.echo(f"\n🛡  Claude Code startet durch AUSTR.AI Proxy (localhost:{config.port})")
    click.echo("   Alle sensiblen Daten werden automatisch geschuetzt.\n")

    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = f"http://localhost:{config.port}"

    cmd = ["claude"] + list(extra_args)
    try:
        os.execvpe("claude", cmd, env)
    except FileNotFoundError:
        click.echo("Claude Code nicht gefunden. Installiere es mit:")
        click.echo("  npm install -g @anthropic-ai/claude-code")
        raise SystemExit(1)


# -----------------------------------------------------------------------
# aai start — Start the proxy
# -----------------------------------------------------------------------

@main.command()
@click.option("--port", "-p", default=None, type=int, help="Port (Standard: 8282)")
@click.option("--background", "-b", is_flag=True, help="Im Hintergrund starten")
@click.option("--anthropic-key", envvar="ANTHROPIC_API_KEY", default=None)
@click.option("--openai-key", envvar="OPENAI_API_KEY", default=None)
def start(port, background, anthropic_key, openai_key):
    """Privacy Proxy starten."""
    config = ProxyConfig.load()

    if anthropic_key:
        config.anthropic_api_key = anthropic_key
    if openai_key:
        config.openai_api_key = openai_key
    if port:
        config.port = port

    if not config.anthropic_api_key and not config.openai_api_key:
        click.echo("Kein API Key konfiguriert. Setze mindestens einen:")
        click.echo("  aai config")
        click.echo("  Oder: aai start --anthropic-key sk-ant-...")
        raise SystemExit(1)

    if background:
        _start_proxy_background(config)
    else:
        _start_proxy_foreground(config)


# -----------------------------------------------------------------------
# aai stop — Stop the proxy
# -----------------------------------------------------------------------

@main.command()
def stop():
    """Privacy Proxy stoppen."""
    if PROXY_PID_FILE.exists():
        try:
            pid = int(PROXY_PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            PROXY_PID_FILE.unlink(missing_ok=True)
            click.echo(f"Proxy gestoppt (PID {pid}).")
        except (ProcessLookupError, ValueError):
            PROXY_PID_FILE.unlink(missing_ok=True)
            click.echo("Proxy war bereits gestoppt.")
    else:
        click.echo("Kein laufender Proxy gefunden.")


# -----------------------------------------------------------------------
# aai app — Open the desktop app
# -----------------------------------------------------------------------

@main.command()
def app():
    """Desktop-App oeffnen (Clipboard-Tool + Proxy Control)."""
    config = ProxyConfig.load()

    # Start proxy in background if not running
    _ensure_proxy_running(config)

    # Find the desktop app
    app_path = _find_desktop_app()
    if not app_path:
        click.echo("Desktop-App nicht gefunden.")
        raise SystemExit(1)

    click.echo("🛡  AUSTR.AI Desktop-App wird geoeffnet...")
    subprocess.Popen([sys.executable, app_path])


# -----------------------------------------------------------------------
# aai config — Configure settings
# -----------------------------------------------------------------------

@main.command()
def config():
    """API Keys und Einstellungen konfigurieren."""
    cfg = ProxyConfig.load()

    click.echo("\n🛡  AUSTR.AI Konfiguration\n")

    key = click.prompt(
        "Anthropic API Key",
        default=_mask(cfg.anthropic_api_key) or "(leer — Enter zum Ueberspringen)",
        show_default=False,
    )
    if key and not key.startswith("(") and key != _mask(cfg.anthropic_api_key):
        cfg.anthropic_api_key = key

    key = click.prompt(
        "OpenAI API Key",
        default=_mask(cfg.openai_api_key) or "(leer — Enter zum Ueberspringen)",
        show_default=False,
    )
    if key and not key.startswith("(") and key != _mask(cfg.openai_api_key):
        cfg.openai_api_key = key

    cfg.port = click.prompt("Proxy Port", default=cfg.port, type=int)

    deny = click.prompt(
        "Deny-List (kommagetrennt, z.B. Firmenname,Projektname)",
        default=", ".join(cfg.deny_list) if cfg.deny_list else "(leer)",
        show_default=False,
    )
    if deny and deny != "(leer)":
        cfg.deny_list = [t.strip() for t in deny.split(",") if t.strip()]
    elif deny == "(leer)":
        cfg.deny_list = []

    cfg.save()
    click.echo(f"\n✅ Gespeichert: {CONFIG_DIR / 'proxy.yaml'}")
    click.echo("\nStarte mit:")
    click.echo("  aai claude    — Claude Code durch Proxy")
    click.echo("  aai start     — Proxy fuer andere Apps")
    click.echo("  aai app       — Desktop-App")


# -----------------------------------------------------------------------
# aai status — Show status
# -----------------------------------------------------------------------

@main.command(name="anon")
@click.argument("text", nargs=-1, required=True)
@click.option("--deny", "-d", multiple=True, help="Zusaetzliche Begriffe anonymisieren")
@click.option("--output", "-o", default=None, help="Anonymisierten Text in Datei speichern")
def anonymize(text, deny, output):
    """Text oder Datei anonymisieren (lokal, kein Server-Call)."""
    full_text = " ".join(text)
    if not full_text.strip():
        click.echo("Kein Text angegeben.")
        raise SystemExit(1)

    # Check if input is a file path
    import os
    if os.path.isfile(full_text):
        click.echo(f"📄 Datei erkannt: {full_text}")
        try:
            from .core.extractor import extract_from_file
            result = extract_from_file(full_text)
            click.echo(f"   Format: {result.format}, Seiten: {result.pages}, {len(result.text)} Zeichen")
            full_text = result.text
        except ImportError as e:
            click.echo(f"✗ {e}")
            raise SystemExit(1)
        except Exception as e:
            click.echo(f"✗ Extraktion fehlgeschlagen: {e}")
            raise SystemExit(1)

    click.echo("⏳ Analysiere lokal...")

    from .core import get_engine
    engine = get_engine()
    deny_list = list(deny) if deny else None
    result = engine.anonymize(full_text, deny_list=deny_list)

    if not result.mappings:
        click.echo("ℹ️  Keine sensiblen Daten erkannt.")
        click.echo(full_text)
        return

    click.echo(f"\n✅ {len(result.mappings)} sensible Begriffe geschuetzt:\n")
    for codename, original in result.mappings.items():
        click.echo(f"  {original:30s} → {codename}")
    click.echo(f"\nAnonymisiert:\n{result.anonymized_text}\n")
    click.echo(f"Session: {result.session_id}")

    # Persist mappings to disk for deanon
    if result.mappings:
        _save_last_session(result.mappings, result.session_id)

    if output:
        import os
        with open(output, "w", encoding="utf-8") as f:
            f.write(result.anonymized_text)
        click.echo(f"💾 Gespeichert: {output}")
    else:
        import subprocess
        try:
            subprocess.run(["pbcopy"], input=result.anonymized_text.encode(), check=True, timeout=5)
            click.echo("📋 In Zwischenablage kopiert!")
        except Exception:
            pass


@main.command(name="deanon")
@click.argument("text", nargs=-1, required=True)
def rehydrate(text):
    """LLM-Antwort de-anonymisieren (Codenames durch Originale ersetzen)."""
    full_text = " ".join(text)
    if not full_text.strip():
        click.echo("Kein Text angegeben.")
        raise SystemExit(1)

    # Load last session from disk
    mappings = _load_last_session()
    if not mappings:
        click.echo("Keine gespeicherte Session. Zuerst aai anon ausfuehren.")
        raise SystemExit(1)

    from .core import get_engine
    engine = get_engine()
    restored = engine.rehydrate(full_text, mappings)

    count = sum(1 for k in mappings if k in full_text)
    click.echo(f"\n✅ {count} Begriffe wiederhergestellt:\n")
    click.echo(restored)

    import subprocess
    try:
        subprocess.run(["pbcopy"], input=restored.encode(), check=True, timeout=5)
        click.echo("\n📋 In Zwischenablage kopiert!")
    except Exception:
        pass


@main.command(name="shell")
def shell():
    """Interaktive Shell mit Slash-Commands (/help, /settings, /denylist, ...)."""
    from .interactive import run_interactive
    run_interactive()


@main.command()
def status():
    """Status anzeigen."""
    cfg = ProxyConfig.load()

    proxy_running = _is_proxy_running()

    click.echo(f"\n🛡  AUSTR.AI Status\n")
    click.echo(f"  Proxy:     {'✓ laeuft' if proxy_running else '✗ gestoppt'}")
    click.echo(f"  Port:      {cfg.port}")
    click.echo(f"  Anthropic: {'✓' if cfg.anthropic_api_key else '✗'}")
    click.echo(f"  OpenAI:    {'✓' if cfg.openai_api_key else '✗'}")
    click.echo(f"  Backend:   {"lokal"}")
    click.echo(f"  Deny-List: {len(cfg.deny_list)} Begriffe")
    click.echo(f"  Config:    {CONFIG_DIR / 'proxy.yaml'}")
    click.echo()

    if proxy_running:
        click.echo(f"  Apps verbinden auf: http://localhost:{cfg.port}")
        click.echo(f"  Claude Code:        aai claude")
    else:
        click.echo("  Starten mit: aai start")


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _start_proxy_foreground(config):
    """Start proxy in foreground (blocking)."""
    import uvicorn
    from .server import create_app

    port = config.port
    anth = "✓" if config.anthropic_api_key else "✗"
    oai = "✓" if config.openai_api_key else "✗"

    click.echo(f"""
🛡  AUSTR.AI Privacy Proxy

   http://localhost:{port}

   Anthropic: {anth}    OpenAI: {oai}
   Backend:   {"lokal"}
   Deny-List: {len(config.deny_list)} Begriffe

   Verbinde deine Apps auf http://localhost:{port}
   Ctrl+C zum Beenden
""")

    app = create_app(config)

    # Save PID
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_PID_FILE.write_text(str(os.getpid()))

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", access_log=False)
    finally:
        PROXY_PID_FILE.unlink(missing_ok=True)


def _start_proxy_background(config):
    """Start proxy as background process."""
    if _is_proxy_running():
        click.echo(f"✓ Proxy laeuft bereits auf Port {config.port}.")
        return

    # Kill anything on the port (stale process)
    _kill_port(config.port)

    cmd = [sys.executable, "-m", "austrai_proxy", "start", "--port", str(config.port)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_PID_FILE.write_text(str(proc.pid))

    time.sleep(2)
    if _is_proxy_running():
        click.echo(f"✓ Proxy gestartet im Hintergrund (Port {config.port}, PID {proc.pid})")
    else:
        click.echo("✗ Proxy konnte nicht gestartet werden.")


def _ensure_proxy_running(config):
    """Make sure the proxy is running, start it if not."""
    if not _is_proxy_running():
        if config.anthropic_api_key or config.openai_api_key:
            _start_proxy_background(config)
        else:
            click.echo("Proxy nicht gestartet — kein API Key konfiguriert.")
            click.echo("  aai config")


def _is_proxy_running() -> bool:
    """Check if proxy is running."""
    if not PROXY_PID_FILE.exists():
        return False
    try:
        pid = int(PROXY_PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        PROXY_PID_FILE.unlink(missing_ok=True)
        return False


def _find_desktop_app() -> str | None:
    """Find the desktop app script."""
    # Try relative to this package
    candidates = [
        DESKTOP_APP,
        os.path.expanduser("~/Applications/AUSTR.AI/austrai_app.py"),
        os.path.expanduser("~/.austrai/austrai_app.py"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _kill_port(port: int) -> None:
    """Kill any process using the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            for pid in result.stdout.strip().split("\n"):
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except (ProcessLookupError, ValueError):
                    pass
            time.sleep(1)
    except Exception:
        pass


def _save_last_session(mappings: dict, session_id: str) -> None:
    """Persist mappings to disk so deanon can read them."""
    import json
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    session_file = CONFIG_DIR / "last_session.json"
    session_file.write_text(json.dumps({
        "session_id": session_id,
        "mappings": mappings,
    }, ensure_ascii=False))


def _load_last_session() -> dict | None:
    """Load the last saved session mappings from disk."""
    import json
    session_file = CONFIG_DIR / "last_session.json"
    if not session_file.exists():
        return None
    try:
        data = json.loads(session_file.read_text())
        return data.get("mappings")
    except Exception:
        return None


def _mask(key: str) -> str:
    if not key or len(key) < 12:
        return ""
    return key[:8] + "..." + key[-4:]


if __name__ == "__main__":
    main()

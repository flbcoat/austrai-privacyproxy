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
# aai chat — Open privacy-protected AI chat
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

    # ── Auto-Setup: alles prüfen und installieren ──────────────
    first_run = not (CONFIG_DIR / "proxy.yaml").exists()
    needs_setup = first_run

    # 1. spaCy model
    try:
        import spacy
        spacy.load("de_core_news_sm")
    except (OSError, ImportError):
        needs_setup = True

    if needs_setup:
        click.echo("  Erster Start — wird eingerichtet...\n")
        _auto_setup()
        click.echo("")

    # 2. Tesseract (optional, non-blocking)
    if not shutil.which("tesseract"):
        click.echo("  Hinweis: Tesseract OCR ist nicht installiert.")
        click.echo("  Bildschwärzung funktioniert erst nach der Installation:")
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


def _auto_setup():
    """Automatisches Setup beim ersten Start. Kein User-Input nötig."""

    # 1. spaCy Sprachmodell
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
                    click.echo("    Manuell: python -m spacy download de_core_news_sm")
            except subprocess.TimeoutExpired:
                click.echo("  ⚠ Download dauert zu lange — bitte manuell ausführen:")
                click.echo("    python -m spacy download de_core_news_sm")
    except ImportError:
        click.echo("  ⚠ spaCy nicht installiert")

    # 2. GLiNER Erkennungsmodell (pre-check, download happens on first use)
    gliner_ready = False
    try:
        from huggingface_hub import scan_cache_dir
        cache = scan_cache_dir()
        for repo in cache.repos:
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

    # 3. Python Dependencies
    missing = []
    for mod, name in [("fitz", "PyMuPDF"), ("docx", "python-docx"), ("PIL", "Pillow"),
                      ("pytesseract", "pytesseract"), ("cryptography", "cryptography")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(name)

    if missing:
        click.echo(f"  ⚠ Fehlende Pakete: {', '.join(missing)}")
        click.echo("    pip install austrai")
    else:
        click.echo("  ✓ Alle Pakete installiert")


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
        # Only show codename and entity type, not original PII values
        click.echo(f"  {codename}")
    click.echo(f"\nAnonymisiert:\n{result.anonymized_text}\n")

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

    # Try persistent mapping store first, then JSON fallback
    from .core import get_engine
    engine = get_engine()

    mappings = engine.get_latest_mappings()
    if not mappings:
        mappings = _load_last_session()
    if not mappings:
        click.echo("Keine gespeicherte Session. Zuerst aai anon ausfuehren.")
        raise SystemExit(1)

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


@main.command(name="redact")
@click.argument("file_path", required=True)
@click.option("--output", "-o", default=None, help="Ausgabepfad fuer geschwaerztes Bild/PDF")
@click.option("--deny", "-d", multiple=True, help="Zusaetzliche Begriffe schwaerzen")
def redact(file_path, output, deny):
    """Bild oder PDF schwaerzen (sensible Daten ueberdecken)."""
    import os
    if not os.path.isfile(file_path):
        click.echo(f"Datei nicht gefunden: {file_path}")
        raise SystemExit(1)

    deny_list = list(deny) if deny else None
    ext = os.path.splitext(file_path)[1].lower()

    click.echo(f"⏳ Schwaerze sensible Daten in {os.path.basename(file_path)}...")

    try:
        if ext == ".pdf":
            from .core.image_redactor import redact_pdf_pages
            result = redact_pdf_pages(file_path, output_path=output, deny_list=deny_list)
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
            from .core.image_redactor import redact_image
            result = redact_image(file_path, output_path=output, deny_list=deny_list)
        else:
            click.echo(f"Format '{ext}' nicht unterstuetzt fuer Schwaerzung. Nutze Bilder oder PDFs.")
            raise SystemExit(1)

        click.echo(f"\n✅ {result['entities_redacted']} Bereiche geschwaerzt")
        click.echo(f"Gespeichert: {result['output_path']}")
    except ImportError as e:
        click.echo(f"✗ {e}")
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"✗ Fehler: {e}")
        raise SystemExit(1)


@main.command(name="audio")
@click.argument("file_path", required=True)
@click.option("--model", "-m", default="base", help="Whisper-Modell (tiny/base/small/medium/large)")
@click.option("--lang", "-l", default="de", help="Sprache (de/en/...)")
@click.option("--deny", "-d", multiple=True, help="Zusaetzliche Begriffe anonymisieren")
def audio(file_path, model, lang, deny):
    """Audiodatei transkribieren und anonymisieren (Whisper, lokal)."""
    import os
    if not os.path.isfile(file_path):
        click.echo(f"Datei nicht gefunden: {file_path}")
        raise SystemExit(1)

    deny_list = list(deny) if deny else None
    click.echo(f"⏳ Transkribiere {os.path.basename(file_path)} mit Whisper ({model})...")

    try:
        from .core.audio_pipeline import transcribe_and_anonymize
        result = transcribe_and_anonymize(file_path, model_size=model, language=lang, deny_list=deny_list)

        click.echo(f"\n📝 Transkript ({result['duration_seconds']:.1f}s):")
        click.echo(result["transcript"][:500])
        if len(result["transcript"]) > 500:
            click.echo(f"  ... (+{len(result['transcript'])-500} Zeichen)")

        if result["entity_count"] > 0:
            click.echo(f"\n✅ {result['entity_count']} sensible Begriffe anonymisiert:")
            click.echo(result["anonymized_text"][:500])
        else:
            click.echo("\nℹ️  Keine sensiblen Daten im Transkript erkannt.")

        # Copy anonymized text to clipboard
        import subprocess
        try:
            text = result["anonymized_text"] or result["transcript"]
            subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
            click.echo("\n📋 In Zwischenablage kopiert!")
        except Exception:
            pass

    except ImportError as e:
        click.echo(f"✗ {e}")
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"✗ Fehler: {e}")
        raise SystemExit(1)


@main.command()
def setup():
    """System-Abhaengigkeiten pruefen und installieren. Einmal nach dem Install ausfuehren."""
    import platform
    import shutil

    click.echo("\n🛡  AUSTR.AI Setup — System-Dependencies prüfen\n")

    ok = True

    # 1. Tesseract OCR (needed for image redaction + OCR)
    tesseract = shutil.which("tesseract")
    if tesseract:
        click.echo(f"  ✓ Tesseract OCR: {tesseract}")
    else:
        click.echo("  ✗ Tesseract OCR: nicht gefunden")
        system = platform.system()
        if system == "Darwin":
            click.echo("    Installiere mit: brew install tesseract")
            if click.confirm("    Jetzt installieren?", default=True):
                try:
                    subprocess.run(["brew", "install", "tesseract"], check=True, timeout=300)
                    click.echo("    ✓ Tesseract installiert")
                except Exception as e:
                    click.echo(f"    ✗ Installation fehlgeschlagen: {e}")
                    ok = False
        elif system == "Linux":
            click.echo("    Installiere mit: sudo apt-get install tesseract-ocr")
            if click.confirm("    Jetzt installieren?", default=True):
                try:
                    subprocess.run(["sudo", "apt-get", "install", "-y", "tesseract-ocr"], check=True, timeout=300)
                    click.echo("    ✓ Tesseract installiert")
                except Exception as e:
                    click.echo(f"    ✗ Installation fehlgeschlagen: {e}")
                    ok = False
        else:
            click.echo("    Bitte manuell installieren: https://github.com/tesseract-ocr/tesseract")
            ok = False

    # 2. spaCy German model
    try:
        import spacy
        try:
            spacy.load("de_core_news_sm")
            click.echo("  ✓ spaCy DE-Modell: de_core_news_sm")
        except OSError:
            click.echo("  ✗ spaCy DE-Modell: nicht installiert")
            click.echo("    Installiere...")
            try:
                subprocess.run([sys.executable, "-m", "spacy", "download", "de_core_news_sm"], check=True, timeout=600)
                click.echo("    ✓ spaCy DE-Modell installiert")
            except Exception as e:
                click.echo(f"    ✗ Installation fehlgeschlagen: {e}")
                ok = False
    except ImportError:
        click.echo("  ✗ spaCy: nicht installiert")
        ok = False

    # 3. Python dependencies check
    deps = [
        ("fitz", "PyMuPDF"),
        ("docx", "python-docx"),
        ("openpyxl", "openpyxl"),
        ("PIL", "Pillow"),
        ("pytesseract", "pytesseract"),
        ("faster_whisper", "faster-whisper"),
        ("cryptography", "cryptography"),
    ]
    for module, name in deps:
        try:
            __import__(module)
            click.echo(f"  ✓ {name}")
        except ImportError:
            click.echo(f"  ✗ {name}: nicht installiert")
            ok = False

    if ok:
        click.echo("\n✅ Alles bereit! Starte mit: aai chat\n")
    else:
        click.echo("\n⚠️  Einige Dependencies fehlen. Installiere mit:")
        click.echo(f"  pip install austrai")
        click.echo()


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


def _ensure_proxy_running(config, require_key=True):
    """Make sure the proxy is running, start it if not."""
    if not _is_proxy_running():
        if not require_key or config.anthropic_api_key or config.openai_api_key:
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

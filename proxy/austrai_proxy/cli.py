"""AUSTR.AI CLI — lokaler KI-Assistent mit eingebautem Datenschutz.

Usage:
  aai chat              Chat starten (Hauptbefehl)
  aai anon "Text"       Text anonymisieren
  aai anon datei.pdf    Datei anonymisieren
  aai deanon "Text"     KI-Antwort wiederherstellen
  aai redact bild.png   Bild/PDF schwärzen
  aai audio datei.mp3   Audio transkribieren + anonymisieren
"""

import os
import signal
import subprocess
import sys
import time

import click

from .config import ProxyConfig, DEFAULT_PORT, CONFIG_DIR


PROXY_PID_FILE = CONFIG_DIR / "proxy.pid"


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """AUSTR.AI — Lokaler KI-Assistent mit Datenschutz."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# -----------------------------------------------------------------------
# aai chat — THE main command. Does everything.
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
# aai anon — Anonymize text or file
# -----------------------------------------------------------------------

@main.command(name="anon")
@click.argument("text", nargs=-1, required=True)
@click.option("--deny", "-d", multiple=True, help="Zusaetzliche Begriffe anonymisieren")
@click.option("--output", "-o", default=None, help="Anonymisierten Text in Datei speichern")
def anonymize(text, deny, output):
    """Text oder Datei anonymisieren (lokal, kein Server noetig)."""
    full_text = " ".join(text)
    if not full_text.strip():
        click.echo("Kein Text angegeben.")
        raise SystemExit(1)

    if os.path.isfile(full_text):
        click.echo(f"📄 Datei: {full_text}")
        try:
            from .core.extractor import extract_from_file
            result = extract_from_file(full_text)
            click.echo(f"   {result.format}, {result.pages} Seiten, {len(result.text)} Zeichen")
            full_text = result.text
        except Exception as e:
            click.echo(f"✗ {e}")
            raise SystemExit(1)

    click.echo("⏳ Analysiere...")

    from .core import get_engine
    engine = get_engine()
    result = engine.anonymize(full_text, deny_list=list(deny) if deny else None)

    if not result.mappings:
        click.echo("ℹ️  Keine sensiblen Daten erkannt.")
        click.echo(full_text)
        return

    click.echo(f"\n✅ {len(result.mappings)} Begriffe anonymisiert:\n")
    for codename in result.mappings:
        click.echo(f"  {codename}")
    click.echo(f"\n{result.anonymized_text}\n")

    if result.mappings:
        _save_last_session(result.mappings, result.session_id)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(result.anonymized_text)
        click.echo(f"💾 Gespeichert: {output}")
    else:
        try:
            subprocess.run(["pbcopy"], input=result.anonymized_text.encode(), check=True, timeout=5)
            click.echo("📋 In Zwischenablage kopiert!")
        except Exception:
            pass


# -----------------------------------------------------------------------
# aai deanon — Rehydrate LLM response
# -----------------------------------------------------------------------

@main.command(name="deanon")
@click.argument("text", nargs=-1, required=True)
def rehydrate(text):
    """KI-Antwort de-anonymisieren (Codenames durch Originale ersetzen)."""
    full_text = " ".join(text)
    if not full_text.strip():
        click.echo("Kein Text angegeben.")
        raise SystemExit(1)

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

    try:
        subprocess.run(["pbcopy"], input=restored.encode(), check=True, timeout=5)
        click.echo("\n📋 In Zwischenablage kopiert!")
    except Exception:
        pass


# -----------------------------------------------------------------------
# aai redact — Redact image or PDF
# -----------------------------------------------------------------------

@main.command(name="redact")
@click.argument("file_path", required=True)
@click.option("--output", "-o", default=None, help="Ausgabepfad")
@click.option("--deny", "-d", multiple=True, help="Zusaetzliche Begriffe")
def redact(file_path, output, deny):
    """Bild oder PDF schwaerzen (sensible Daten ueberdecken)."""
    if not os.path.isfile(file_path):
        click.echo(f"Datei nicht gefunden: {file_path}")
        raise SystemExit(1)

    ext = os.path.splitext(file_path)[1].lower()
    click.echo(f"⏳ Schwärze {os.path.basename(file_path)}...")

    try:
        if ext == ".pdf":
            from .core.image_redactor import redact_pdf_pages
            result = redact_pdf_pages(file_path, output_path=output, deny_list=list(deny) if deny else None)
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
            from .core.image_redactor import redact_image
            result = redact_image(file_path, output_path=output, deny_list=list(deny) if deny else None)
        else:
            click.echo(f"Format '{ext}' nicht unterstuetzt. Nutze Bilder oder PDFs.")
            raise SystemExit(1)

        click.echo(f"\n✅ {result['entities_redacted']} Bereiche geschwärzt")
        click.echo(f"Gespeichert: {result['output_path']}")
    except ImportError as e:
        click.echo(f"✗ {e}")
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"✗ {e}")
        raise SystemExit(1)


# -----------------------------------------------------------------------
# aai audio — Transcribe + anonymize audio
# -----------------------------------------------------------------------

@main.command(name="audio")
@click.argument("file_path", required=True)
@click.option("--model", "-m", default="base", help="Whisper-Modell (tiny/base/small/medium/large)")
@click.option("--lang", "-l", default="de", help="Sprache (de/en/...)")
@click.option("--deny", "-d", multiple=True, help="Zusaetzliche Begriffe")
def audio(file_path, model, lang, deny):
    """Audiodatei transkribieren und anonymisieren (lokal)."""
    if not os.path.isfile(file_path):
        click.echo(f"Datei nicht gefunden: {file_path}")
        raise SystemExit(1)

    click.echo(f"⏳ Transkribiere {os.path.basename(file_path)}...")

    try:
        from .core.audio_pipeline import transcribe_and_anonymize
        result = transcribe_and_anonymize(file_path, model_size=model, language=lang,
                                          deny_list=list(deny) if deny else None)

        click.echo(f"\n📝 Transkript ({result['duration_seconds']:.1f}s):")
        click.echo(result["transcript"][:500])

        if result["entity_count"] > 0:
            click.echo(f"\n✅ {result['entity_count']} Begriffe anonymisiert:")
            click.echo(result["anonymized_text"][:500])
        else:
            click.echo("\nℹ️  Keine sensiblen Daten erkannt.")

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
        click.echo(f"✗ {e}")
        raise SystemExit(1)


# -----------------------------------------------------------------------
# Hidden: aai start (for advanced users / server deployment)
# -----------------------------------------------------------------------

@main.command(hidden=True)
@click.option("--port", "-p", default=None, type=int)
@click.option("--host", "-h", default="127.0.0.1")
def start(port, host):
    """Server starten (fuer Entwickler / Server-Deployment)."""
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
    PROXY_PID_FILE.write_text(str(os.getpid()))

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
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_PID_FILE.write_text(str(proc.pid))


def _is_proxy_running() -> bool:
    if not PROXY_PID_FILE.exists():
        return False
    try:
        pid = int(PROXY_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        PROXY_PID_FILE.unlink(missing_ok=True)
        return False


def _kill_port(port: int) -> None:
    try:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5)
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
    """Save session_id only — mappings are in the encrypted MappingStore."""
    import json
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "last_session.json").write_text(
        json.dumps({"session_id": session_id}, ensure_ascii=False)
    )


def _load_last_session() -> dict | None:
    """Load mappings from the encrypted MappingStore via session_id."""
    import json
    f = CONFIG_DIR / "last_session.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
        session_id = data.get("session_id")
        # Legacy: if mappings are still in the file, use them but don't persist
        if data.get("mappings"):
            return data["mappings"]
        # New: look up from encrypted store
        if session_id:
            from .core import get_engine
            engine = get_engine()
            return engine.get_latest_mappings()
        return None
    except Exception:
        return None


def _mask(key: str) -> str:
    if not key or len(key) < 12:
        return ""
    return key[:8] + "..." + key[-4:]


if __name__ == "__main__":
    main()

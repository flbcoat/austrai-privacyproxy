"""Interactive AUSTR.AI shell — control center for privacy settings.

This is NOT an auto-anonymizer. It's a control panel where you manage
settings, deny-lists, proxy, and explicitly anonymize text when needed.

Commands:
  /settings           Show & edit settings (models, keys, thresholds)
  /denylist            Manage deny-list
  /proxy               Start/stop/status of the proxy
  /anonymize TEXT      Explicitly anonymize text
  /status              System status
  /help                Available commands
  /quit                Exit
"""

import os
import signal
import subprocess
import sys
import time

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from .config import ProxyConfig, CONFIG_DIR

COMMANDS = [
    "/settings", "/denylist", "/proxy",
    "/status", "/help", "/quit",
]

STYLE = Style.from_dict({
    "prompt": "#3b82f6 bold",
})

PROXY_PID_FILE = CONFIG_DIR / "proxy.pid"

# Supported LLM providers
PROVIDERS = {
    "anthropic": {"name": "Anthropic (Claude)", "env": "ANTHROPIC_API_KEY", "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-20250414"]},
    "openai": {"name": "OpenAI (GPT)", "env": "OPENAI_API_KEY", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"]},
    "mistral": {"name": "Mistral", "env": "MISTRAL_API_KEY", "models": ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"]},
    "google": {"name": "Google (Gemini)", "env": "GOOGLE_API_KEY", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]},
    "ollama": {"name": "Ollama (lokal)", "env": None, "models": ["llama3.1", "mistral", "qwen2.5", "gemma2"]},
}


def run_interactive():
    """Run the interactive AUSTR.AI shell."""
    config = ProxyConfig.load()
    completer = WordCompleter(COMMANDS, sentence=True)
    session = PromptSession(completer=completer, style=STYLE)

    _print_banner(config)

    while True:
        try:
            text = session.prompt(HTML("<prompt>aai ❯ </prompt>")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Auf Wiedersehen!")
            break

        if not text:
            continue

        if not text.startswith("/"):
            print(f"  Unbekannte Eingabe. Tippe /help fuer alle Befehle.")
            continue

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            _cmd_help()
        elif cmd == "/settings":
            _cmd_settings(config, arg)
        elif cmd == "/denylist":
            _cmd_denylist(config, arg)
        elif cmd == "/proxy":
            _cmd_proxy(config, arg)
        elif cmd == "/status":
            _cmd_status(config)
        elif cmd in ("/quit", "/exit", "/q"):
            print("👋 Auf Wiedersehen!")
            break
        else:
            print(f"  Unbekannter Befehl: {cmd}. Tippe /help")


def _print_banner(config):
    proxy = "✓ aktiv" if _is_proxy_running() else "✗ gestoppt"
    keys = []
    for pid, info in PROVIDERS.items():
        key_attr = f"{pid}_api_key"
        if hasattr(config, key_attr) and getattr(config, key_attr):
            keys.append(info["name"].split(" ")[0])
    keys_str = ", ".join(keys) if keys else "keine Keys"

    print(f"""
  🛡  AUSTR.AI — Privacy Control Center

  Proxy: {proxy}   Keys: {keys_str}   Deny-List: {len(config.deny_list)}
  Modus: Lokal (alles auf deinem Rechner)

  /help fuer alle Befehle
""")


# -----------------------------------------------------------------------
# /help
# -----------------------------------------------------------------------

def _cmd_help():
    print("""
  Befehle:

    /settings                Einstellungen anzeigen & aendern
    /settings keys           API Keys verwalten
    /settings model          Modell auswaehlen
    /settings threshold      Erkennungs-Schwelle anpassen

    /denylist                Deny-List anzeigen
    /denylist add X,Y        Begriffe hinzufuegen
    /denylist remove X       Begriff entfernen
    /denylist clear          Alles leeren

    /proxy start             Proxy starten
    /proxy stop              Proxy stoppen
    /proxy log               Proxy-Logs anzeigen

    /status                  Gesamtstatus
    /quit                    Beenden

  Text anonymisieren: aai anonymize TEXT (im Terminal)
""")


# -----------------------------------------------------------------------
# /settings
# -----------------------------------------------------------------------

def _cmd_settings(config, arg):
    arg = arg.strip().lower()

    if arg == "keys":
        _settings_keys(config)
    elif arg == "model":
        _settings_model(config)
    elif arg == "threshold":
        _settings_threshold(config)
    elif arg:
        print(f"  Unbekannt: /settings {arg}")
        print("  Optionen: /settings keys | model | threshold")
    else:
        _settings_show(config)


def _settings_show(config):
    print(f"""
  🛡  Einstellungen ({CONFIG_DIR / 'proxy.yaml'})

    SpaCy Modell:     {config.spacy_model}
    Schwelle:         {config.confidence_threshold}
    Proxy Port:       {config.port}
    Deny-List:        {len(config.deny_list)} Begriffe
    Modus:            Lokal

  API Keys:""")
    for pid, info in PROVIDERS.items():
        key_attr = f"{pid}_api_key"
        key = getattr(config, key_attr, "") if hasattr(config, key_attr) else ""
        status = f"✓ {_mask(key)}" if key else "✗ nicht gesetzt"
        print(f"    {info['name']:25s} {status}")
    print(f"""
  Aendern: /settings keys | /settings model | /settings threshold
""")


def _settings_keys(config):
    print("\n  API Keys konfigurieren:\n")
    for pid, info in PROVIDERS.items():
        key_attr = f"{pid}_api_key"
        if not hasattr(config, key_attr):
            continue
        current = getattr(config, key_attr, "")
        display = _mask(current) if current else "(leer)"
        print(f"  {info['name']:25s} aktuell: {display}")

        try:
            new_key = input(f"  Neuer Key (Enter = behalten): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if new_key and new_key != display:
            setattr(config, key_attr, new_key)
            print(f"    ✓ Gespeichert")

    config.save()
    print(f"\n  ✅ Keys gespeichert in {CONFIG_DIR / 'proxy.yaml'}\n")


def _settings_model(config):
    print(f"\n  Aktuelles SpaCy-Modell: {config.spacy_model}\n")
    print("  Verfuegbar:")
    print("    1. de_core_news_lg  (560 MB, beste Erkennung)")
    print("    2. de_core_news_md  (45 MB, gut)")
    print("    3. de_core_news_sm  (15 MB, schnell, weniger genau)")
    try:
        choice = input("\n  Auswahl (1/2/3, Enter = behalten): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    models = {"1": "de_core_news_lg", "2": "de_core_news_md", "3": "de_core_news_sm"}
    if choice in models:
        config.spacy_model = models[choice]
        config.save()
        print(f"  ✓ Modell auf {config.spacy_model} gesetzt. Neustart noetig.\n")


def _settings_threshold(config):
    print(f"\n  Aktuelle Erkennungs-Schwelle: {config.confidence_threshold}")
    print("  (0.5 = aggressiv, 0.8 = konservativ, Standard: 0.6)")
    try:
        val = input("  Neuer Wert (Enter = behalten): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if val:
        try:
            config.confidence_threshold = float(val)
            config.save()
            print(f"  ✓ Schwelle auf {config.confidence_threshold} gesetzt.\n")
        except ValueError:
            print("  ✗ Ungueltiger Wert.\n")


# -----------------------------------------------------------------------
# /denylist
# -----------------------------------------------------------------------

def _cmd_denylist(config, arg):
    if not arg:
        if config.deny_list:
            print(f"\n  Deny-List ({len(config.deny_list)} Begriffe):")
            for t in config.deny_list:
                print(f"    • {t}")
        else:
            print("\n  Deny-List ist leer.")
        print("\n  /denylist add Firma,Projekt   — hinzufuegen")
        print("  /denylist remove Begriff      — entfernen")
        print("  /denylist clear               — leeren\n")
        return

    parts = arg.split(maxsplit=1)
    action = parts[0].lower()
    value = parts[1] if len(parts) > 1 else ""

    if action == "add" and value:
        new_terms = [t.strip() for t in value.split(",") if t.strip()]
        existing = set(config.deny_list)
        added = [t for t in new_terms if t not in existing]
        config.deny_list.extend(added)
        config.save()
        print(f"  ✅ {len(added)} Begriffe hinzugefuegt: {', '.join(added)}")
    elif action == "remove" and value:
        before = len(config.deny_list)
        config.deny_list = [t for t in config.deny_list if t.lower() != value.lower()]
        config.save()
        print(f"  ✅ {before - len(config.deny_list)} Begriffe entfernt.")
    elif action == "clear":
        config.deny_list = []
        config.save()
        print("  ✅ Deny-List geleert.")
    else:
        print("  Nutzung: /denylist add X,Y | /denylist remove X | /denylist clear")


# -----------------------------------------------------------------------
# /proxy
# -----------------------------------------------------------------------

def _cmd_proxy(config, arg):
    action = arg.strip().lower() if arg else "status"

    if action == "start":
        if _is_proxy_running():
            print(f"  ✓ Proxy laeuft bereits auf Port {config.port}.")
            return
        _kill_port(config.port)
        cmd = [sys.executable, "-m", "austrai_proxy", "start", "--port", str(config.port)]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PROXY_PID_FILE.write_text(str(proc.pid))
        time.sleep(2)
        if _is_proxy_running():
            print(f"  ✅ Proxy gestartet auf Port {config.port} (PID {proc.pid})")
        else:
            print("  ✗ Proxy konnte nicht gestartet werden.")
    elif action == "stop":
        if PROXY_PID_FILE.exists():
            try:
                pid = int(PROXY_PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                PROXY_PID_FILE.unlink(missing_ok=True)
                print(f"  ✅ Proxy gestoppt.")
            except (ProcessLookupError, ValueError):
                PROXY_PID_FILE.unlink(missing_ok=True)
                print("  Proxy war bereits gestoppt.")
        else:
            print("  Kein laufender Proxy gefunden.")
    elif action == "log":
        log_file = CONFIG_DIR / "proxy.log"
        if log_file.exists():
            lines = log_file.read_text().strip().split("\n")
            last = lines[-20:] if len(lines) > 20 else lines
            print(f"\n  Letzte {len(last)} Log-Eintraege:\n")
            for line in last:
                print(f"  {line}")
            print()
        else:
            print("  Keine Logs vorhanden. Proxy starten mit /proxy start")
    else:
        if _is_proxy_running():
            print(f"  ✓ Proxy laeuft auf http://localhost:{config.port}")
            print(f"  /proxy log    — Logs anzeigen")
            print(f"  /proxy stop   — Stoppen")
        else:
            print(f"  ✗ Proxy gestoppt. /proxy start zum Starten.")


# -----------------------------------------------------------------------
# /status
# -----------------------------------------------------------------------

def _cmd_status(config):
    proxy = "✓ aktiv" if _is_proxy_running() else "✗ gestoppt"
    print(f"""
  🛡  AUSTR.AI Status

    Proxy:       {proxy}
    Port:        {config.port}
    Modus:       Lokal
    SpaCy:       {config.spacy_model}
    Schwelle:    {config.confidence_threshold}
    Deny-List:   {len(config.deny_list)} Begriffe
    Config:      {CONFIG_DIR / 'proxy.yaml'}
""")


# -----------------------------------------------------------------------
# /anonymize
# -----------------------------------------------------------------------

def _cmd_anonymize(config, text):
    if not text:
        print("  Nutzung: /anonymize Dein Text hier")
        return

    print("  ⏳ Analysiere lokal...")

    try:
        from .core import get_engine
        engine = get_engine()
        result = engine.anonymize(text, deny_list=config.deny_list if config.deny_list else None)

        if not result.mappings:
            print("  ℹ️  Keine sensiblen Daten erkannt.")
            return

        print(f"\n  ✅ {len(result.mappings)} sensible Begriffe geschuetzt:\n")
        for codename, original in result.mappings.items():
            print(f"    {original:30s} → {codename}")
        print(f"\n  Anonymisiert:\n  {result.anonymized_text}\n")

        try:
            subprocess.run(["pbcopy"], input=result.anonymized_text.encode(), check=True, timeout=5)
            print("  📋 In Zwischenablage kopiert!")
        except Exception:
            pass

    except Exception as e:
        print(f"  ✗ Fehler: {e}")


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _is_proxy_running():
    if not PROXY_PID_FILE.exists():
        return False
    try:
        pid = int(PROXY_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        PROXY_PID_FILE.unlink(missing_ok=True)
        return False


def _kill_port(port):
    try:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5)
        for pid in result.stdout.strip().split("\n"):
            if pid:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except (ProcessLookupError, ValueError):
                    pass
        time.sleep(1)
    except Exception:
        pass


def _mask(key):
    if not key or len(key) < 12:
        return ""
    return key[:8] + "..." + key[-4:]

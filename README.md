# AUSTR.AI PrivacyProxy

**Privacy Firewall für KI-Dienste.** Erkennt sensible Daten in deinen Texten, Dokumenten und Audiodateien, anonymisiert sie lokal mit nicht-rückverfolgbaren Codenames, und setzt die echten Daten erst in der KI-Antwort wieder ein.

Alles läuft **komplett lokal** auf deinem Rechner. Keine Cloud, kein Drittanbieter, keine Kosten.

🌐 [austr.ai](https://austr.ai) · 📦 [PyPI](https://pypi.org/project/austrai/) · 📄 [MIT Lizenz](LICENSE)

---

## Was es macht

```
Du tippst:    "Thomas Gruber, IBAN AT48 3200 0000 1234 5678"
KI sieht:    "Arion, IBAN [AT_IBAN_1]"
Du siehst:   Die KI-Antwort mit deinen echten Daten
```

Die KI arbeitet genauso gut — weiß aber nicht wer du bist.

## Installation

```bash
pip install austrai
```

Beim ersten Start wird das deutsche Sprachmodell heruntergeladen (~500 MB, einmalig).

### Optionale Erweiterungen

```bash
pip install austrai[docs]     # PDF, DOCX, XLSX, Bilder (OCR)
pip install austrai[audio]    # Audio-Transkription (Whisper)
pip install austrai[memory]   # Semantisches Langzeitgedächtnis
pip install austrai[all]      # Alles
```

### Desktop-App (macOS)

Download: [GitHub Releases](https://github.com/flbcoat/austrai-privacyproxy/releases)

## Befehle

```bash
# Text anonymisieren
aai anon Thomas Gruber bei Innovatech GmbH, IBAN AT48 3200 0000 1234 5678

# Datei anonymisieren (PDF, DOCX, XLSX, TXT, Bilder)
aai anon dokument.pdf

# KI-Antwort deanonymisieren
aai deanon Arion bei Nexon Corp hat die Zahlung bestaetigt

# Bild oder PDF schwärzen (Pixel überdecken)
aai redact scan.png
aai redact rechnung.pdf

# Audio transkribieren + anonymisieren
aai audio sprachnachricht.mp3

# Privacy Proxy starten (für Claude, ChatGPT, Cursor etc.)
aai start

# Einstellungen (API Keys, Deny-List, Schwelle)
aai shell

# Desktop-App öffnen
aai app
```

## Was erkannt wird

| Kategorie | Beispiele | Erkennungsrate |
|---|---|---|
| IBANs, Kontonummern | AT48 3200..., DE89 3704... | 95-99% |
| E-Mail-Adressen | name@firma.at | 95-99% |
| Telefonnummern | +43 1 234 5678 | 95%+ |
| Kreditkarten | Visa, Mastercard, Amex | 95%+ |
| Passwörter, API Keys | Passwort: ..., sk-ant-... | 90-95% |
| IP-Adressen | 192.168.1.100 | 90-95% |
| Personennamen | 2200+ Vornamen (DE, TR, RS/HR/BA, EN, AR, PL, HU, RO) | 80-92% |
| Firmennamen | GmbH, AG, bekannte Firmen | 80-90% |
| Diagnosen, Medikamente | Diagnose: Diabetes... | 80-85% |
| Geburtsdaten | 15.03.1985, 1990-06-22 | 85-90% |
| SVNr, UID-Nr, Firmenbuch | ATU12345678, 1234 567890 | 98%+ |

### Besonders geschützte Daten (DSGVO Art. 9)

- Gesundheitsdaten (Diagnosen, Medikamente, Befunde)
- Connection Strings (postgres://, mongodb://...)
- Bearer Tokens (JWT)
- Private Keys (SSH, RSA)

## Wie es funktioniert

### Codename-Anonymisierung

Sensible Daten werden durch **abstrakte Codenames** ersetzt — keine Übersetzungen, keine Fake-Namen, nichts das ein LLM zurückübersetzen könnte:

- Personen → "Arion", "Brynn", "Cael" (fiktive Namen, keine echte Sprache)
- Firmen → "Nexon Corp", "Velar AG" (fiktive Firmennamen)
- Strukturierte Daten → [AT_IBAN_1], [CREDENTIAL_1] (Bracket-Format)

### Zwei-Pass-Erkennung

1. **Phase 1**: Presidio + SpaCy (regelbasiert + NER) erkennen offensichtliche PII
2. **Phase 2**: Context Learner analysiert die Phase-1-Ergebnisse und findet zusätzliche identifizierende Begriffe (PROPN-Tags, NER-Re-Check, Vektor-Ähnlichkeit)

### Persistenter verschlüsselter Mapping Store

Zuordnungen (Arion → Thomas Gruber) werden lokal in SQLite gespeichert, mit Fernet-AES verschlüsselt. Überlebt Neustarts. Session-TTL konfigurierbar.

### API Proxy

```bash
aai start
# Jetzt: http://localhost:8282
# Unterstützt: Anthropic (Claude), OpenAI (GPT), Mistral,
#              und jedes LLM mit OpenAI-kompatibler API (Ollama, vLLM)
```

Der Proxy anonymisiert jeden Request automatisch und rehydriert die Response — mit Streaming-Support (Sliding-Window-Buffer für SSE).

### Memory Layer (optional)

Anonymisierte Konversationen werden als Vektoren in ChromaDB gespeichert. Bei neuen Prompts wird automatisch relevanter Kontext aus vergangenen Gesprächen hinzugefügt.

```bash
pip install austrai[memory]
```

## Konfiguration

```bash
aai shell

# In der Shell:
/settings keys      # API Keys (Anthropic, OpenAI, Mistral, Google)
/settings model     # SpaCy-Modell wählen (lg/md/sm)
/settings threshold # Erkennungs-Schwelle (0.5-0.8)
/denylist add Firmenname,Projektname
/proxy start
```

Config-Datei: `~/.austrai/proxy.yaml`

## Projektstruktur

```
proxy/austrai_proxy/        # Lokales Tool (pip install austrai)
  core/                     # Privacy Engine
    detector.py             # PII-Erkennung (Presidio + Context Learner)
    anonymizer.py           # Codename-Anonymisierung
    codename_engine.py      # Codename-Generierung
    context_learner.py      # Dokumenten-adaptive Erkennung
    rehydrator.py           # Wiederherstellung der Originaldaten
    mapping_store.py        # Verschlüsselter SQLite Store
    memory.py               # ChromaDB Langzeitgedächtnis
    austrian_recognizers.py # DSGVO-Recognizers (2200+ Vornamen, IPs, etc.)
    image_redactor.py       # Bildschwärzung (OCR + Pixel-Überdeckung)
    audio_pipeline.py       # Whisper-Transkription + Anonymisierung
    llm_detector.py         # Optionale LLM-basierte Erkennung
    extractor.py            # Datei-Extraktion (PDF, DOCX, XLSX, OCR)
  server.py                 # API Proxy (Anthropic + OpenAI Format)
  stream_rehydrator.py      # Streaming-Rehydrierung (SSE)
  cli.py                    # CLI (aai-Befehl)
  interactive.py            # Interaktive Shell (/settings, /denylist)
  config.py                 # Konfiguration

backend/                    # Server-Demo (austr.ai)
desktop/                    # macOS Desktop-App (pywebview)
```

## Sicherheit

- **Komplett lokal**: Keine Verbindung zu unseren Servern
- **AES-Verschlüsselung**: Mappings in SQLite mit Fernet verschlüsselt
- **Fail-Closed**: Proxy blockiert bei Anonymisierungs-Fehler (statt durchzuleiten)
- **Kein PII-Logging**: Sensible Daten werden nicht geloggt
- **Secure Permissions**: Key-Files mit 0o600, Verzeichnisse mit 0o700

## DSGVO

AUSTR.AI unterstützt die DSGVO-Grundsätze:
- **Art. 5(1c)** Datenminimierung — nur anonymisierte Daten verlassen den Rechner
- **Art. 25** Privacy by Design — Anonymisierung als Infrastruktur
- **Art. 32** Sicherheit — AES-Verschlüsselung, lokale Verarbeitung
- **Art. 44-49** Drittlandtransfer — nur anonymisierte Daten an US-Server

⚠️ AUSTR.AI reduziert das DSGVO-Risiko, ersetzt aber keine rechtliche Beratung.

## Lizenz

MIT — frei nutzbar, auch kommerziell.

## Entwickelt von

[FLB.CO.AT](https://flb.co.at) — Kommunikationsberatung und KI-Enablement aus Wien, Österreich.

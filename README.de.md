# AUSTR.AI — Lokaler KI-Assistent mit eingebautem Datenschutz

**Chatte mit KI, ohne deine Daten preiszugeben.** AUSTR.AI anonymisiert sensible Informationen automatisch bevor sie an einen KI-Anbieter gehen und stellt deine echten Daten in der Antwort wieder her. Alles läuft lokal auf deinem Rechner.

[austr.ai](https://austr.ai) · [PyPI](https://pypi.org/project/austrai/) · [MIT Lizenz](LICENSE) · [English Version](README.md)

---

## So funktioniert es

```
Du schreibst:    "Dr. Müller, IBAN AT48 2011 1820 8120 0100"
Du bestätigst:   ✓ 2 Begriffe anonymisiert — [PERSON_1], [AT_IBAN_1]
Die KI sieht:    "Arion, IBAN [AT_IBAN_1]"
Du bekommst:     Die KI-Antwort mit deinen echten Daten
```

Die KI funktioniert genauso gut — weiß aber nicht, wer du bist.

## Schnellstart

```bash
pip install austrai
aai chat
```

Das ist alles. AUSTR.AI lädt beim ersten Start alle Modelle automatisch, öffnet deinen Browser und führt dich durch die Einrichtung. Wähle deinen KI-Anbieter (Ollama für komplett lokal, oder Claude/GPT/Mistral/Gemini mit API-Key) und chatte los.

## Features

- **Chat mit Datenschutz** — Wie ChatGPT, aber jede Nachricht wird anonymisiert bevor sie rausgeht
- **Bestätigungsschritt** — Sieh vor dem Senden was anonymisiert wird. Begriffe per Klick zur Allow-List hinzufügen.
- **Anonymisierungs-Werkzeuge** — 5-Schritt-Pipeline: Text einfügen, Erkennung prüfen, Anonymisierung ansehen, optional an LLM senden, Antwort wiederherstellen
- **Dokument-Analyse** — PDF, DOCX, XLSX, TXT, CSV hochladen — extrahiert und anonymisiert
- **Bildschwärzung** — Bilder hochladen, PII wird per OCR erkannt und geschwärzt
- **Audio-Transkription** — MP3, WAV hochladen — mit Whisper transkribiert und anonymisiert
- **Mehrere KI-Anbieter** — Ollama (100% lokal), Claude, GPT, Mistral, Gemini
- **Allow-List / Deny-List** — Volle Kontrolle über die Anonymisierung
- **Verschlüsselte Speicherung** — Gespräche lokal mit AES verschlüsselt
- **Zweisprachig** — Deutsch und Englisch, automatisch erkannt
- **Open Source** — MIT Lizenz, transparenter Code

## Server-Deployment

Auf dem Firmenserver installieren — Mitarbeiter greifen per Browser von jedem Gerät zu, auch mobil:

```bash
# Auf dem Server
pip install austrai
aai chat --no-browser

# Oder mit Docker
docker compose up -d
```

Mitarbeiter öffnen `https://ki.deine-firma.at/chat` im Browser. Sensible Daten bleiben in der eigenen Infrastruktur.

## CLI-Werkzeuge

```bash
aai anon "Thomas Gruber bei Innovatech GmbH"   # Text anonymisieren
aai anon dokument.pdf                           # Datei anonymisieren
aai deanon "Arion bei Nexon Corp bestätigt"     # Original wiederherstellen
aai redact scan.png                             # Bild schwärzen
aai audio sprachnachricht.mp3                   # Transkribieren + anonymisieren
```

## Was erkannt wird

| Kategorie | Beispiele | Erkennungsrate |
|---|---|---|
| IBANs, Kontonummern | AT48 3200..., DE89 3704... | 95-99% |
| E-Mail-Adressen | name@firma.at | 95-99% |
| Telefonnummern | +43 1 234 5678 | 95%+ |
| SVNr, UID, Firmenbuch | ATU12345678, 1234 567890 | 98%+ |
| Personennamen | 2.200+ Vornamen (DE, TR, RS/HR/BA, EN, AR, PL, HU, RO) | 80-92% |
| Firmennamen | GmbH, AG, bekannte Firmen | 80-90% |
| Kreditkarten, API-Keys | Visa, sk-ant-... | 90-95% |
| Medizinische Daten | Diagnosen, Medikamente | 80-85% |

Drei Erkennungsschichten: **GLiNER** (F1 0.98) + **Presidio/SpaCy** + optionales **lokales LLM** (Ollama).

## Sicherheit

- **Komplett lokal** — Keine Verbindung zu unseren Servern. Alles auf deinem Rechner.
- **AES-Verschlüsselung** — Gespräche und Mappings mit Fernet verschlüsselt
- **Fail-Closed** — Blockiert bei Anonymisierungsfehler (leitet nie ungeschützt weiter)
- **Kein PII-Logging** — Sensible Daten werden nie in Logfiles geschrieben
- **Transparenz-Log** — Prüfe jederzeit was wirklich ans LLM ging (Einstellungen → Transparenz-Log)

## DSGVO

AUSTR.AI unterstützt DSGVO-Konformität:
- **Art. 5(1c)** Datenminimierung — nur anonymisierte Daten verlassen die Infrastruktur
- **Art. 25** Privacy by Design — Anonymisierung als Standard
- **Art. 32** Sicherheit der Verarbeitung — AES-Verschlüsselung, lokale Verarbeitung

> AUSTR.AI reduziert DSGVO-Risiken, ersetzt aber keine Rechtsberatung.

## Roadmap

- **API Proxy** — Middleware zur Integration in bestehende Tools (verfuegbar ueber `aai start`)
- **Datenklassifizierung** — 4-stufige Schutzklassen (Oeffentlich, Intern, Vertraulich, Streng Vertraulich) mit stufenbasierten TTLs
- **Browser Extension** — Direkt in ChatGPT, Claude etc. anonymisieren

## Lizenz

MIT — frei nutzbar, auch kommerziell.

## Entwickelt von

[FLB.CO.AT](https://flb.co.at) — Kommunikationsberatung und KI-Enablement aus Wien, Österreich.

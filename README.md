# AUSTR.AI — Local AI Assistant with Built-in Privacy

**Chat with AI without giving up your data.** AUSTR.AI automatically anonymizes sensitive information before it reaches any AI provider, and restores your real data in the response. Everything runs locally on your machine.

[austr.ai](https://austr.ai) · [PyPI](https://pypi.org/project/austrai/) · [MIT License](LICENSE) · [Deutsche Version](README.de.md)

---

## How it works

```
You type:     "Dr. Müller, IBAN AT48 2011 1820 8120 0100"
You confirm:  ✓ 2 terms anonymized — [PERSON_1], [AT_IBAN_1]
AI sees:      "Arion, IBAN [AT_IBAN_1]"
You get:      The AI response with your real data restored
```

The AI works just as well — but never sees who you are.

## Quick start

```bash
pip install austrai
aai chat
```

That's it. AUSTR.AI downloads all models automatically on first start, opens your browser, and guides you through the setup. Choose your AI provider (Ollama for fully local, or Claude/GPT/Mistral/Gemini with API key) and start chatting.

## Features

- **Chat with privacy** — Like ChatGPT, but every message is anonymized before sending and restored in the response
- **Confirmation step** — See what gets anonymized before you send. Add terms to your allow-list with one click.
- **Anonymization tools** — 5-step pipeline: paste text, see detection, review anonymization, optionally send to LLM, get restored response
- **Document analysis** — Upload PDF, DOCX, XLSX, TXT, CSV — extracted and anonymized
- **Image redaction** — Upload images, PII is detected via OCR and blacked out
- **Audio transcription** — Upload MP3, WAV — transcribed with Whisper and anonymized
- **Multiple AI providers** — Ollama (100% local), Claude, GPT, Mistral, Gemini
- **Allow-list / Deny-list** — Full control over what gets anonymized
- **Encrypted storage** — Conversations stored locally with AES encryption
- **Bilingual** — German and English, auto-detected
- **Open source** — MIT license, transparent code

## Server deployment

Install on your company server — employees access via browser from any device, including mobile:

```bash
# On your server
pip install austrai
aai chat --no-browser

# Or with Docker
docker compose up -d
```

Employees open `https://ai.your-company.com/chat` in their browser. Sensitive data stays within your infrastructure.

## CLI tools

```bash
aai anon "Thomas Gruber at Innovatech GmbH"    # Anonymize text
aai anon document.pdf                          # Anonymize file
aai deanon "Arion at Nexon Corp confirmed"     # Restore original
aai redact scan.png                            # Redact image
aai audio voicenote.mp3                        # Transcribe + anonymize
```

## What gets detected

| Category | Examples | Detection rate |
|---|---|---|
| IBANs, account numbers | AT48 3200..., DE89 3704... | 95-99% |
| Email addresses | name@company.at | 95-99% |
| Phone numbers | +43 1 234 5678 | 95%+ |
| Austrian SSN, Tax ID | ATU12345678, 1234 567890 | 98%+ |
| Person names | 2,200+ first names (DE, TR, RS/HR/BA, EN, AR, PL, HU, RO) | 80-92% |
| Company names | GmbH, AG, well-known firms | 80-90% |
| Credit cards, API keys | Visa, sk-ant-... | 90-95% |
| Medical data | Diagnoses, medications | 80-85% |

Three detection layers: **GLiNER** (F1 0.98) + **Presidio/SpaCy** + optional **local LLM** (Ollama).

## Security

- **Fully local** — No connection to our servers. All processing on your machine.
- **AES encryption** — Conversations and mappings encrypted with Fernet
- **Fail-closed** — Blocks the request if anonymization fails (never passes through unprotected)
- **No PII logging** — Sensitive data is never written to log files
- **Transparency log** — Verify exactly what was sent to the LLM (Settings → Transparency Log)

## GDPR

AUSTR.AI supports GDPR compliance:
- **Art. 5(1c)** Data minimization — only anonymized data leaves your infrastructure
- **Art. 25** Privacy by Design — anonymization as default
- **Art. 32** Security of processing — AES encryption, local processing

> AUSTR.AI reduces GDPR risk but does not replace legal advice.

## Roadmap

- **API Proxy** — Middleware for integration into existing tools (available via `aai start`)
- **Data Classification** — 4-tier protection levels (Public, Internal, Confidential, Restricted) with level-based TTLs
- **Browser Extension** — Anonymize directly in ChatGPT, Claude, etc.

## License

MIT — free to use, including commercially.

## Built by

[FLB.CO.AT](https://flb.co.at) — Communications consulting and AI enablement from Vienna, Austria.

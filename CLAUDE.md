# AUSTR.AI PrivacyProxy

## Core Rule
**Fully local architecture.** User data never leaves the device.
The server at `austr.ai` is a demo website only — no real user traffic through it.

## Structure
```
proxy/austrai_proxy/
  core/              <- Detection, classification, anonymization, codename engine
    classifier.py    <- 4-tier protection levels (v2.2.0)
    gliner_detector.py <- Layer 1: GLiNER PII detection (F1 0.98)
    detector.py      <- Layer 2: Presidio + SpaCy + custom recognizers
    context_learner.py <- Layer 2b: semantic context learning
    llm_detector.py  <- Layer 3: optional local LLM
    anonymizer.py    <- Codenames + bracket replacement
    codename_engine.py <- Pool-based codenames (Arion, Brynn...)
    mapping_store.py <- Encrypted SQLite vault (v2: tiered by protection level)
    rehydrator.py    <- 3-pass restoration + tiered rehydration
    models.py        <- Entity model (with protection_level field)
    austrian_recognizers.py <- AT-specific: UID, IBAN, SVNr, Firmenbuch, etc.
  chat/              <- Chat UI (Vanilla JS, CSS) — Preact migration planned
  server.py          <- Transparent proxy (Anthropic + OpenAI passthrough)
  chat_api.py        <- Chat UI API endpoints (SSE streaming)
  stream_rehydrator.py <- Live streaming rehydration with fuzzy matching
  config.py          <- YAML config (~/.austrai/proxy.yaml)
  cli.py             <- CLI: aai start, aai anon, aai deanon
backend/app/         <- FastAPI demo server (austr.ai, Hetzner Docker)
frontend/            <- Astro SSG demo website (austr.ai)
```

## Stack
- **Proxy**: Python 3.11+, Starlette, GLiNER, spaCy (de_core_news_sm/lg), Presidio, Fernet (AES)
- **Backend**: FastAPI, sentence-transformers, Mistral API
- **Frontend**: Astro 5.x, static SSG, bilingual DE/EN
- **Demo Server**: Docker on Hetzner

## Versions (current)
- Proxy PyPI: `austrai` 2.2.0
- Backend: 2.1.0
- Engine: v3.3 (Classification)

## Key Commands
```bash
# Run locally (starts proxy + chat UI in browser)
aai start
# or: cd proxy/ && python -m austrai_proxy start

# Deploy backend (demo server only)
rsync -avz --exclude '__pycache__' --exclude '.venv' -e "ssh -p 2222" \
  backend/app/ florian@178.104.37.171:/var/www/austrai/backend/app/

# Deploy frontend
cd frontend/ && npm run build
rsync -avz --delete -e "ssh -p 2222" \
  frontend/dist/ florian@178.104.37.171:/var/www/austrai/dist/

# Publish to PyPI (token via env var — never hardcoded)
cd proxy/ && python -m build && python -m twine upload dist/*
```

## Server
Host: `florian@178.104.37.171`, Port: `2222`
Web path: `/var/www/austrai/`
Docker: `docker compose up -d` in `/var/www/austrai/`

## Entity Types (semantic, v2.2.0)
Codename-based: `PERSON`, `ORGANIZATION`, `DOC_METADATA`, `CUSTOM`
Bracket-based: `AT_IBAN`, `AT_SVNR`, `AT_UID_NR`, `AT_FIRMENBUCH_NR`,
`PHONE_NUMBER`, `EMAIL_ADDRESS`, `LOCATION`, `CREDIT_CARD`, `CREDENTIAL`,
`DATE_OF_BIRTH`, `IP_ADDRESS`, `MEDICAL_CONDITION`, `PASSPORT_NUMBER`, `LICENSE_PLATE`

## Protection Levels (v2.2.0)
1=Public (24h TTL), 2=Internal (1h), 3=Confidential (30min), 4=Restricted (5min)
Context-aware upgrade: entities in medical/legal docs get +1 level.
MappingStore v2: encrypted SQLite, partitioned by level, audit log.

## Security Rules
- ALL messages (user + assistant) must be anonymized before LLM send
- Fail-closed: if anonymization fails, block request (503), never pass through
- No PII in logs (debug log, proxy log, audit log)
- CORS: localhost only on proxy server
- Mappings: only in encrypted vault, never in plaintext files
- System prompts: never interpolate user data

## LLM System Prompt (BRACKET_HINT)
Injected when anonymization occurs. Explains to the LLM:
- Data is anonymized, codenames are fictional, brackets are typed placeholders
- Never swap placeholders (DATE_OF_BIRTH is always a date, not an IBAN)
- Reproduce codes exactly, don't mention anonymization

## Planned: Preact Migration
Chat UI will be rebuilt from Vanilla JS to Preact + HTM (no build step).
Reason: innerHTML-based rendering loses event handlers, no reactive state,
cache-busting issues. All backend APIs are ready for new UI features.

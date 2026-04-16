# AUSTR.AI PrivacyProxy

## Core Rule
**Fully local architecture.** User data never leaves the device.
The server at `austr.ai` is a demo website only — no real user traffic through it.

## Structure
```
proxy/austrai_proxy/
  core/          <- Detection, anonymization, classification, codename engine
  chat/          <- Chat UI (CSS + JS), served at localhost:8765/chat
  config.py
  server.py      <- Proxy server (Anthropic + OpenAI passthrough)
  chat_api.py    <- Chat UI API endpoints
backend/app/     <- FastAPI demo server (server-side only)
frontend/        <- Vite demo website
```

## Stack
Python 3.11+, FastAPI, GLiNER (3-layer detection), spaCy (`de_core_news_sm`),
Presidio, Mistral (optional LLM)

## Key Commands
```bash
# Run locally (starts proxy + opens chat UI in browser)
austrai start
# or: python -m austrai_proxy start

# Deploy backend (demo server only)
rsync -avz --exclude '__pycache__' --exclude '.venv' -e "ssh -p 2222" \
  backend/app/ florian@178.104.37.171:/var/www/austrai/backend/app/

# Deploy frontend
rsync -avz --delete -e "ssh -p 2222" \
  frontend/dist/ florian@178.104.37.171:/var/www/austrai/dist/

# Publish to PyPI (token via env var — never hardcoded)
cd proxy/ && python -m build && twine upload dist/*
```

## Server
Host: `florian@178.104.37.171`, Port: `2222`
Web path: `/var/www/austrai/`

## Entity Types
`PERSON`, `LOCATION`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IBAN`,
`CREDENTIAL`, `EU_PII`, `SENSITIVE_DATA`, `AUSTRIAN_*`

## Protection Levels (v2.2.0)
1=Public, 2=Internal, 3=Confidential, 4=Restricted
TTLs: 24h, 1h, 30min, 5min. Context-aware upgrade for medical/legal docs.

"""AUSTR.AI Chat API — endpoints for the privacy-protected chat interface.

Mounted at /chat/* on the proxy server. Provides:
  GET  /chat                   — Serve the chat UI
  POST /chat/api/message       — Send message, receive SSE-streamed response
  GET  /chat/api/settings      — Get current config (keys masked)
  PUT  /chat/api/settings      — Update config
  GET  /chat/api/providers     — Available providers + models
  GET  /chat/api/system-info   — RAM, OS for Ollama model recommendation
"""

import asyncio
import json
import logging
import os
import platform
import time
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse, FileResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from .config import ProxyConfig, CONFIG_DIR
from .stream_rehydrator import StreamRehydrator

logger = logging.getLogger("austrai.chat")

# Directory containing the chat frontend files
CHAT_DIR = Path(__file__).parent / "chat"

# Provider configuration
PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "format": "anthropic",
        "base_url": "https://api.anthropic.com",
        "auth_header": "x-api-key",
        "models": [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
            {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
        ],
    },
    "openai": {
        "name": "OpenAI (GPT)",
        "format": "openai",
        "base_url": "https://api.openai.com",
        "auth_header": "authorization",
        "models": [
            {"id": "gpt-4.1", "name": "GPT-4.1"},
            {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini"},
            {"id": "gpt-4.1-nano", "name": "GPT-4.1 Nano"},
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "o3", "name": "o3"},
            {"id": "o4-mini", "name": "o4-mini"},
        ],
    },
    "mistral": {
        "name": "Mistral",
        "format": "openai",
        "base_url": "https://api.mistral.ai",
        "auth_header": "authorization",
        "models": [
            {"id": "mistral-large-latest", "name": "Mistral Large"},
            {"id": "mistral-small-latest", "name": "Mistral Small"},
            {"id": "codestral-latest", "name": "Codestral"},
        ],
    },
    "google": {
        "name": "Google (Gemini)",
        "format": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "auth_header": "authorization",
        "models": [
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
        ],
    },
    "ollama": {
        "name": "Ollama (lokal)",
        "format": "openai",
        "base_url": "http://localhost:11434",
        "auth_header": None,
        "models": [],  # Discovered dynamically
    },
    "lmstudio": {
        "name": "LM Studio (lokal)",
        "format": "openai",
        "base_url": "http://localhost:1234",
        "auth_header": None,
        "models": [],  # Discovered dynamically via /v1/models
    },
}

# Privacy context prompt — tells the LLM it's working with anonymized data.
# This prevents the LLM from confusing placeholder types (e.g. using a
# DATE_OF_BIRTH code where an IBAN should be) and preserves conversational context.
BRACKET_HINT = (
    "IMPORTANT: The user's text has been automatically anonymized for privacy. "
    "Personal data has been replaced with typed placeholders:\n"
    "- Names are replaced with fictional codenames (e.g. Arion, Brynn, Nexon Corp)\n"
    "- Structured data uses semantic brackets: [DATE_OF_BIRTH_1], [AT_IBAN_1], "
    "[PHONE_NUMBER_1], [LOCATION_1], [MEDICAL_CONDITION_1], [AT_SVNR_1], etc.\n\n"
    "Rules:\n"
    "1. Treat codenames and brackets as if they were real data — respond naturally.\n"
    "2. Reproduce each placeholder EXACTLY as written (same spelling, same number).\n"
    "3. Never swap placeholders — [DATE_OF_BIRTH_1] is always a birth date, "
    "[AT_IBAN_1] is always a bank account.\n"
    "4. Do not mention that the data is anonymized or that you see placeholders.\n"
    "5. If you need to reference the data, use the exact placeholder or codename.\n"
    "6. NEVER put your own square brackets [ ] around values. Only placeholders "
    "that already appear in square brackets in the text may be written with brackets. "
    "All other values, numbers, URLs, and text must be written normally without brackets."
)

_config: ProxyConfig | None = None
_engine = None

# ---------------------------------------------------------------------------
# Debug / Transparency Log
# Stores the last N requests so users can verify what the proxy actually sends
# ---------------------------------------------------------------------------
_debug_log: list[dict] = []
_DEBUG_LOG_MAX = 50


def _extract_spreadsheet_terms(file_path: str, suffix: str) -> list[str]:
    """Extract all unique text values from a spreadsheet.

    For XLSX/CSV files, every text cell is potentially identifying.
    Returns a list of unique terms (>= 2 chars, not pure numbers)
    to be used as deny_list for aggressive anonymization.
    """
    import re
    terms = set()

    # Common words that should NOT be anonymized (column headers, labels)
    SKIP_WORDS = {
        "summe", "gesamt", "total", "durchschnitt", "mittelwert", "anzahl",
        "datum", "monat", "jahr", "quartal", "q1", "q2", "q3", "q4",
        "januar", "februar", "märz", "april", "mai", "juni",
        "juli", "august", "september", "oktober", "november", "dezember",
        "umsatz", "kosten", "gewinn", "verlust", "netto", "brutto",
        "stück", "menge", "preis", "betrag", "prozent", "anteil",
        "name", "adresse", "telefon", "email", "notizen", "status",
        "ja", "nein", "offen", "erledigt", "aktiv", "inaktiv",
        "nr", "nummer", "id", "position", "kategorie", "typ", "art",
        "beschreibung", "bemerkung", "kommentar", "einheit", "währung",
        "eur", "usd", "chf", "gbp",
    }

    try:
        if suffix == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell is not None and isinstance(cell, str):
                            val = cell.strip()
                            if len(val) >= 2 and not re.match(r'^[\d\s.,€$%+-]+$', val):
                                if val.lower() not in SKIP_WORDS:
                                    terms.add(val)
            wb.close()

        elif suffix == ".csv":
            import csv
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.reader(f)
                for row in reader:
                    for cell in row:
                        val = cell.strip()
                        if len(val) >= 2 and not re.match(r'^[\d\s.,€$%+-]+$', val):
                            if val.lower() not in SKIP_WORDS:
                                terms.add(val)
    except Exception as e:
        logger.warning("Spreadsheet term extraction failed: %s", e)

    return list(terms)


def _get_config() -> ProxyConfig:
    global _config
    if _config is None:
        _config = ProxyConfig.load()
    return _config


def _get_engine():
    global _engine
    if _engine is None:
        from .core import get_engine
        _engine = get_engine()
    return _engine


def _mask_key(key: str) -> str:
    if not key or len(key) < 12:
        return ""
    return key[:8] + "..." + key[-4:]


def _get_api_key(provider: str, config: ProxyConfig) -> str:
    return {
        "anthropic": config.anthropic_api_key,
        "openai": config.openai_api_key,
        "mistral": config.mistral_api_key,
        "google": config.google_api_key,
    }.get(provider, "")


def _entity_type_for_codename(codename: str, entities: list) -> str:
    """Extract the entity type for a codename.

    For bracket codenames like [AT_IBAN_1], extract from the bracket.
    For pool codenames like Arion, look up in the entities list.
    """
    if codename.startswith("[") and codename.endswith("]"):
        inner = codename[1:-1]
        # Strip trailing _N counter: AT_IBAN_1 → AT_IBAN
        parts = inner.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        return inner

    # Pool codename (Arion, Brynn, Nexon Corp, etc.) — look up in entities
    for entity in entities:
        if hasattr(entity, 'entity_type') and hasattr(entity, 'text'):
            # Check if this entity's text maps to this codename
            # by checking the anonymizer's codename engine
            pass

    # Fallback: check known pool types
    from .core.codename_engine import PERSON_POOL, ORG_POOL, CUSTOM_POOL
    if codename in PERSON_POOL:
        return "PERSON"
    if codename in ORG_POOL:
        return "ORGANIZATION"
    if codename in CUSTOM_POOL:
        return "CUSTOM"
    return "PERSON"


# ---------------------------------------------------------------------------
# GET /chat — Serve the chat UI
# ---------------------------------------------------------------------------

# Shared cache-control headers for chat assets. Without these, Safari (and
# to a lesser extent Chrome) aggressively cache ES modules by URL. A user who
# upgraded from 2.2.x to 2.3.x could end up with the new app.js but an old
# cached state.js — which produces the notorious
# "SyntaxError: Importing binding name 'signals' is not found" because the
# old state.js never exported `signals`. must-revalidate forces the browser
# to ask the server on every load, with If-Modified-Since/ETag; 304 when
# unchanged, fresh 200 after an upgrade.
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, must-revalidate",
    "Pragma": "no-cache",
}


async def serve_chat(request: Request) -> FileResponse:
    return FileResponse(
        CHAT_DIR / "index.html",
        media_type="text/html",
        headers=_NO_CACHE_HEADERS,
    )


async def serve_favicon(request: Request) -> FileResponse:
    # index.html references <link rel="icon" href="favicon.svg"> relative to
    # /chat/, so the browser requests /chat/favicon.svg. Without this route
    # that lookup 404s and the tab icon falls back to the browser default.
    return FileResponse(
        CHAT_DIR / "favicon.svg",
        media_type="image/svg+xml",
        headers=_NO_CACHE_HEADERS,
    )


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles subclass that adds no-cache headers to every response.

    Starlette's stock StaticFiles sets `Last-Modified` and lets the browser
    decide — which Safari does wrong: it serves from its disk cache without
    revalidation when pages are re-loaded from the same origin. Overriding
    `file_response` lets us inject Cache-Control on every served asset.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        for k, v in _NO_CACHE_HEADERS.items():
            response.headers[k] = v
        return response


# ---------------------------------------------------------------------------
# POST /chat/api/message — Send message, get SSE-streamed response
# ---------------------------------------------------------------------------

async def chat_message(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    message = body.get("message", "").strip()
    provider = body.get("provider", "anthropic")
    model = body.get("model", "")
    system_prompt = body.get("system_prompt", "")
    history = body.get("history", [])  # Previous messages [{role, content}]
    conversation_id = body.get("conversation_id")

    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    config = _get_config()

    # Resolve provider config
    prov = PROVIDERS.get(provider)
    if not prov:
        return JSONResponse({"error": f"Unknown provider: {provider}"}, status_code=400)

    api_format = prov["format"]
    base_url = prov["base_url"]

    # For local providers, use configured URL
    if provider == "ollama":
        base_url = getattr(config, "ollama_url", "http://localhost:11434")
    elif provider == "lmstudio":
        base_url = getattr(config, "lmstudio_url", "http://localhost:1234")

    # Get API key
    api_key = _get_api_key(provider, config)
    if not api_key and provider not in ("ollama", "lmstudio"):
        return JSONResponse({"error": f"No API key configured for {provider}"}, status_code=400)

    # Anonymize the user message
    engine = _get_engine()
    try:
        result = engine.anonymize(
            message,
            deny_list=config.deny_list or None,
            allow_list=config.allow_list or None,
        )
        anonymized_message = result.anonymized_text
        mappings = result.mappings
        entity_count = len(mappings)
    except Exception as e:
        logger.error("Anonymization failed: %s", e)
        return JSONResponse(
            {"error": "Anonymization failed. Message blocked to protect privacy."},
            status_code=503,
        )

    # Anonymize ALL history messages — user AND assistant
    # Assistant messages were rehydrated for display and contain real data.
    # They must be re-anonymized before sending to the LLM.
    anonymized_history = []
    all_mappings = dict(mappings)
    for msg in history:
        content = msg.get("content", "")
        if not content:
            anonymized_history.append(msg)
            continue
        try:
            hist_result = engine.anonymize(
                content,
                deny_list=config.deny_list or None,
                allow_list=config.allow_list or None,
            )
            anonymized_history.append({"role": msg.get("role", "user"), "content": hist_result.anonymized_text})
            all_mappings.update(hist_result.mappings)
        except Exception as e:
            # FAIL-CLOSED: if ANY message can't be anonymized, abort the entire request.
            # Never send un-anonymized data to an external LLM.
            logger.error("History anonymization failed: %s — request blocked (fail-closed)", e)
            return JSONResponse(
                {"error": "Anonymization failed. Message blocked to protect privacy."},
                status_code=503,
            )

    # Inject privacy context prompt whenever ANY anonymization happened
    # (codenames like Arion need it just as much as bracket codes)
    sys_prompt = system_prompt or ""
    if all_mappings:
        sys_prompt = f"{sys_prompt}\n\n{BRACKET_HINT}" if sys_prompt else BRACKET_HINT

    # Build request body based on API format
    if api_format == "anthropic":
        messages = anonymized_history + [{"role": "user", "content": anonymized_message}]
        api_body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": 4096,
        }
        if sys_prompt:
            api_body["system"] = sys_prompt
        url = f"{base_url}/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        # OpenAI-compatible format (OpenAI, Mistral, Ollama)
        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.extend(anonymized_history)
        messages.append({"role": "user", "content": anonymized_message})
        api_body = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        url = f"{base_url}/v1/chat/completions"
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"

    # --- Debug log: record ONLY anonymized data, never originals ---
    _debug_log.append({
        "timestamp": time.time(),
        "anonymized_message": anonymized_message,
        "entity_count": entity_count,
        "codenames_used": list(mappings.keys()),
        "provider": provider,
        "model": model,
        "api_url": url,
        "api_body_messages": [
            {"role": m.get("role", ""), "content": m.get("content", "")[:500]}
            for m in api_body.get("messages", [])
        ],
        "pii_detected": entity_count > 0,
        "pii_removed": anonymized_message != message,
    })
    if len(_debug_log) > _DEBUG_LOG_MAX:
        del _debug_log[:-_DEBUG_LOG_MAX]
    logger.info("Debug: %d PII entities anonymized for %s/%s", entity_count, provider, model)

    # Save user message to persistent storage
    if conversation_id:
        try:
            store = _get_conv_store()
            store.add_message(conversation_id, "user", message,
                              anonymized=anonymized_message,
                              mappings=mappings,
                              entity_count=entity_count)
        except Exception as e:
            logger.error("Failed to save user message: %s", e)

    # Send SSE-streamed response
    async def generate():
        # Send meta event first
        meta = {
            "anonymized_count": entity_count,
            "model": model,
            "provider": provider,
            "mappings_preview": [
                {
                    "type": _entity_type_for_codename(k, result.entities if hasattr(result, 'entities') else []),
                    "codename": k,
                    "protection_level": result.level_map.get(k, 2) if hasattr(result, 'level_map') else 2,
                }
                for k, v in list(mappings.items())[:10]
            ] if mappings else [],
            "max_protection_level": result.max_protection_level if hasattr(result, 'max_protection_level') else 2,
            "doc_type": result.doc_type if hasattr(result, 'doc_type') else "general",
        }
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"

        rehydrator = StreamRehydrator(all_mappings) if all_mappings else None
        full_response = []
        raw_response = []  # Pre-rehydration text (what the LLM actually said)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                async with client.stream("POST", url, json=api_body, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        yield f"event: error\ndata: {json.dumps({'error': error_body.decode()[:500]})}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        # Extract text delta
                        delta_text = None
                        if api_format == "anthropic":
                            if data.get("type") == "error":
                                error_info = data.get("error", {})
                                error_msg = error_info.get("message", "Unknown API error")
                                yield f"event: error\ndata: {json.dumps({'error': f'Anthropic: {error_msg}'})}\n\n"
                                return
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    delta_text = delta.get("text", "")
                        else:
                            # OpenAI-compatible: mid-stream errors come as {"error": {...}}
                            # or (occasionally) as a top-level "error" string.
                            err = data.get("error")
                            if err:
                                if isinstance(err, dict):
                                    error_msg = err.get("message") or err.get("type") or "Unknown API error"
                                else:
                                    error_msg = str(err)
                                yield f"event: error\ndata: {json.dumps({'error': f'{provider}: {error_msg}'})}\n\n"
                                return
                            choices = data.get("choices", [])
                            if choices:
                                delta_text = choices[0].get("delta", {}).get("content")

                        if delta_text is None:
                            continue

                        # Collect raw LLM text (before rehydration)
                        if delta_text:
                            raw_response.append(delta_text)

                        # Rehydrate
                        if rehydrator:
                            text = rehydrator.feed(delta_text)
                        else:
                            text = delta_text

                        if text:
                            full_response.append(text)
                            yield f"data: {json.dumps({'content': text})}\n\n"

            # Flush remaining rehydrator buffer
            if rehydrator:
                remaining = rehydrator.flush()
                if remaining:
                    full_response.append(remaining)
                    yield f"data: {json.dumps({'content': remaining})}\n\n"

            # Done event — get actual count from StreamRehydrator
            restored_count = rehydrator.restored_count if rehydrator else 0
            done_data = {
                'restored_count': restored_count,
                'full_response': ''.join(full_response),
            }
            # Include raw (pre-rehydration) response so the UI can show what the LLM actually saw
            if raw_response and restored_count > 0:
                done_data['raw_response'] = ''.join(raw_response)
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

            # Save assistant message to persistent storage
            if conversation_id and full_response:
                try:
                    store = _get_conv_store()
                    store.add_message(conversation_id, "assistant",
                                      ''.join(full_response))
                except Exception as e:
                    logger.error("Failed to save assistant message: %s", e)

        except httpx.ConnectError as e:
            yield f"event: error\ndata: {json.dumps({'error': f'Connection failed: {e}. Is the provider running?'})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:500]})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# GET/PUT /chat/api/settings
# ---------------------------------------------------------------------------

async def get_settings(request: Request) -> JSONResponse:
    config = _get_config()
    return JSONResponse({
        "anthropic_api_key": _mask_key(config.anthropic_api_key),
        "openai_api_key": _mask_key(config.openai_api_key),
        "mistral_api_key": _mask_key(config.mistral_api_key),
        "google_api_key": _mask_key(config.google_api_key),
        "anthropic_configured": bool(config.anthropic_api_key),
        "openai_configured": bool(config.openai_api_key),
        "mistral_configured": bool(config.mistral_api_key),
        "google_configured": bool(config.google_api_key),
        "deny_list": config.deny_list,
        "allow_list": config.allow_list,
        "confidence_threshold": config.confidence_threshold,
        "spacy_model": config.spacy_model,
        "port": config.port,
        "default_provider": getattr(config, "default_provider", ""),
        "default_model": getattr(config, "default_model", ""),
        "ollama_url": getattr(config, "ollama_url", "http://localhost:11434"),
        "lmstudio_url": getattr(config, "lmstudio_url", "http://localhost:1234"),
        "onboarding_done": (CONFIG_DIR / "proxy.yaml").exists(),
    })


async def update_settings(request: Request) -> JSONResponse:
    global _config
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    config = _get_config()

    # Update only provided fields
    if "anthropic_api_key" in body and not body["anthropic_api_key"].startswith("***"):
        config.anthropic_api_key = body["anthropic_api_key"]
    if "openai_api_key" in body and not body["openai_api_key"].startswith("***"):
        config.openai_api_key = body["openai_api_key"]
    if "mistral_api_key" in body and not body["mistral_api_key"].startswith("***"):
        config.mistral_api_key = body["mistral_api_key"]
    if "google_api_key" in body and not body["google_api_key"].startswith("***"):
        config.google_api_key = body["google_api_key"]
    if "deny_list" in body:
        config.deny_list = body["deny_list"]
    if "allow_list" in body:
        config.allow_list = body["allow_list"]
    if "confidence_threshold" in body:
        config.confidence_threshold = float(body["confidence_threshold"])
    if "default_provider" in body:
        config.default_provider = body["default_provider"]
    if "default_model" in body:
        config.default_model = body["default_model"]
    if "ollama_url" in body:
        config.ollama_url = body["ollama_url"]
    if "lmstudio_url" in body:
        config.lmstudio_url = body["lmstudio_url"]

    config.save()
    _config = config

    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# GET /chat/api/providers — Available providers + models
# ---------------------------------------------------------------------------

async def get_providers(request: Request) -> JSONResponse:
    config = _get_config()
    result = {}

    for pid, prov in PROVIDERS.items():
        api_key = _get_api_key(pid, config)
        configured = bool(api_key) or pid in ("ollama", "lmstudio")
        models = list(prov["models"])

        # Ollama: discover models dynamically via /api/tags
        if pid == "ollama":
            ollama_url = getattr(config, "ollama_url", "http://localhost:11434")
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{ollama_url}/api/tags")
                    if resp.status_code == 200:
                        ollama_models = resp.json().get("models", [])
                        models = [{"id": m["name"], "name": m["name"]} for m in ollama_models]
                        configured = True
            except Exception:
                configured = False

        # LM Studio: discover models dynamically via /v1/models (OpenAI-standard)
        if pid == "lmstudio":
            lmstudio_url = getattr(config, "lmstudio_url", "http://localhost:1234")
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{lmstudio_url}/v1/models")
                    if resp.status_code == 200:
                        lms_models = resp.json().get("data", [])
                        models = [{"id": m["id"], "name": m.get("id", m.get("object", "unknown"))} for m in lms_models]
                        configured = True
            except Exception:
                configured = False

        result[pid] = {
            "name": prov["name"],
            "configured": configured,
            "models": models,
        }

    return JSONResponse(result)


# ---------------------------------------------------------------------------
# GET /chat/api/system-info — For Ollama model recommendations
# ---------------------------------------------------------------------------

async def get_system_info(request: Request) -> JSONResponse:
    from ._platform import get_total_ram_gb
    ram_gb = get_total_ram_gb()

    # Model recommendation based on RAM
    if ram_gb >= 16:
        recommended = {"model": "qwen3.5:3b", "reason": "Best detection quality for your hardware"}
    elif ram_gb >= 8:
        recommended = {"model": "qwen3.5:1.5b", "reason": "Good balance of quality and speed"}
    else:
        recommended = {"model": "qwen3.5:0.8b", "reason": "Lightweight, optimized for your hardware"}

    return JSONResponse({
        "ram_gb": ram_gb,
        "os": platform.system(),
        "arch": platform.machine(),
        "recommended_model": recommended,
    })


# ---------------------------------------------------------------------------
# POST /chat/api/validate-key — Test if an API key works
# ---------------------------------------------------------------------------

async def validate_key(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    provider = body.get("provider", "")
    api_key = body.get("api_key", "")

    if not provider or not api_key:
        return JSONResponse({"valid": False, "error": "Missing provider or key"})

    prov = PROVIDERS.get(provider)
    if not prov:
        return JSONResponse({"valid": False, "error": f"Unknown provider: {provider}"})

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "anthropic":
                resp = await client.post(
                    f"{prov['base_url']}/v1/messages",
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                )
            elif provider == "ollama":
                ollama_url = body.get("ollama_url", "http://localhost:11434")
                resp = await client.get(f"{ollama_url}/api/tags")
            elif provider == "lmstudio":
                lmstudio_url = body.get("lmstudio_url", "http://localhost:1234")
                resp = await client.get(f"{lmstudio_url}/v1/models")
            else:
                # Use cheapest model per provider for validation
                cheap_models = {
                    "openai": "gpt-4.1-nano",
                    "mistral": "mistral-small-latest",
                    "google": "gemini-2.5-flash",
                }
                val_model = cheap_models.get(provider, prov["models"][0]["id"] if prov["models"] else "gpt-4.1-nano")
                resp = await client.post(
                    f"{prov['base_url']}/v1/chat/completions",
                    json={"model": val_model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                    headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
                )

            if resp.status_code in (200, 201):
                return JSONResponse({"valid": True})
            elif resp.status_code == 401:
                return JSONResponse({"valid": False, "error": "Invalid API key"})
            else:
                return JSONResponse({"valid": False, "error": f"API returned status {resp.status_code}"})
    except httpx.ConnectError:
        if provider == "ollama":
            return JSONResponse({"valid": False, "error": "Ollama is not running. Start it with: ollama serve"})
        if provider == "lmstudio":
            return JSONResponse({"valid": False, "error": "LM Studio is not running. Start it and enable the local server."})
        return JSONResponse({"valid": False, "error": "Connection failed"})
    except Exception as e:
        return JSONResponse({"valid": False, "error": str(e)[:200]})


# ---------------------------------------------------------------------------
# POST /chat/api/allow-list/add — Quick-add to allow list from chat
# ---------------------------------------------------------------------------

async def add_to_allow_list(request: Request) -> JSONResponse:
    global _config
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    term = body.get("term", "").strip()
    if not term:
        return JSONResponse({"error": "Empty term"}, status_code=400)

    config = _get_config()
    if term not in config.allow_list:
        config.allow_list.append(term)
        config.save()
        _config = config

    return JSONResponse({"status": "ok", "allow_list": config.allow_list})


# ---------------------------------------------------------------------------
# App factory — creates the chat sub-application
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# POST /chat/api/upload — Extract text from file + anonymize
# ---------------------------------------------------------------------------

async def upload_file(request: Request) -> JSONResponse:
    """Upload a file, extract text, anonymize, return result."""
    form = await request.form()
    file = form.get("file")
    if not file:
        return JSONResponse({"error": "No file uploaded"}, status_code=400)

    # Save to temp file
    import tempfile
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:  # 25MB limit
            return JSONResponse({"error": "File too large (max 25MB)"}, status_code=400)
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = _get_config()
        engine = _get_engine()

        # Determine file type and process
        audio_exts = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}
        image_exts = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
        doc_exts = {".pdf", ".docx", ".xlsx", ".txt", ".csv", ".md", ".json", ".xml"}

        if suffix in audio_exts:
            # Audio: transcribe + anonymize
            try:
                from .core.audio_pipeline import transcribe_and_anonymize
                result = transcribe_and_anonymize(
                    tmp_path,
                    model_size="base",
                    language="de",
                    deny_list=config.deny_list or None,
                )
                return JSONResponse({
                    "type": "audio",
                    "filename": file.filename,
                    "transcript": result["transcript"],
                    "anonymized_text": result["anonymized_text"],
                    "mappings": result["mappings"],
                    "entity_count": result["entity_count"],
                    "duration_seconds": result.get("duration_seconds", 0),
                })
            except ImportError:
                return JSONResponse({"error": "Audio support not installed. Run: pip install austrai && pip install faster-whisper"}, status_code=400)

        elif suffix in image_exts:
            # Image: OCR + anonymize (text extraction mode)
            try:
                from .core.extractor import extract_from_file
                ex = extract_from_file(tmp_path)
                anon_result = engine.anonymize(
                    ex.text,
                    deny_list=config.deny_list or None,
                    allow_list=config.allow_list or None,
                )
                return JSONResponse({
                    "type": "image",
                    "filename": file.filename,
                    "extracted_text": ex.text,
                    "anonymized_text": anon_result.anonymized_text,
                    "mappings": anon_result.mappings,
                    "entity_count": len(anon_result.mappings),
                    "format": ex.format,
                    "warnings": list(ex.warnings),
                })
            except ImportError:
                return JSONResponse({"error": "Image/OCR support not installed. Run: pip install austrai (Neuinstallation nötig)"}, status_code=400)

        elif suffix in doc_exts:
            # Document: extract text + anonymize
            try:
                from .core.extractor import extract_from_file
                ex = extract_from_file(tmp_path)

                # Spreadsheets (XLSX, CSV): aggressive mode — anonymize ALL text terms
                # because in tabular data, every term can potentially identify the source
                deny_list = list(config.deny_list or [])
                is_spreadsheet = suffix in (".xlsx", ".csv")

                if is_spreadsheet:
                    # Extract all unique text values from cells and add as deny_list
                    spreadsheet_terms = _extract_spreadsheet_terms(tmp_path, suffix)
                    deny_list = list(set(deny_list + spreadsheet_terms))

                anon_result = engine.anonymize(
                    ex.text,
                    deny_list=deny_list or None,
                    allow_list=config.allow_list or None,
                )
                return JSONResponse({
                    "type": "spreadsheet" if is_spreadsheet else "document",
                    "filename": file.filename,
                    "extracted_text": ex.text[:500],  # Preview only
                    "anonymized_text": anon_result.anonymized_text,
                    "mappings": anon_result.mappings,
                    "entity_count": len(anon_result.mappings),
                    "format": ex.format,
                    "pages": ex.pages,
                    "chars": len(ex.text),
                    "spreadsheet_mode": is_spreadsheet,
                    "warnings": list(ex.warnings),
                })
            except ImportError:
                return JSONResponse({"error": "Document support not installed. Run: pip install austrai (Neuinstallation nötig)"}, status_code=400)

        else:
            return JSONResponse({"error": f"Unsupported file type: {suffix}"}, status_code=400)

    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# POST /chat/api/redact — Redact image (pixel overlay)
# ---------------------------------------------------------------------------

async def redact_file(request: Request) -> Response:
    """Upload an image/PDF, redact PII, return redacted file."""
    form = await request.form()
    file = form.get("file")
    if not file:
        return JSONResponse({"error": "No file uploaded"}, status_code=400)

    import tempfile, base64
    suffix = Path(file.filename).suffix.lower()

    if suffix not in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp", ".pdf"}:
        return JSONResponse({"error": f"Redaction not supported for {suffix}. Use images or PDFs."}, status_code=400)

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = _get_config()
        deny_list = config.deny_list or None

        if suffix == ".pdf":
            from .core.image_redactor import redact_pdf_pages
            result = redact_pdf_pages(tmp_path, deny_list=deny_list)
        else:
            from .core.image_redactor import redact_image
            result = redact_image(tmp_path, deny_list=deny_list)

        # Read the redacted file and return as base64
        output_path = result["output_path"]
        with open(output_path, "rb") as f:
            redacted_bytes = f.read()

        redacted_b64 = base64.b64encode(redacted_bytes).decode("ascii")
        out_suffix = Path(output_path).suffix

        # Clean up output file
        try:
            os.unlink(output_path)
        except Exception:
            pass

        return JSONResponse({
            "filename": file.filename.replace(suffix, f"_redacted{out_suffix}"),
            "redacted_base64": redacted_b64,
            "mime_type": f"image/{out_suffix[1:]}" if out_suffix != ".pdf" else "application/pdf",
            "entities_redacted": result["entities_redacted"],
        })

    except ImportError:
        return JSONResponse({"error": "Image redaction not installed. Run: pip install austrai (Neuinstallation nötig)"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------

_conv_store = None

def _get_conv_store():
    global _conv_store
    if _conv_store is None:
        from .conversation_store import ConversationStore
        _conv_store = ConversationStore()
    return _conv_store


async def list_conversations(request: Request) -> JSONResponse:
    store = _get_conv_store()
    return JSONResponse(store.list_conversations())


async def create_conversation(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    store = _get_conv_store()
    conv_id = store.create_conversation(
        title=body.get("title", "New Chat"),
        model=body.get("model", ""),
        provider=body.get("provider", ""),
        system_prompt=body.get("system_prompt", ""),
    )
    return JSONResponse({"id": conv_id})


async def get_conversation_messages(request: Request) -> JSONResponse:
    conv_id = request.path_params["id"]
    store = _get_conv_store()
    conv = store.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Not found"}, status_code=404)
    messages = store.get_messages(conv_id)
    return JSONResponse({"conversation": conv, "messages": messages})


async def update_conversation(request: Request) -> JSONResponse:
    conv_id = request.path_params["id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    store = _get_conv_store()
    store.update_conversation(conv_id, **body)
    return JSONResponse({"status": "ok"})


async def delete_conversation(request: Request) -> JSONResponse:
    conv_id = request.path_params["id"]
    store = _get_conv_store()
    store.delete_conversation(conv_id)
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# POST /chat/api/dismiss — Dismiss a term (session + optional allow-list)
# ---------------------------------------------------------------------------

async def dismiss_term(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    term = body.get("term", "").strip()
    permanent = body.get("permanent", False)

    if not term:
        return JSONResponse({"error": "Empty term"}, status_code=400)

    # Always add to session dismiss
    engine = _get_engine()
    engine.dismiss_term(term)

    # Optionally add to permanent allow-list
    if permanent:
        config = _get_config()
        if term not in config.allow_list:
            config.allow_list.append(term)
            config.save()

    return JSONResponse({"status": "ok", "permanent": permanent})


# ---------------------------------------------------------------------------
# Debug / Transparency Endpoints
# ---------------------------------------------------------------------------

async def debug_test(request: Request) -> JSONResponse:
    """Anonymize text without sending to LLM.

    Returns both original and anonymized text side-by-side, plus mappings.
    This lets users verify the proxy works correctly without any LLM involvement.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "Empty text"}, status_code=400)

    config = _get_config()
    engine = _get_engine()

    try:
        # Off-load the sync, CPU-bound detection work to a worker thread so the
        # event loop stays free for parallel requests (dropdowns, conversation
        # listing, validate-key). Without this, the first call does a lazy
        # GLiNER + spaCy load (~60s) and blocks every other endpoint.
        result = await asyncio.to_thread(
            engine.anonymize,
            text,
            deny_list=config.deny_list or None,
            allow_list=config.allow_list or None,
        )
    except Exception as e:
        return JSONResponse({"error": f"Anonymization error: {e}"}, status_code=500)

    # Build detailed entity breakdown with protection levels
    from .core.classifier import LEVEL_LABELS, LEVEL_LABELS_EN
    entities = []
    for codename, original in result.mappings.items():
        entity_type = codename.split("]")[0].replace("[", "") if codename.startswith("[") else "UNKNOWN"
        level = result.level_map.get(codename, 2)
        entities.append({
            "original": original,
            "codename": codename,
            "type": entity_type,
            "protection_level": level,
            "protection_label": LEVEL_LABELS.get(level, "Intern"),
            "protection_label_en": LEVEL_LABELS_EN.get(level, "Internal"),
        })

    # Session info for vault countdown
    session_info = None
    if result.session_id:
        session_info = engine.get_session_info(result.session_id)

    return JSONResponse({
        "original": text,
        "anonymized": result.anonymized_text,
        "mappings": result.mappings,
        "entities": entities,
        "entity_count": len(result.mappings),
        "is_changed": text != result.anonymized_text,
        "confidence_threshold": config.confidence_threshold,
        "allow_list": config.allow_list,
        "deny_list": config.deny_list,
        "max_protection_level": result.max_protection_level,
        "doc_type": result.doc_type,
        "session_id": result.session_id,
        "session_info": session_info,
    })


async def debug_log(request: Request) -> JSONResponse:
    """Return the transparency log — the last N requests sent to LLMs.

    Each entry shows:
    - The original user message
    - The anonymized version that was actually sent to the LLM
    - Mappings (what was replaced with what)
    - Provider, model, timestamp
    - The full message array the LLM received

    This is the honest, machine-verifiable proof of what the proxy does.
    """
    limit = int(request.query_params.get("limit", "20"))
    limit = min(limit, _DEBUG_LOG_MAX)

    # Return in reverse chronological order (newest first)
    entries = list(reversed(_debug_log[-limit:]))

    return JSONResponse({
        "entries": entries,
        "total": len(_debug_log),
        "max_stored": _DEBUG_LOG_MAX,
    })


async def debug_clear(request: Request) -> JSONResponse:
    """Clear the debug log."""
    _debug_log.clear()
    return JSONResponse({"status": "ok", "cleared": True})


async def _warmup_engine() -> None:
    """Pre-load the anonymization engine in a background task.

    GLiNER + spaCy together take ~60s on first call. Triggering the load at
    startup (fire-and-forget) means the server is ready for `/api/settings`
    and `/api/providers` immediately, while the heavy models are warming
    behind the scenes. By the time the user types the first message, the
    engine is usually ready.
    """
    async def _load() -> None:
        try:
            await asyncio.to_thread(_get_engine)
            logger.info("Engine warmup complete")
        except Exception as e:
            logger.warning("Engine warmup failed (will retry on first call): %s", e)

    asyncio.create_task(_load())


def create_chat_app() -> Starlette:
    routes = [
        Route("/", serve_chat, methods=["GET"]),
        Route("/favicon.svg", serve_favicon, methods=["GET"]),
        Route("/api/message", chat_message, methods=["POST"]),
        Route("/api/settings", get_settings, methods=["GET"]),
        Route("/api/settings", update_settings, methods=["PUT"]),
        Route("/api/providers", get_providers, methods=["GET"]),
        Route("/api/system-info", get_system_info, methods=["GET"]),
        Route("/api/validate-key", validate_key, methods=["POST"]),
        Route("/api/allow-list/add", add_to_allow_list, methods=["POST"]),
        Route("/api/upload", upload_file, methods=["POST"]),
        Route("/api/redact", redact_file, methods=["POST"]),
        Route("/api/dismiss", dismiss_term, methods=["POST"]),
        Route("/api/debug/test", debug_test, methods=["POST"]),
        Route("/api/debug/log", debug_log, methods=["GET"]),
        Route("/api/debug/clear", debug_clear, methods=["POST"]),
        Route("/api/conversations", list_conversations, methods=["GET"]),
        Route("/api/conversations", create_conversation, methods=["POST"]),
        Route("/api/conversations/{id}", get_conversation_messages, methods=["GET"]),
        Route("/api/conversations/{id}", update_conversation, methods=["PUT"]),
        Route("/api/conversations/{id}", delete_conversation, methods=["DELETE"]),
        Mount("/css", NoCacheStaticFiles(directory=str(CHAT_DIR / "css")), name="chat-css"),
        Mount("/js", NoCacheStaticFiles(directory=str(CHAT_DIR / "js")), name="chat-js"),
    ]
    return Starlette(routes=routes, on_startup=[_warmup_engine])

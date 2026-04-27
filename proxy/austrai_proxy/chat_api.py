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
from . import router as auto_router
from . import skills as skills_module
from . import projects as projects_module

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
            {"id": "claude-opus-4-7", "name": "Claude Opus 4.7 (1M Context)"},
            {"id": "claude-opus-4-6", "name": "Claude Opus 4.6"},
            {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
            {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
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

# Model capabilities — single source of truth for what each model supports.
# Frontend reads this via /chat/api/providers to render the Advanced panel.
# The Auto-Router + Reasoning-Mapping in chat_message read it at call time.
#
# reasoning_type:
#   "thinking_budget"  -> Anthropic / Gemini: maps effort to budget_tokens
#   "effort"           -> OpenAI o-series: native reasoning_effort parameter
#   None               -> no reasoning support
# reasoning_budgets: effort -> tokens for "thinking_budget" providers.
MODEL_CAPABILITIES: dict[str, dict] = {
    # NOTE 1: Anthropic split the Extended-Thinking API between Claude 4 generations.
    #   Mai-2025 models (claude-*-20250514) use legacy `thinking: {type: "enabled", budget_tokens}`.
    #   Newer Claude 4 (4.1+, 4.5+, 4.6, 4.7) require `thinking: {type: "adaptive"}` plus
    #   `output_config: {effort}`. Sending the wrong shape returns 400 with a clear error.
    # NOTE 2: max_tokens_default is conservative (~2k chat / ~3k reasoning) so answers
    #   stay reasonably short by default. Power users can raise it via Advanced > Max-Tokens.
    #   For high-budget thinking models the legacy "budget_tokens > max_tokens" guard in
    #   _apply_model_params bumps max_tokens automatically (Anthropic requires headroom).
    # --- Anthropic ---
    "claude-opus-4-7":            {"reasoning_type": "thinking_adaptive", "temperature": True, "max_tokens_default": 3072, "tier": "opus",     "context": 1_000_000},
    "claude-opus-4-6":            {"reasoning_type": "thinking_adaptive", "temperature": True, "max_tokens_default": 3072, "tier": "opus",     "context": 200_000},
    "claude-sonnet-4-6":          {"reasoning_type": "thinking_adaptive", "temperature": True, "max_tokens_default": 3072, "tier": "sonnet",   "context": 200_000},
    "claude-opus-4-20250514":     {"reasoning_type": "thinking_budget",   "temperature": True, "max_tokens_default": 3072, "tier": "opus",     "context": 200_000},
    "claude-sonnet-4-20250514":   {"reasoning_type": "thinking_budget",   "temperature": True, "max_tokens_default": 3072, "tier": "sonnet",   "context": 200_000},
    "claude-haiku-4-5-20251001":  {"reasoning_type": None,                "temperature": True, "max_tokens_default": 2048, "tier": "haiku",    "context": 200_000},
    # --- OpenAI ---
    "gpt-4.1":                    {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "flagship", "context": 1_000_000},
    "gpt-4.1-mini":               {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "small"},
    "gpt-4.1-nano":               {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "nano"},
    "gpt-4o":                     {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "vision"},
    "o3":                         {"reasoning_type": "effort", "reasoning_values": ["minimal", "low", "medium", "high"], "temperature": False, "max_tokens_default": 3072, "tier": "reasoning"},
    "o4-mini":                    {"reasoning_type": "effort", "reasoning_values": ["minimal", "low", "medium", "high"], "temperature": False, "max_tokens_default": 3072, "tier": "reasoning"},
    # --- Mistral / Google ---
    "mistral-large-latest":       {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "flagship"},
    "mistral-small-latest":       {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "small"},
    "codestral-latest":           {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "code"},
    "gemini-2.5-pro":             {"reasoning_type": "thinking_budget", "temperature": True, "max_tokens_default": 3072, "tier": "flagship"},
    "gemini-2.5-flash":           {"reasoning_type": "thinking_budget", "temperature": True, "max_tokens_default": 2048, "tier": "small"},
}

_DEFAULT_CAPS = {"reasoning_type": None, "temperature": True, "max_tokens_default": 2048, "tier": "local"}

# Map reasoning_effort (low/medium/high) to Anthropic thinking budget_tokens.
# Anthropic recommends >1024 as minimum useful budget.
_THINKING_BUDGETS = {"low": 1024, "medium": 4096, "high": 16384}


def _normalize_local_url(url: str) -> str:
    """Normalize a user-entered Ollama/LMStudio base URL.

    Users frequently paste copies that include trailing path segments like
    `/api`, `/api/tags`, `/v1` or stray slashes. The validator and request-
    builder both append their own paths, so leftover suffixes turn correct
    URLs into 404s. This strips known suffixes and trailing whitespace/slash.

    Examples:
        "http://localhost:11434/api"        -> "http://localhost:11434"
        "http://localhost:11434/api/tags/"  -> "http://localhost:11434"
        "http://localhost:11434/v1"         -> "http://localhost:11434"
        "  http://localhost:11434/  "       -> "http://localhost:11434"
    """
    if not isinstance(url, str):
        return url
    u = url.strip().rstrip("/")  # strip trailing slash FIRST so suffix-checks match
    # Strip in order, longest first, otherwise '/api' would consume '/api/tags'
    for suffix in ("/api/tags", "/api/generate", "/api", "/v1/models", "/v1/chat/completions", "/v1"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    return u.rstrip("/")


def _caps_for(model_id: str) -> dict:
    """Lookup capabilities for a model, with heuristic fallback for unknown IDs.

    Discovery may find newer model IDs that are not in MODEL_CAPABILITIES yet.
    Instead of returning the generic default (which would hide reasoning
    support), pattern-match the family so e.g. a freshly-released
    `claude-opus-4-8-<date>` still reports thinking_budget support.
    """
    exact = MODEL_CAPABILITIES.get(model_id)
    if exact:
        return exact

    mid = (model_id or "").lower()

    # Anthropic family heuristics — Claude 4+ families all support extended
    # thinking (except Haiku). The Extended-Thinking API SHAPE depends on
    # release vintage:
    #   - DATED model IDs (claude-sonnet-4-5-20250929, claude-opus-4-20250514,
    #     claude-sonnet-4-5-20250929 etc. — ANY id ending in YYYYMMDD) use
    #     the legacy `thinking_budget` form (`type: enabled`, budget_tokens).
    #   - UNDATED marketing IDs (claude-opus-4-7, claude-sonnet-4-6, ...)
    #     use `thinking_adaptive` plus `output_config.effort`.
    # Sending `adaptive` to a dated model returns 400 "adaptive thinking is
    # not supported on this model" — caught in production on Sonnet 4.5
    # (claude-sonnet-4-5-20250929).
    import re as _re
    _DATED_ID_RE = _re.compile(r"\d{8}$")

    def _claude_thinking_type(mid: str) -> str:
        return "thinking_budget" if _DATED_ID_RE.search(mid) else "thinking_adaptive"

    if "claude-opus" in mid or "opus-" in mid:
        return {"reasoning_type": _claude_thinking_type(mid), "temperature": True,
                "max_tokens_default": 3072, "tier": "opus"}
    if "claude-sonnet" in mid or "sonnet-" in mid:
        return {"reasoning_type": _claude_thinking_type(mid), "temperature": True,
                "max_tokens_default": 3072, "tier": "sonnet"}
    if "claude-haiku" in mid or "haiku-" in mid:
        return {"reasoning_type": None, "temperature": True,
                "max_tokens_default": 2048, "tier": "haiku"}

    # OpenAI o-series reasoning family (o1/o3/o4/o5 and variants)
    if mid.startswith(("o1", "o3", "o4", "o5")) or mid.startswith("chatgpt-o"):
        return {"reasoning_type": "effort",
                "reasoning_values": ["minimal", "low", "medium", "high"],
                "temperature": False, "max_tokens_default": 8192, "tier": "reasoning"}

    # OpenAI GPT-family chat models
    if mid.startswith("gpt-"):
        return {"reasoning_type": None, "temperature": True,
                "max_tokens_default": 4096, "tier": "chat"}

    # Google Gemini thinking models
    if "gemini" in mid and ("2.5" in mid or "3" in mid):
        return {"reasoning_type": "thinking_budget", "temperature": True,
                "max_tokens_default": 8192, "tier": "flagship"}

    # Unknown — safe defaults
    return _DEFAULT_CAPS


# ---------------------------------------------------------------------------
# Dynamic model discovery
# ---------------------------------------------------------------------------
# All major cloud LLM providers expose a /v1/models endpoint that returns the
# models the configured key has access to. We query it on demand and cache
# results for 5 minutes so /chat/api/providers stays fast on repeat calls.
# This frees us from hardcoding model IDs that go stale.
#
# Filtering: each provider returns more than just chat models (embeddings,
# TTS, audio, vision-only previews etc.). We keep only models the chat
# endpoint can actually use.
_DISCOVERY_CACHE: dict[str, dict] = {}  # provider_id -> {time, models}
_DISCOVERY_TTL = 300  # 5 minutes

# Known non-chat OpenAI model fragments we always exclude from the dropdown.
_OPENAI_EXCLUDE = ("embedding", "embed", "whisper", "tts", "dall-e", "moderation",
                   "babbage", "davinci-002", "audio", "transcribe", "realtime",
                   "image", "search-")


async def _discover_models(provider_id: str, api_key: str, client) -> list | None:
    """Query the provider for the model list its key has access to.

    Returns the discovered list, or None if discovery isn't possible (no key,
    network failure, unknown provider). On None, callers fall back to the
    hardcoded PROVIDERS[pid]['models'] list.
    """
    if not api_key or provider_id not in ("anthropic", "openai", "mistral", "google"):
        return None

    now = time.time()
    cached = _DISCOVERY_CACHE.get(provider_id)
    if cached and (now - cached["time"]) < _DISCOVERY_TTL:
        return cached["models"]

    try:
        if provider_id == "anthropic":
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning("Anthropic /v1/models returned %d", resp.status_code)
                return None
            data = resp.json().get("data", [])
            models = [
                {"id": m["id"], "name": m.get("display_name", m["id"])}
                for m in data
                if m.get("type") == "model" and m.get("id")
            ]

        elif provider_id == "openai":
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning("OpenAI /v1/models returned %d", resp.status_code)
                return None
            data = resp.json().get("data", [])
            models = []
            for m in data:
                mid = m.get("id", "")
                if not mid:
                    continue
                if any(x in mid for x in _OPENAI_EXCLUDE):
                    continue
                # Chat-relevant: GPT-x, o-series (o1/o3/o4/o5), chatgpt-x
                if mid.startswith(("gpt-", "o1", "o3", "o4", "o5", "chatgpt-")):
                    models.append({"id": mid, "name": mid})
            # Sort: newest-feeling-first heuristic by name
            models.sort(key=lambda x: x["id"], reverse=True)

        elif provider_id == "mistral":
            resp = await client.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning("Mistral /v1/models returned %d", resp.status_code)
                return None
            data = resp.json().get("data", [])
            models = [
                {"id": m["id"], "name": m["id"]}
                for m in data
                if m.get("id") and "embed" not in m["id"].lower()
            ]

        elif provider_id == "google":
            # Gemini API: API key as ?key= query param, no Authorization header.
            resp = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning("Gemini /v1beta/models returned %d", resp.status_code)
                return None
            data = resp.json().get("models", [])
            models = []
            for m in data:
                name = m.get("name", "")
                if not name:
                    continue
                # generateContent = chat-capable (excludes embedding-only models)
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    short_id = name.replace("models/", "")
                    models.append({
                        "id": short_id,
                        "name": m.get("displayName") or short_id,
                    })

        else:
            return None

        _DISCOVERY_CACHE[provider_id] = {"time": now, "models": models}
        logger.info("Discovered %d models for %s", len(models), provider_id)
        return models

    except Exception as e:
        logger.warning("Model discovery failed for %s: %s", provider_id, e)
        return None


def _invalidate_discovery_cache(provider_id: str | None = None) -> None:
    """Drop cached discovery results. Called when API keys change so the next
    /providers call re-queries the upstream with the fresh key.
    """
    if provider_id is None:
        _DISCOVERY_CACHE.clear()
    else:
        _DISCOVERY_CACHE.pop(provider_id, None)


def _snapshot_configured_providers(config) -> dict:
    """Compact snapshot of provider-configuration state, used both by the
    /chat/api/providers response (async) and by the Auto-Router (sync).
    Kept in one place to avoid drift between the two views.
    """
    snap: dict[str, dict] = {}
    for pid, prov in PROVIDERS.items():
        api_key = _get_api_key(pid, config)
        configured = bool(api_key) or pid in ("ollama", "lmstudio")
        snap[pid] = {
            "configured": configured,
            "models": list(prov.get("models", [])),
            "name": prov.get("name", pid),
        }
    return snap


def _apply_model_params(
    api_body: dict,
    api_format: str,
    model: str,
    reasoning_effort: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
) -> None:
    """Mutate api_body in place to add reasoning / temperature / top_p / max_tokens
    according to what the model supports. Silently drops unsupported params
    so we never send invalid requests to the provider.
    """
    caps = _caps_for(model)

    # max_tokens (both formats accept it; Anthropic requires it)
    if max_tokens is not None and max_tokens > 0:
        api_body["max_tokens"] = int(max_tokens)
    elif "max_tokens" not in api_body:
        api_body["max_tokens"] = caps.get("max_tokens_default", 4096)

    # Reasoning. Three shapes depending on provider/model generation:
    #   - thinking_budget   (Anthropic Mai 2025): {type: "enabled", budget_tokens: N}
    #   - thinking_adaptive (Anthropic 4.1+):     {type: "adaptive"} + output_config.effort
    #   - effort            (OpenAI o-series):    reasoning_effort native param
    # "off" means: send nothing, model behaves as a normal chat model.
    rtype = caps.get("reasoning_type")
    if reasoning_effort == "off" or not rtype:
        pass  # nothing to add
    elif rtype == "thinking_budget" and reasoning_effort in _THINKING_BUDGETS:
        budget = _THINKING_BUDGETS[reasoning_effort]
        api_body["thinking"] = {"type": "enabled", "budget_tokens": budget}
        # Anthropic requires max_tokens > budget_tokens. With high reasoning
        # (budget=16384) and a default max_tokens of 8192 we'd get a 400.
        current_max = api_body.get("max_tokens", caps.get("max_tokens_default", 4096))
        if current_max <= budget:
            api_body["max_tokens"] = budget + 2048
    elif rtype == "thinking_adaptive" and reasoning_effort in ("low", "medium", "high"):
        # Newer Claude 4 (Opus 4.6/4.7, Sonnet 4.5/4.6 etc.). Anthropic decides
        # the budget itself; we only express user-intent via effort.
        api_body["thinking"] = {"type": "adaptive"}
        api_body["output_config"] = {"effort": reasoning_effort}
    elif rtype == "effort":
        allowed = caps.get("reasoning_values", ["minimal", "low", "medium", "high"])
        if reasoning_effort in allowed:
            api_body["reasoning_effort"] = reasoning_effort

    # Temperature / top_p. Anthropic recently tightened its API: Claude 4
    # models reject requests that specify BOTH `temperature` and `top_p`
    # ("temperature and top_p cannot both be specified for this model").
    # Reproduced 26.04.2026 on claude-haiku-4-5-20251001 with default
    # advanced-mode values (temperature=1.0, top_p=1.0). Defensive rule:
    # for Anthropic provider, only send temperature; drop top_p. Other
    # providers (OpenAI, Mistral, Gemini) still accept both.
    if caps.get("temperature") and temperature is not None:
        api_body["temperature"] = float(temperature)
    if caps.get("temperature") and top_p is not None and api_format != "anthropic":
        api_body["top_p"] = float(top_p)


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

# Math/LaTeX rendering hint. The chat UI uses KaTeX to render formulas; KaTeX
# only triggers on explicit delimiters. Without this hint many LLMs default to
# Unicode math symbols ("²", "≤", "α") which cannot be re-rendered. By asking
# for explicit $$..$$ / $..$ delimiters we get the same output that KaTeX
# turns into clean formulas. Always injected (cheap, helpful) — even when no
# anonymization happened.
LATEX_HINT = (
    "FORMATTING — Math notation:\n"
    "When you write mathematical expressions, ALWAYS use LaTeX delimiters:\n"
    "  - Display equations on their own line: wrap with $$...$$ (e.g. $$x^2 + y^2 = z^2$$).\n"
    "  - Inline math inside a sentence: wrap with $...$ (e.g. \"the value $a + b$ equals\").\n"
    "Do NOT output formulas as plain text or unicode symbols (e.g. avoid 'a² + b² = c²' — "
    "write '$a^2 + b^2 = c^2$' instead). Do NOT duplicate the formula in both forms. "
    "The chat UI renders LaTeX automatically; users will see beautiful formulas only if "
    "you use these delimiters consistently."
)

_config: ProxyConfig | None = None
_engine = None

# ---------------------------------------------------------------------------
# Debug / Transparency Log
# Stores the last N requests so users can verify what the proxy actually sends
# ---------------------------------------------------------------------------
_debug_log: list[dict] = []
_DEBUG_LOG_MAX = 50

# Upload-Limits — gelten für /api/upload und /api/redact.
# Audio wird mit einem höheren Limit (100 MB) erlaubt, weil .wav-Dateien
# von längeren Transkripten schnell >25 MB werden.
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024           # 25 MB für Dokumente + Bilder + Redact
_MAX_AUDIO_UPLOAD_BYTES = 100 * 1024 * 1024    # 100 MB für Audio-Dateien

# Whitelists — wenn Suffix nicht drin ist, reject.
_AUDIO_EXTS = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"})
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"})
_DOC_EXTS = frozenset({".pdf", ".docx", ".xlsx", ".txt", ".csv", ".md", ".json", ".xml"})
_REDACT_EXTS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp", ".pdf"})


import re
_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._\-]+")

def _safe_filename(raw: str | None, fallback: str = "file") -> str:
    """Sanitise a client-supplied filename for safe use in responses and
    output paths. Removes path components, null bytes, and everything
    outside [A-Za-z0-9._-]. Caps length at 128 chars. Never returns an
    empty string.
    """
    if not raw:
        return fallback
    # Strip path components — defend against "/etc/passwd" oder "C:\..\"
    name = Path(raw).name
    # Remove null bytes explicitly (some OSes treat `\x00` as a separator).
    name = name.replace("\x00", "")
    # Collapse any unsafe run into a single underscore.
    name = _FILENAME_UNSAFE.sub("_", name)
    # Cap length (.tar.gz-style double suffixes bleiben erhalten, weil 128
    # chars großzügig sind).
    name = name[:128]
    return name or fallback


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


_MASK_PREFIX = "***"


def _mask_key(key: str) -> str:
    """Return a display-safe placeholder of the API key.

    Format: '***' + last-4 chars (e.g. '***xyz1'). The '***' prefix is the
    canonical marker that _is_masked_key() recognizes — keep this in sync.
    """
    if not key or len(key) < 12:
        return ""
    return f"{_MASK_PREFIX}{key[-4:]}"


def _is_masked_key(val: str) -> bool:
    """True if the value is the masked-display version of a key, NOT the real key.

    update_settings() uses this to avoid overwriting the stored key with the
    placeholder string when the user saves Settings without re-entering the
    key (the frontend always echoes back whatever it displayed).

    Recognizes:
      * empty string (no-op = leave unchanged)
      * canonical mask prefix '***'
      * legacy '...' separator (older _mask_key format) for safety
    """
    if not val:
        return True
    if val.startswith(_MASK_PREFIX):
        return True
    # Legacy mask format 'sk-ant-1...xyz' (8 + 3 + 4 = 15 chars). Real keys are
    # always > 30 chars, so anything short with '...' is a mask leftover.
    if "..." in val and len(val) <= 30:
        return True
    return False


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
    user_provider = body.get("provider", "anthropic")
    user_model = body.get("model", "")
    # Advanced-mode params (opt-in). Defaults preserve legacy basic behavior.
    auto_route = bool(body.get("auto_route", False))
    reasoning_effort = body.get("reasoning_effort") or "medium"
    temperature_req = body.get("temperature")  # None -> leave out (provider default)
    top_p_req = body.get("top_p")
    max_tokens_req = body.get("max_tokens")
    system_prompt = body.get("system_prompt", "")
    history = body.get("history", [])  # Previous messages [{role, content}]
    conversation_id = body.get("conversation_id")
    # Phase 2/3: skill activation + knowledge-base context (Anti-Magic-RAG)
    skill_slug = (body.get("skill_slug") or "").strip().lower() or None
    project_slug = (body.get("project_slug") or "").strip().lower() or None
    attached_chunk_ids_raw = body.get("attached_chunk_ids") or []
    attached_chunk_ids: list[int] = []
    if isinstance(attached_chunk_ids_raw, list):
        for cid in attached_chunk_ids_raw[:20]:
            try:
                attached_chunk_ids.append(int(cid))
            except (TypeError, ValueError):
                continue

    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    config = _get_config()

    # Provider resolution. In auto-route we defer model selection until AFTER
    # anonymization (privacy invariant: the router never sees raw user input).
    _configured_snapshot: dict | None = None
    if auto_route:
        _configured_snapshot = _snapshot_configured_providers(config)
        if not any(p.get("configured") for p in _configured_snapshot.values()):
            return JSONResponse({"error": "No provider configured"}, status_code=400)
        provider, model, prov, api_format, base_url, api_key = (None, None, None, None, None, None)
    else:
        provider, model = user_provider, user_model
        prov = PROVIDERS.get(provider)
        if not prov:
            return JSONResponse({"error": f"Unknown provider: {provider}"}, status_code=400)
        api_format = prov["format"]
        base_url = prov["base_url"]
        if provider == "ollama":
            base_url = getattr(config, "ollama_url", "http://localhost:11434")
        elif provider == "lmstudio":
            base_url = getattr(config, "lmstudio_url", "http://localhost:1234")
        api_key = _get_api_key(provider, config)
        if not api_key and provider not in ("ollama", "lmstudio"):
            return JSONResponse({"error": f"No API key configured for {provider}"}, status_code=400)

    # Anonymize the user message.
    #
    # engine.anonymize() ist CPU-bound (GLiNER + spaCy + Presidio), darum
    # wandert es in einen Worker-Thread via asyncio.to_thread. Sonst würde
    # der Event-Loop für 100ms-5s blockiert und andere in-flight Requests
    # (z.B. Sidebar-Refresh, Privacy-Panel-Updates) stoppen.
    engine = _get_engine()
    deny_list_arg = config.deny_list or None
    allow_list_arg = config.allow_list or None

    def _anonymize_sync(text: str):
        return engine.anonymize(text, deny_list=deny_list_arg, allow_list=allow_list_arg)

    try:
        result = await asyncio.to_thread(_anonymize_sync, message)
        anonymized_message = result.anonymized_text
        mappings = result.mappings
        entity_count = len(mappings)
    except Exception as e:
        logger.error("Anonymization failed: %s", e)
        return JSONResponse(
            {"error": "Anonymization failed. Message blocked to protect privacy."},
            status_code=503,
        )

    # Anonymize ALL history messages — user AND assistant.
    #
    # Frontend schickt für Assistant-Messages bevorzugt den `raw_response`
    # (LLM-Output mit Codenames, noch nicht rehydriert) als content mit
    # `{"already_anonymized": true}`. In dem Fall überspringen wir die
    # Re-Detection und übernehmen den Text 1:1 — das ist deutlich sicherer
    # als eine neue probabilistische Detection auf rehydriertem Text,
    # und verhindert Codename-Instabilität zwischen Turns (H-10 Fix).
    anonymized_history = []
    all_mappings = dict(mappings)
    for msg in history:
        content = msg.get("content", "")
        if not content:
            anonymized_history.append(msg)
            continue
        if msg.get("already_anonymized") is True:
            anonymized_history.append({"role": msg.get("role", "user"), "content": content})
            continue
        try:
            hist_result = await asyncio.to_thread(_anonymize_sync, content)
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

    # Skill system-prompt injection (Phase 2). The skill body is treated
    # as user-controlled content and routed through the SAME anonymisation
    # pipeline as the user message, so PII inside a skill body never
    # reaches the LLM in plain text. This is the "no exception" privacy
    # boundary from Florian's pivot constraints.
    skill_prompt_anonymized = ""
    if skill_slug:
        skill = skills_module.get_skill(skill_slug)
        if skill is None:
            return JSONResponse({"error": f"Unknown skill: {skill_slug}"}, status_code=400)
        if skill.system_prompt:
            try:
                sk_result = await asyncio.to_thread(_anonymize_sync, skill.system_prompt)
                skill_prompt_anonymized = sk_result.anonymized_text
                all_mappings.update(sk_result.mappings)
            except Exception as e:
                logger.error("Skill prompt anonymisation failed: %s — request blocked", e)
                return JSONResponse(
                    {"error": "Anonymisation failed. Message blocked to protect privacy."},
                    status_code=503,
                )

    # Knowledge-base attached chunks (Phase 3 / Anti-Magic-RAG). Chunks
    # are ALREADY anonymised at upload time — we re-fetch them by id from
    # the per-project store. We do NOT re-anonymise them; their stored
    # form is the canonical anonymised representation. The user has
    # explicitly confirmed which chunks to attach.
    chunk_context_block = ""
    if project_slug and attached_chunk_ids:
        if projects_module.get_project(project_slug) is None:
            return JSONResponse({"error": f"Unknown project: {project_slug}"}, status_code=400)
        chunks = projects_module.get_chunks_by_id(project_slug, attached_chunk_ids)
        if chunks:
            chunk_lines = []
            for c in chunks:
                chunk_lines.append(
                    f"[Source: {c['doc_filename']} #chunk{c['chunk_index']}]\n{c['anonymized_text']}"
                )
                # Merge per-chunk mappings into the global rehydrator dict.
                # Without this, codenames from KB chunks (e.g. "Apex Group"
                # for BSI, "Ilan" for the original author) would never be
                # translated back when the LLM echoes them in its answer.
                if c.get("mappings"):
                    all_mappings.update(c["mappings"])
            chunk_context_block = (
                "RELEVANT CONTEXT (already anonymised, attached by user):\n\n"
                + "\n\n---\n\n".join(chunk_lines)
            )

    # Compose the final system prompt. Order matters: skill first (sets
    # the assistant's role), then user-supplied system prompt, then KB
    # context, then BRACKET_HINT (privacy semantics) + LATEX_HINT.
    sys_parts = []
    if skill_prompt_anonymized:
        sys_parts.append(skill_prompt_anonymized)
    if system_prompt:
        sys_parts.append(system_prompt)
    if chunk_context_block:
        sys_parts.append(chunk_context_block)
    if all_mappings:
        sys_parts.append(BRACKET_HINT)
    sys_parts.append(LATEX_HINT)
    sys_prompt = "\n\n".join(p for p in sys_parts if p)

    # Privacy-safe Auto-Route: the router classifies on anonymized_message ONLY.
    # No raw user input ever reaches the classifier, whether local LLM,
    # embeddings or keyword rules. Provider is resolved here, deferred from
    # above (see the `if auto_route` branch in the provider-resolution block).
    routing_decision: dict | None = None
    if auto_route and _configured_snapshot is not None:
        local_p, local_m = auto_router.detect_local_llm_router(_configured_snapshot)
        # classify_intent is CPU-bound (sentence-transformers loads ~500MB on
        # first call, plus an httpx call to the local LLM if Stage 1 active).
        # Without asyncio.to_thread the event loop blocks for 10-30s on first
        # use, freezing every other in-flight request and making the browser
        # appear hung. Same pattern as engine.anonymize above.
        task, stage = await asyncio.to_thread(
            auto_router.classify_intent,
            anonymized_message,
            local_p,
            local_m,
        )
        provider, model = auto_router.pick_model(task, _configured_snapshot)
        prov = PROVIDERS.get(provider)
        if not prov:
            return JSONResponse({"error": "Auto-Router picked unknown provider"}, status_code=500)
        api_format = prov["format"]
        base_url = prov["base_url"]
        if provider == "ollama":
            base_url = getattr(config, "ollama_url", "http://localhost:11434")
        elif provider == "lmstudio":
            base_url = getattr(config, "lmstudio_url", "http://localhost:1234")
        api_key = _get_api_key(provider, config)
        if not api_key and provider not in ("ollama", "lmstudio"):
            return JSONResponse(
                {"error": f"No API key for auto-routed provider {provider}"},
                status_code=400,
            )
        routing_decision = {"task": task, "stage": stage, "provider": provider, "model": model}
        logger.info("Auto-Route: task=%s stage=%s -> %s/%s", task, stage, provider, model)

    # Build request body based on API format
    if api_format == "anthropic":
        messages = anonymized_history + [{"role": "user", "content": anonymized_message}]
        api_body = {
            "model": model,
            "messages": messages,
            "stream": True,
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
        # OpenAI-compatible format (OpenAI, Mistral, Ollama, LM Studio, Gemini)
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

    # Apply reasoning / temperature / top_p / max_tokens per model capabilities.
    # Silently drops unsupported params so we never send invalid requests.
    _apply_model_params(
        api_body,
        api_format,
        model,
        reasoning_effort=reasoning_effort,
        temperature=temperature_req,
        top_p=top_p_req,
        max_tokens=max_tokens_req,
    )

    # --- Debug log: record ONLY anonymized data, never originals ---
    #
    # Vor 3.1.10 wurde hier zusätzlich `api_body_messages` (die gesamten an
    # den LLM gesendeten Messages inkl. History) als 500-Zeichen-Slice
    # mitgeschrieben. Das ist PII-gefährlich: Die History enthält
    # rehydrierte Assistant-Texte, und wenn die Re-Anonymisierung einer
    # History-Message unvollständig ist (Edge-Case bei GLiNER), landet
    # Klartext-PII im Debug-Log. Darum schreiben wir nur noch den
    # aktuellen anonymisierten Turn + Codenames — der ist nachweislich
    # bereits anonymisiert (`entity_count` reflektiert exakt das, was
    # ersetzt wurde).
    _debug_log.append({
        "timestamp": time.time(),
        "anonymized_message": anonymized_message,
        "entity_count": entity_count,
        "codenames_used": list(mappings.keys()),
        "provider": provider,
        "model": model,
        "api_url": url,
        "history_message_count": len(api_body.get("messages", [])),
        "pii_detected": entity_count > 0,
        "pii_removed": anonymized_message != message,
        # Diagnose: was wird wirklich an den Provider geschickt? Hilft zu
        # verifizieren ob thinking-mode aktiv ist und ob das Auto-Routing
        # tatsächlich umgangen wurde (auto_route_received muss False sein).
        "auto_route_received": bool(body.get("auto_route", False)),
        "reasoning_effort_used": reasoning_effort,
        "thinking_payload": api_body.get("thinking") or api_body.get("output_config"),
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
            "routing": routing_decision,  # None unless auto-route was active
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
                        # Upstream-Error-Body kann API-Keys + sensitive Headers
                        # enthalten (manche Provider echoen Auth-Token in
                        # 403-JSON). Secrets aus dem String rausfiltern
                        # bevor er via SSE zum Client geht.
                        from .security_middleware import redact_secrets
                        safe_msg = redact_secrets(error_body.decode(errors="replace"))[:600]
                        logger.warning("Upstream %s/%s returned %d: %s", provider, model, resp.status_code, safe_msg)
                        # Structured error: status + provider + model + body.
                        # The client renders a persistent error-bubble with this.
                        # Dict is built externally so the f-string stays single-line
                        # (nested braces in f-strings require Python 3.12+).
                        err_payload = {
                            "error": safe_msg,
                            "status": resp.status_code,
                            "provider": provider,
                            "model": model,
                        }
                        yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"
                        return

                    # Keep-Alive Wrapper: Manche LLMs (v.a. Ollama mit großen
                    # Models oder OpenAI o3 mit reasoning) können 30-60s
                    # zwischen Tokens brauchen. Proxies/Firewalls brechen
                    # dann oft nach ~30s idle ab. Wir senden alle 15s ein
                    # SSE-Comment (`:keepalive\n\n`) — das ist für den
                    # Client sichtbar als "nichts passiert", aber für den
                    # Proxy ein Lebenszeichen.
                    line_iter = resp.aiter_lines()
                    while True:
                        try:
                            line = await asyncio.wait_for(line_iter.__anext__(), timeout=15.0)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            # Kein Token seit 15s — Keep-Alive senden und
                            # weiter warten. SSE-Comments beginnen mit ':'
                            # und werden von EventSource-Clients ignoriert.
                            yield ": keepalive\n\n"
                            continue
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        # Extract text delta. Thinking deltas (Anthropic
                        # Extended Thinking) are emitted on a SEPARATE SSE
                        # event so the frontend can render them in their
                        # own collapsible block instead of mixing them
                        # into the visible answer.
                        delta_text = None
                        if api_format == "anthropic":
                            if data.get("type") == "error":
                                error_info = data.get("error", {})
                                error_msg = error_info.get("message", "Unknown API error")
                                yield f"event: error\ndata: {json.dumps({'error': f'Anthropic: {error_msg}'})}\n\n"
                                return
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                dtype = delta.get("type")
                                if dtype == "text_delta":
                                    delta_text = delta.get("text", "")
                                elif dtype == "thinking_delta":
                                    thinking_chunk = delta.get("thinking", "")
                                    if thinking_chunk:
                                        yield f"event: thinking\ndata: {json.dumps({'content': thinking_chunk})}\n\n"
                                    continue
                                elif dtype == "signature_delta":
                                    # Cryptographic signature for the
                                    # thinking block (Anthropic verifies
                                    # tampering). Not user-visible.
                                    continue
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

        except asyncio.CancelledError:
            # Client hat die Verbindung geschlossen (Tab zu, `Stop`-Button,
            # Navigation). httpx.AsyncClient schließt im `async with`-Exit
            # automatisch die Upstream-Verbindung — das LLM stoppt also
            # Token-Generation und der User zahlt keine unnötigen Tokens.
            # Wir re-raisen, damit Starlette den Stream sauber beendet.
            logger.info("SSE-Stream abgebrochen (Client-Disconnect)")
            raise
        except httpx.ConnectError as e:
            from .security_middleware import redact_secrets
            yield f"event: error\ndata: {json.dumps({'error': 'Connection failed', 'detail': redact_secrets(str(e))[:200]})}\n\n"
        except Exception as e:
            from .security_middleware import safe_error_message
            logger.error("SSE-Stream unexpected exception: %s", e, exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': safe_error_message(e, fallback='Stream failed')})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # X-Accel-Buffering=no deaktiviert nginx/proxy response buffering
            # — wichtig für echten Token-by-Token-Stream, sonst puffert der
            # Proxy bis zum Ende und der User sieht nichts tropfenweise.
            "X-Accel-Buffering": "no",
        },
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
        # Advanced mode (opt-in; basic UI never shows these)
        "advanced_mode": getattr(config, "advanced_mode", False),
        "auto_route": getattr(config, "auto_route", False),
        "slash_commands": getattr(config, "slash_commands", False),
        "slash_aliases": getattr(config, "slash_aliases", {}),
        "reasoning_effort": getattr(config, "reasoning_effort", "medium"),
        "temperature": getattr(config, "temperature", 1.0),
        "top_p": getattr(config, "top_p", 1.0),
        "max_tokens": getattr(config, "max_tokens", 4096),
        "onboarding_done": (CONFIG_DIR / "proxy.yaml").exists(),
    })


async def update_settings(request: Request) -> JSONResponse:
    global _config
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    config = _get_config()

    # Update API keys, but ONLY if the value is a real key (not the masked
    # placeholder the frontend echoes back). _is_masked_key handles all
    # masking conventions and empty strings — preventing the latent
    # "save wiped my key" bug where any non-key Settings save would
    # overwrite real keys with the display-only placeholder.
    # Changed keys also invalidate the model-discovery cache so the next
    # /providers call re-queries the upstream with the fresh key.
    for _provider in ("anthropic", "openai", "mistral", "google"):
        _field = f"{_provider}_api_key"
        if _field in body and not _is_masked_key(body[_field]):
            new_key = body[_field]
            if getattr(config, _field) != new_key:
                _invalidate_discovery_cache(_provider)
            setattr(config, _field, new_key)
    # deny_list / allow_list validation: strict list[str], Länge begrenzt.
    # Ein Angreifer könnte (vor dem CSRF-Fix) oder ein kompromittierter
    # Browser-Tab mit gültigem Origin beliebig viele / beliebig lange
    # Einträge einschleusen — das würde jede spätere Anonymisierung
    # ausbremsen (linear mehr Regex-Matches). Wir cappen bei 500 × 200 chars.
    def _sanitize_term_list(raw, field_name):
        if not isinstance(raw, list):
            raise ValueError(f"{field_name} must be a list")
        cleaned = []
        for item in raw:
            if not isinstance(item, str):
                continue
            trimmed = item.strip()
            if 1 <= len(trimmed) <= 200:
                cleaned.append(trimmed)
            if len(cleaned) >= 500:
                break
        return cleaned

    if "deny_list" in body:
        try:
            config.deny_list = _sanitize_term_list(body["deny_list"], "deny_list")
        except ValueError as ve:
            return JSONResponse({"error": str(ve)}, status_code=400)
    if "allow_list" in body:
        try:
            config.allow_list = _sanitize_term_list(body["allow_list"], "allow_list")
        except ValueError as ve:
            return JSONResponse({"error": str(ve)}, status_code=400)
    if "confidence_threshold" in body:
        try:
            thresh = float(body["confidence_threshold"])
        except (TypeError, ValueError):
            return JSONResponse({"error": "confidence_threshold must be a number"}, status_code=400)
        if not (0.0 <= thresh <= 1.0):
            return JSONResponse({"error": "confidence_threshold must be between 0.0 and 1.0"}, status_code=400)
        config.confidence_threshold = thresh
    if "default_provider" in body:
        prov = body["default_provider"]
        if isinstance(prov, str) and prov in PROVIDERS:
            config.default_provider = prov
    if "default_model" in body:
        model = body["default_model"]
        if isinstance(model, str) and len(model) <= 200:
            config.default_model = model
    if "ollama_url" in body:
        url_val = body["ollama_url"]
        if isinstance(url_val, str) and len(url_val) <= 500:
            config.ollama_url = _normalize_local_url(url_val)
    if "lmstudio_url" in body:
        url_val = body["lmstudio_url"]
        if isinstance(url_val, str) and len(url_val) <= 500:
            config.lmstudio_url = _normalize_local_url(url_val)

    # Advanced-mode params (opt-in, validated defensively).
    if "advanced_mode" in body:
        config.advanced_mode = bool(body["advanced_mode"])
    if "auto_route" in body:
        config.auto_route = bool(body["auto_route"])
    if "slash_commands" in body:
        config.slash_commands = bool(body["slash_commands"])
    if "slash_aliases" in body and isinstance(body["slash_aliases"], dict):
        cleaned = {}
        for k, v in body["slash_aliases"].items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            slug = k.strip().lower()
            if not slug or len(slug) > 32:
                continue
            if not slug.replace("-", "").replace("_", "").isalnum():
                continue
            prov = str(v.get("provider", "")).strip()
            model = str(v.get("model", "")).strip()
            if prov in PROVIDERS and 1 <= len(model) <= 200:
                cleaned[slug] = {"provider": prov, "model": model}
            if len(cleaned) >= 50:
                break
        config.slash_aliases = cleaned
    if "reasoning_effort" in body:
        val = body["reasoning_effort"]
        if isinstance(val, str) and val in ("off", "minimal", "low", "medium", "high"):
            config.reasoning_effort = val
    if "temperature" in body:
        try:
            t = float(body["temperature"])
            if 0.0 <= t <= 2.0:
                config.temperature = t
        except (TypeError, ValueError):
            pass
    if "top_p" in body:
        try:
            p = float(body["top_p"])
            if 0.0 <= p <= 1.0:
                config.top_p = p
        except (TypeError, ValueError):
            pass
    if "max_tokens" in body:
        try:
            mt = int(body["max_tokens"])
            if 1 <= mt <= 200_000:
                config.max_tokens = mt
        except (TypeError, ValueError):
            pass

    config.save()
    _config = config

    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# GET /chat/api/providers — Available providers + models
# ---------------------------------------------------------------------------

async def get_providers(request: Request) -> JSONResponse:
    config = _get_config()
    result = {}

    # Single httpx client shared across all discovery calls in this request.
    # Significantly cheaper than spinning one up per provider.
    async with httpx.AsyncClient(timeout=5.0) as client:
        for pid, prov in PROVIDERS.items():
            api_key = _get_api_key(pid, config)
            configured = bool(api_key) or pid in ("ollama", "lmstudio")
            models = list(prov["models"])

            # Cloud providers: query /v1/models with the configured key.
            # Falls back to hardcoded PROVIDERS list on any error.
            if configured and pid in ("anthropic", "openai", "mistral", "google"):
                discovered = await _discover_models(pid, api_key, client)
                if discovered:
                    models = discovered

            # Ollama: discover models dynamically via /api/tags
            elif pid == "ollama":
                ollama_url = getattr(config, "ollama_url", "http://localhost:11434")
                try:
                    resp = await client.get(f"{ollama_url}/api/tags", timeout=3.0)
                    if resp.status_code == 200:
                        ollama_models = resp.json().get("models", [])
                        models = [{"id": m["name"], "name": m["name"]} for m in ollama_models]
                        configured = True
                except Exception:
                    configured = False

            # LM Studio: discover models dynamically via /v1/models (OpenAI-standard)
            elif pid == "lmstudio":
                lmstudio_url = getattr(config, "lmstudio_url", "http://localhost:1234")
                try:
                    resp = await client.get(f"{lmstudio_url}/v1/models", timeout=3.0)
                    if resp.status_code == 200:
                        lms_models = resp.json().get("data", [])
                        models = [{"id": m["id"], "name": m.get("id", m.get("object", "unknown"))} for m in lms_models]
                        configured = True
                except Exception:
                    configured = False

            # Annotate each model with its capabilities so the Advanced panel
            # can render reasoning/temperature controls conditionally. Runs
            # per-provider so each provider's models get their own annotations.
            annotated_models = []
            for m in models:
                caps = _caps_for(m["id"])
                annotated_models.append({
                    **m,
                    "reasoning_type": caps.get("reasoning_type"),
                    "supports_temperature": caps.get("temperature", True),
                    "tier": caps.get("tier", "local"),
                })

            result[pid] = {
                "name": prov["name"],
                "configured": configured,
                "models": annotated_models,
            }

    # Meta: tell frontend which router stages are available (so Advanced
    # Settings can show the correct active stage).
    try:
        import importlib.util
        embeddings_available = importlib.util.find_spec("sentence_transformers") is not None
    except Exception:
        embeddings_available = False

    # Local LLM router is available if an Ollama or LMStudio provider is
    # configured (detected above as part of the normal discovery loop).
    local_llm_available = any(
        result.get(pid, {}).get("configured") for pid in ("ollama", "lmstudio")
    )

    result["_meta"] = {
        "router_stages": {
            "local_llm": local_llm_available,
            "embeddings": embeddings_available,
            "rules": True,  # always available
        },
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

    if not provider:
        return JSONResponse({"valid": False, "error": "Missing provider"})

    prov = PROVIDERS.get(provider)
    if not prov:
        return JSONResponse({"valid": False, "error": f"Unknown provider: {provider}"})

    # Local runners (Ollama, LMStudio) authenticate via reachable URL, NOT
    # via API key. Cloud providers require a key. Splitting the check here
    # so the "missing key" early-return does not block local-runner validation.
    if provider not in ("ollama", "lmstudio") and not api_key:
        return JSONResponse({"valid": False, "error": "API-Key fehlt — bitte oben eintragen."})

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "anthropic":
                resp = await client.post(
                    f"{prov['base_url']}/v1/messages",
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                )
            elif provider == "ollama":
                ollama_url = _normalize_local_url(body.get("ollama_url", "http://localhost:11434"))
                resp = await client.get(f"{ollama_url}/api/tags")
            elif provider == "lmstudio":
                lmstudio_url = _normalize_local_url(body.get("lmstudio_url", "http://localhost:1234"))
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
                return JSONResponse({"valid": False, "error": "API-Key ist ungültig oder abgelaufen."})
            elif resp.status_code == 404:
                if provider == "ollama":
                    return JSONResponse({"valid": False, "error": "URL stimmt nicht mit Ollama überein. Nur die Basis-URL eingeben (z.B. http://localhost:11434), ohne /api oder /v1."})
                if provider == "lmstudio":
                    return JSONResponse({"valid": False, "error": "URL stimmt nicht mit LM Studio überein. Nur die Basis-URL eingeben (z.B. http://localhost:1234), ohne /v1."})
                return JSONResponse({"valid": False, "error": f"Endpoint nicht gefunden (HTTP 404)."})
            else:
                return JSONResponse({"valid": False, "error": f"Provider antwortete mit HTTP {resp.status_code}"})
    except httpx.ConnectError:
        if provider == "ollama":
            return JSONResponse({"valid": False, "error": "Ollama läuft nicht. Im Terminal starten: `ollama serve`. Dann nochmal prüfen."})
        if provider == "lmstudio":
            return JSONResponse({"valid": False, "error": "LM Studio läuft nicht. App öffnen → Local Server starten → dann nochmal prüfen."})
        return JSONResponse({"valid": False, "error": "Verbindung fehlgeschlagen — Server nicht erreichbar."})
    except Exception as e:
        from .security_middleware import safe_error_message
        logger.warning("Key-Validation exception for %s: %s", provider, e)
        return JSONResponse({"valid": False, "error": safe_error_message(e, max_len=200, fallback="Validation failed")})


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

    # Filename sanitation + Suffix-Whitelist VOR dem Read. Damit kann ein
    # Angreifer nicht einmal einen 1 GB-Upload starten — schon die
    # Content-Length prüfen wir, bevor wir überhaupt Bytes lesen.
    safe_name = _safe_filename(file.filename)
    suffix = Path(safe_name).suffix.lower()

    # Wenn der Suffix in keiner der drei Gruppen ist, sofort raus.
    if suffix not in _AUDIO_EXTS and suffix not in _IMAGE_EXTS and suffix not in _DOC_EXTS:
        return JSONResponse({"error": f"Unsupported file type: {suffix}"}, status_code=400)

    # Content-Length early reject — bevor wir file.read() aufrufen.
    content_length = request.headers.get("content-length")
    max_bytes = _MAX_AUDIO_UPLOAD_BYTES if suffix in _AUDIO_EXTS else _MAX_UPLOAD_BYTES
    if content_length:
        try:
            if int(content_length) > max_bytes:
                return JSONResponse(
                    {"error": f"File too large (max {max_bytes // (1024*1024)}MB)"},
                    status_code=413,
                )
        except ValueError:
            pass

    # Save to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        if len(content) > max_bytes:
            # Double-check after read (Content-Length kann manipuliert sein)
            try: tmp.close(); os.unlink(tmp.name)
            except Exception: pass
            return JSONResponse(
                {"error": f"File too large (max {max_bytes // (1024*1024)}MB)"},
                status_code=413,
            )
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = _get_config()
        engine = _get_engine()

        # Use module-level frozensets (s.o.) statt lokaler Re-Definition.
        audio_exts = _AUDIO_EXTS
        image_exts = _IMAGE_EXTS
        doc_exts = _DOC_EXTS

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
                    "filename": safe_name,
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
                    "filename": safe_name,
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
                    "filename": safe_name,
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

    # Filename-Sanitization + Suffix-Whitelist VOR dem Read (analog zu
    # upload_file), damit Path-Traversal und Typ-Mismatch gar nicht erst
    # in den File-System-Write kommen.
    safe_name = _safe_filename(file.filename)
    suffix = Path(safe_name).suffix.lower()

    if suffix not in _REDACT_EXTS:
        return JSONResponse(
            {"error": f"Redaction not supported for {suffix}. Use images or PDFs."},
            status_code=400,
        )

    # Content-Length Early-Reject — blockiert 1 GB-DoS ohne einen Byte zu lesen.
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_UPLOAD_BYTES:
                return JSONResponse(
                    {"error": f"File too large (max {_MAX_UPLOAD_BYTES // (1024*1024)}MB)"},
                    status_code=413,
                )
        except ValueError:
            pass

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            try: tmp.close(); os.unlink(tmp.name)
            except Exception: pass
            return JSONResponse(
                {"error": f"File too large (max {_MAX_UPLOAD_BYTES // (1024*1024)}MB)"},
                status_code=413,
            )
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

        # Output filename: strip Original-Suffix vom sanitisierten Namen und
        # hänge "_redacted<ext>" an. Vorher benutzter str.replace() bug fixed
        # (bei "a.jpg.jpg" würde nur das erste ".jpg" ersetzt).
        stem = Path(safe_name).stem
        out_name = f"{stem}_redacted{out_suffix}"

        # Server-kontrollierte MIME-Type Allowlist (nicht aus Suffix erraten).
        mime_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tiff": "image/tiff",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
        }
        mime_type = mime_type_map.get(out_suffix, "application/octet-stream")

        return JSONResponse({
            "filename": out_name,
            "redacted_base64": redacted_b64,
            "mime_type": mime_type,
            "entities_redacted": result["entities_redacted"],
        })

    except ImportError:
        return JSONResponse({"error": "Image redaction not installed. Run: pip install austrai (Neuinstallation nötig)"}, status_code=400)
    except Exception as e:
        from .security_middleware import safe_error_message
        logger.error("Redaction failed: %s", e, exc_info=True)
        return JSONResponse({"error": safe_error_message(e, max_len=300, fallback="Redaction failed")}, status_code=500)
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


# ---------------------------------------------------------------------------
# Skills API — user-defined "profis" (system-prompt + recommended model)
# ---------------------------------------------------------------------------


async def list_skills_endpoint(request: Request) -> JSONResponse:
    skills = skills_module.list_skills()
    return JSONResponse({"skills": [s.to_public_dict() for s in skills]})


async def save_skill_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    slug = (body.get("slug") or "").strip().lower()
    if not skills_module.is_valid_slug(slug):
        return JSONResponse({"error": "Invalid slug. Use lowercase letters, digits, '-' or '_' (max 64)."}, status_code=400)
    name = str(body.get("name", slug))[:200].strip()
    description = str(body.get("description", ""))[:500].strip()
    rec_provider = str(body.get("recommended_provider", "")).strip()
    rec_model = str(body.get("recommended_model", "")).strip()[:200]
    if rec_provider and rec_provider not in PROVIDERS:
        return JSONResponse({"error": f"Unknown provider: {rec_provider}"}, status_code=400)
    rec_temp = body.get("recommended_temperature")
    if rec_temp is not None:
        try:
            rec_temp = float(rec_temp)
            if not (0.0 <= rec_temp <= 2.0):
                rec_temp = None
        except (TypeError, ValueError):
            rec_temp = None
    system_prompt = str(body.get("system_prompt", ""))[:50_000].strip()
    skill = skills_module.Skill(
        slug=slug,
        name=name,
        description=description,
        recommended_provider=rec_provider,
        recommended_model=rec_model,
        recommended_temperature=rec_temp,
        system_prompt=system_prompt,
    )
    try:
        skills_module.save_skill(skill)
    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=400)
    return JSONResponse({"status": "ok", "skill": skill.to_public_dict()})


async def delete_skill_endpoint(request: Request) -> JSONResponse:
    slug = request.path_params.get("slug", "")
    ok = skills_module.delete_skill(slug)
    if not ok:
        return JSONResponse({"error": "Skill not found"}, status_code=404)
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Projects (Wissensbasis) API
# ---------------------------------------------------------------------------


async def list_projects_endpoint(request: Request) -> JSONResponse:
    projects = projects_module.list_projects()
    return JSONResponse({"projects": [p.to_public_dict() for p in projects]})


async def create_project_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    slug = (body.get("slug") or "").strip().lower()
    if not projects_module.is_valid_slug(slug):
        return JSONResponse({"error": "Invalid slug. Use lowercase letters, digits, '-' or '_' (max 64)."}, status_code=400)
    name = str(body.get("name", slug))[:200].strip()
    description = str(body.get("description", ""))[:500].strip()
    try:
        proj = projects_module.create_project(slug, name, description)
    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=400)
    return JSONResponse({"status": "ok", "project": proj.to_public_dict()})


async def update_project_endpoint(request: Request) -> JSONResponse:
    slug = request.path_params.get("slug", "")
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    name = body.get("name")
    description = body.get("description")
    if name is not None:
        name = str(name)[:200].strip()
    if description is not None:
        description = str(description)[:500].strip()
    proj = projects_module.update_project(slug, name=name, description=description)
    if proj is None:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    return JSONResponse({"status": "ok", "project": proj.to_public_dict()})


async def delete_project_endpoint(request: Request) -> JSONResponse:
    slug = request.path_params.get("slug", "")
    ok = projects_module.delete_project(slug)
    if not ok:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    return JSONResponse({"status": "ok"})


async def list_project_docs_endpoint(request: Request) -> JSONResponse:
    slug = request.path_params.get("slug", "")
    if not projects_module.is_valid_slug(slug):
        return JSONResponse({"error": "Invalid slug"}, status_code=400)
    docs = projects_module.list_documents(slug)
    return JSONResponse({"documents": docs})


async def reindex_project_doc_endpoint(request: Request) -> JSONResponse:
    """Re-anonymise + re-index an already-uploaded document with extended
    deny-list terms. Use case: the upload-time detector missed something
    (e.g. a rare address form), the user spots it in the inspector,
    types the missed term into the inline deny-list and triggers
    re-indexing. Old chunks for that filename are dropped first."""
    slug = request.path_params.get("slug", "")
    if not projects_module.is_valid_slug(slug):
        return JSONResponse({"error": "Invalid slug"}, status_code=400)
    if projects_module.get_project(slug) is None:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    filename = (body.get("filename") or "").strip()
    extra_terms_raw = body.get("extra_deny_terms") or []
    persist_globally = bool(body.get("persist_globally", True))
    if not filename:
        return JSONResponse({"error": "filename required"}, status_code=400)

    extra_terms = []
    if isinstance(extra_terms_raw, list):
        for t in extra_terms_raw[:200]:
            if isinstance(t, str):
                trimmed = t.strip()
                if 1 <= len(trimmed) <= 200:
                    extra_terms.append(trimmed)

    src_path = projects_module.get_document_path(slug, filename)
    if src_path is None:
        return JSONResponse({"error": "Original document not on disk anymore"}, status_code=404)

    # Persist new terms into the global deny_list (so the same terms also
    # protect future uploads + chat messages). User opted in via the
    # `persist_globally` flag, default true.
    config = _get_config()
    if persist_globally and extra_terms:
        merged = list(dict.fromkeys((config.deny_list or []) + extra_terms))
        config.deny_list = merged[:500]
        config.save()

    # Combine the (now possibly-updated) global deny_list with this
    # request's extra terms for the actual anonymisation pass — guarantees
    # the new terms hit even if persist_globally was false.
    deny_for_pass = list(dict.fromkeys((config.deny_list or []) + extra_terms))

    try:
        from .core.extractor import extract_from_file
        extraction = extract_from_file(str(src_path))
        plain_text = extraction.text or ""
    except Exception as e:
        return JSONResponse({"error": f"Re-extract failed: {e}"}, status_code=400)
    if not plain_text.strip():
        return JSONResponse({"error": "Document text is empty"}, status_code=400)

    engine = _get_engine()

    def _anonymize(t: str):
        return engine.anonymize(t, deny_list=deny_for_pass or None,
                                allow_list=config.allow_list or None)

    try:
        result = await asyncio.to_thread(_anonymize, plain_text)
    except Exception as e:
        logger.error("Re-index anonymisation failed: %s", e)
        return JSONResponse({"error": "Anonymisation failed"}, status_code=503)

    # Drop existing chunks for this doc, then add the freshly anonymised ones.
    projects_module.remove_document(slug, filename)
    try:
        chunks_added = await asyncio.to_thread(
            projects_module.add_document,
            slug, filename, result.anonymized_text, result.mappings,
        )
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)

    return JSONResponse({
        "status": "ok",
        "filename": filename,
        "chunks_added": chunks_added,
        "entities_anonymized": len(result.mappings),
        "deny_list_size": len(deny_for_pass),
    })


async def inspect_project_chunks_endpoint(request: Request) -> JSONResponse:
    """Verification endpoint — returns the anonymised chunks for a doc so
    the user can see what is actually stored. Useful when the LLM echoes
    something that was supposed to be anonymised (then we know whether
    the detection missed it at upload-time or something downstream
    de-anonymised it)."""
    slug = request.path_params.get("slug", "")
    filename = request.query_params.get("filename", "")
    if not projects_module.is_valid_slug(slug) or not filename:
        return JSONResponse({"error": "Invalid slug or filename"}, status_code=400)
    chunks = projects_module.list_chunks_for_doc(slug, filename)
    return JSONResponse({"chunks": chunks})


async def upload_project_doc_endpoint(request: Request) -> JSONResponse:
    """Upload a document, anonymise it, chunk + embed, store anonymised
    chunks. Plain-text content NEVER leaves this handler — chromadb /
    sqlite hold only anonymised text."""
    slug = request.path_params.get("slug", "")
    if not projects_module.is_valid_slug(slug):
        return JSONResponse({"error": "Invalid slug"}, status_code=400)
    if projects_module.get_project(slug) is None:
        return JSONResponse({"error": "Project not found"}, status_code=404)

    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename"):
        return JSONResponse({"error": "No file uploaded"}, status_code=400)
    raw_bytes = await upload.read()
    if len(raw_bytes) > 20_000_000:
        return JSONResponse({"error": "File too large (max 20MB)"}, status_code=413)

    # Persist the original (so user can re-upload / inspect later)
    saved_path = projects_module.save_document_file(slug, upload.filename, raw_bytes)

    # Extract plain text. Reuse the existing extractor used for chat
    # attachments; it handles PDF/Docx/Txt and never leaks bytes upstream.
    try:
        from .core.extractor import extract_from_file
        extraction = extract_from_file(str(saved_path))
        plain_text = extraction.text or ""
    except Exception as e:
        logger.warning("Text extraction failed for %s/%s: %s", slug, upload.filename, e)
        return JSONResponse({"error": f"Could not extract text: {e}"}, status_code=400)

    if not plain_text or not plain_text.strip():
        return JSONResponse({"error": "Document contains no extractable text"}, status_code=400)

    # Anonymise the WHOLE document before any indexing happens. This is the
    # privacy boundary for the knowledge base: the index never sees plain
    # text, only codenames + bracket placeholders.
    config = _get_config()
    engine = _get_engine()

    def _anonymize_doc(t: str):
        return engine.anonymize(t, deny_list=config.deny_list or None,
                                allow_list=config.allow_list or None)

    try:
        result = await asyncio.to_thread(_anonymize_doc, plain_text)
    except Exception as e:
        logger.error("Knowledge-base anonymisation failed for %s/%s: %s", slug, upload.filename, e)
        return JSONResponse(
            {"error": "Anonymisation failed. Document not indexed."},
            status_code=503,
        )

    try:
        chunks_added = await asyncio.to_thread(
            projects_module.add_document,
            slug, upload.filename, result.anonymized_text, result.mappings,
        )
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)

    return JSONResponse({
        "status": "ok",
        "filename": upload.filename,
        "chunks_added": chunks_added,
        "entities_anonymized": len(result.mappings),
    })


async def delete_project_doc_endpoint(request: Request) -> JSONResponse:
    slug = request.path_params.get("slug", "")
    filename = request.query_params.get("filename", "")
    if not projects_module.is_valid_slug(slug) or not filename:
        return JSONResponse({"error": "Invalid slug or filename"}, status_code=400)
    removed = projects_module.remove_document(slug, filename)
    # Also drop the original file
    docs_dir = projects_module._docs_dir(slug)
    safe = re.sub(r"[^\w.\-]", "_", filename)[:200]
    fp = docs_dir / safe
    if fp.exists():
        try:
            fp.unlink()
        except OSError:
            pass
    return JSONResponse({"status": "ok", "chunks_removed": removed})


async def search_project_endpoint(request: Request) -> JSONResponse:
    """Anti-Magic-RAG retrieval: returns candidate chunks for a query.
    The frontend shows them under the input field; the user picks which
    ones to attach. Only confirmed chunks reach the LLM."""
    slug = request.path_params.get("slug", "")
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    query = (body.get("query") or "").strip()
    top_k = int(body.get("top_k", 5))
    top_k = max(1, min(top_k, 20))
    if not projects_module.is_valid_slug(slug):
        return JSONResponse({"error": "Invalid slug"}, status_code=400)
    if not query:
        return JSONResponse({"results": []})

    # The query gets anonymised before retrieval so that semantic matching
    # happens against the anonymised index in the same coordinate system.
    config = _get_config()
    engine = _get_engine()

    def _anonymize_q(t: str):
        return engine.anonymize(t, deny_list=config.deny_list or None,
                                allow_list=config.allow_list or None)

    try:
        result = await asyncio.to_thread(_anonymize_q, query)
        anon_query = result.anonymized_text
    except Exception as e:
        logger.error("Query anonymisation failed: %s", e)
        return JSONResponse({"error": "Query anonymisation failed"}, status_code=503)

    try:
        results = await asyncio.to_thread(projects_module.search, slug, anon_query, top_k)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    return JSONResponse({"results": results})


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
        # Skills (Phase 2 of the 04/2026 pivot — see project_austrai_pivot_skills_kb_plan.md)
        Route("/api/skills", list_skills_endpoint, methods=["GET"]),
        Route("/api/skills", save_skill_endpoint, methods=["PUT"]),
        Route("/api/skills/{slug}", delete_skill_endpoint, methods=["DELETE"]),
        # Knowledge base (Phase 3)
        Route("/api/projects", list_projects_endpoint, methods=["GET"]),
        Route("/api/projects", create_project_endpoint, methods=["POST"]),
        Route("/api/projects/{slug}", update_project_endpoint, methods=["PUT"]),
        Route("/api/projects/{slug}", delete_project_endpoint, methods=["DELETE"]),
        Route("/api/projects/{slug}/docs", list_project_docs_endpoint, methods=["GET"]),
        Route("/api/projects/{slug}/upload", upload_project_doc_endpoint, methods=["POST"]),
        Route("/api/projects/{slug}/doc", delete_project_doc_endpoint, methods=["DELETE"]),
        Route("/api/projects/{slug}/search", search_project_endpoint, methods=["POST"]),
        Route("/api/projects/{slug}/chunks", inspect_project_chunks_endpoint, methods=["GET"]),
        Route("/api/projects/{slug}/reindex", reindex_project_doc_endpoint, methods=["POST"]),
        Mount("/css", NoCacheStaticFiles(directory=str(CHAT_DIR / "css")), name="chat-css"),
        Mount("/js", NoCacheStaticFiles(directory=str(CHAT_DIR / "js")), name="chat-js"),
    ]
    return Starlette(routes=routes, on_startup=[_warmup_engine])

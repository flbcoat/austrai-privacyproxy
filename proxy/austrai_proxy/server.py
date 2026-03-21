"""AUSTR.AI Proxy Server — transparent privacy layer between apps and LLM APIs.

Intercepts LLM API calls, anonymizes user messages, forwards to the real API,
and rehydrates the streaming response. The calling app doesn't know it's
talking to a proxy.

Supports:
  POST /v1/messages          — Anthropic Messages API
  POST /v1/chat/completions  — OpenAI Chat Completions API
  GET  /health               — Health check
"""

import json
import logging

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse, Response
from starlette.routing import Route

from .config import ProxyConfig
from .stream_rehydrator import StreamRehydrator

logger = logging.getLogger("austrai.proxy")

# File logging for proxy activity
_LOG_FILE = None

def _init_file_logging():
    global _LOG_FILE
    from .config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = CONFIG_DIR / "proxy.log"
    _LOG_FILE = log_path
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# Upstream API URLs
ANTHROPIC_API = "https://api.anthropic.com"
OPENAI_API = "https://api.openai.com"

# System prompt fragment injected to preserve bracket references
BRACKET_HINT = (
    "The text contains reference codes in square brackets "
    "(e.g. [AT_IBAN_1], [PHONE_NUMBER_1]). "
    "Reproduce these EXACTLY as they appear."
)

# Global config, set by create_app()
_config: ProxyConfig | None = None


# ---------------------------------------------------------------------------
# Local anonymization engine
# ---------------------------------------------------------------------------

async def _anonymize(text: str, deny_list: list[str] | None = None) -> tuple[str, dict[str, str]]:
    """Anonymize text locally using the PrivacyEngine. No external API calls."""
    import asyncio
    from .core import get_engine

    engine = get_engine()
    # Run blocking Presidio call in thread pool
    result = await asyncio.to_thread(engine.anonymize, text, deny_list)
    return result.anonymized_text, result.mappings


# ---------------------------------------------------------------------------
# Format handlers: extract/inject user text from request bodies
# ---------------------------------------------------------------------------

def _extract_and_anonymize_messages(body: dict, mappings_out: dict, deny_list: list[str] | None):
    """Return list of (message_index, original_text) pairs for user messages."""
    texts = []
    for i, msg in enumerate(body.get("messages", [])):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                texts.append((i, content))
            elif isinstance(content, list):
                # Anthropic content blocks
                for j, block in enumerate(content):
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append((i, block.get("text", ""), j))
    return texts


async def _anonymize_request_body(body: dict, api_format: str, deny_list: list[str] | None) -> dict[str, str]:
    """Anonymize all user messages in-place. Returns merged mappings."""
    merged_mappings: dict[str, str] = {}
    messages = body.get("messages", [])

    for i, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue

        content = msg.get("content", "")

        if isinstance(content, str) and content.strip():
            anon_text, mappings = await _anonymize(content, deny_list)
            msg["content"] = anon_text
            merged_mappings.update(mappings)

        elif isinstance(content, list):
            # Anthropic: array of content blocks
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                    anon_text, mappings = await _anonymize(block["text"], deny_list)
                    block["text"] = anon_text
                    merged_mappings.update(mappings)

    # Inject bracket-preservation hint into system message
    if merged_mappings and any("[" in k for k in merged_mappings):
        _inject_system_hint(body, api_format)

    return merged_mappings


def _inject_system_hint(body: dict, api_format: str):
    """Add bracket-preservation hint to system message."""
    messages = body.get("messages", [])

    if api_format == "anthropic":
        # Anthropic: system is a top-level field, not in messages
        existing = body.get("system", "")
        if isinstance(existing, str):
            body["system"] = (existing + "\n\n" + BRACKET_HINT).strip()
        elif isinstance(existing, list):
            body["system"].append({"type": "text", "text": BRACKET_HINT})
    else:
        # OpenAI: system is a message with role=system
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = msg.get("content", "") + "\n\n" + BRACKET_HINT
                return
        messages.insert(0, {"role": "system", "content": BRACKET_HINT})


# ---------------------------------------------------------------------------
# SSE stream parsing and rehydration
# ---------------------------------------------------------------------------

def _extract_delta_text(data: dict, api_format: str) -> str | None:
    """Extract the text delta from a parsed SSE data object."""
    if api_format == "anthropic":
        if data.get("type") == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text", "")
    else:
        choices = data.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            return delta.get("content")
    return None


def _set_delta_text(data: dict, new_text: str, api_format: str) -> dict:
    """Set the text delta in a parsed SSE data object."""
    if api_format == "anthropic":
        data["delta"]["text"] = new_text
    else:
        data["choices"][0]["delta"]["content"] = new_text
    return data


async def _stream_proxy(upstream_response: httpx.Response, mappings: dict[str, str], api_format: str):
    """Stream SSE from upstream, rehydrating codenames on the fly."""
    rehydrator = StreamRehydrator(mappings)

    async for line in upstream_response.aiter_lines():
        if not line.startswith("data: "):
            # Pass through event types, empty lines, comments
            yield line + "\n"
            continue

        raw_data = line[6:]  # strip "data: "

        # End-of-stream signals
        if raw_data.strip() == "[DONE]":
            # Flush remaining buffer
            remaining = rehydrator.flush()
            if remaining:
                # Emit one final delta with the flushed content
                if api_format == "openai":
                    final = {"choices": [{"delta": {"content": remaining}, "index": 0}]}
                    yield f"data: {json.dumps(final, ensure_ascii=False)}\n"
                else:
                    final = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": remaining}}
                    yield f"data: {json.dumps(final, ensure_ascii=False)}\n"
            yield line + "\n"
            continue

        # Parse the SSE data
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            yield line + "\n"
            continue

        # Extract text delta
        delta_text = _extract_delta_text(data, api_format)
        if delta_text is None:
            # Non-text event (e.g., content_block_start, usage) — pass through
            yield line + "\n"
            continue

        # Rehydrate through sliding window
        rehydrated = rehydrator.feed(delta_text)

        if rehydrated:
            _set_delta_text(data, rehydrated, api_format)
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n"
        # If rehydrated is empty, the text is buffered — don't emit yet

    # Stream ended without [DONE] — flush remaining
    remaining = rehydrator.flush()
    if remaining:
        if api_format == "openai":
            final = {"choices": [{"delta": {"content": remaining}, "index": 0}]}
        else:
            final = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": remaining}}
        yield f"data: {json.dumps(final, ensure_ascii=False)}\n"


# ---------------------------------------------------------------------------
# Header handling: pass through auth from the calling app
# ---------------------------------------------------------------------------

# Headers to forward from the incoming request to the upstream API
_PASSTHROUGH_HEADERS = {
    "x-api-key", "authorization", "anthropic-version", "anthropic-beta",
    "openai-organization", "openai-project",
}

def _build_upstream_headers(request: Request, api_format: str) -> dict[str, str]:
    """Build headers for the upstream request.

    Strategy: pass through ALL auth headers from the calling app.
    Only use configured API key as fallback if no auth is present.
    This allows Claude Max (session auth) and API key users to work.
    """
    headers: dict[str, str] = {"content-type": "application/json"}

    # Pass through relevant headers from the incoming request
    has_auth = False
    for key in request.headers:
        if key.lower() in _PASSTHROUGH_HEADERS:
            headers[key] = request.headers[key]
            if key.lower() in ("x-api-key", "authorization"):
                has_auth = True

    # Fallback: use configured API key if no auth was passed through
    if not has_auth:
        if api_format == "anthropic" and _config.anthropic_api_key:
            headers["x-api-key"] = _config.anthropic_api_key
        elif api_format == "openai" and _config.openai_api_key:
            headers["Authorization"] = f"Bearer {_config.openai_api_key}"

    # Ensure anthropic-version is set
    if api_format == "anthropic" and "anthropic-version" not in headers:
        headers["anthropic-version"] = "2023-06-01"

    return headers


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def _proxy_request(request: Request, api_format: str) -> Response:
    """Handle a proxied LLM API request."""
    # Determine upstream URL
    if api_format == "anthropic":
        upstream_base = ANTHROPIC_API
    else:
        upstream_base = OPENAI_API

    # Parse request body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    is_streaming = body.get("stream", False)

    # Anonymize user messages
    try:
        mappings = await _anonymize_request_body(body, api_format, _config.deny_list or None)
        if mappings:
            logger.info(
                "Anonymisiert: %d Begriffe ersetzt (%s)",
                len(mappings),
                ", ".join(list(mappings.values())[:3]),
            )
    except Exception as e:
        logger.warning("Anonymisierung fehlgeschlagen: %s — forwarding unmodified", e)
        mappings = {}

    # Build upstream headers: pass through original auth, add our own as fallback
    upstream_url = f"{upstream_base}{request.url.path}"
    headers = _build_upstream_headers(request, api_format)

    client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))

    if is_streaming:
        # Streaming: keep client alive for the duration of the response
        upstream_resp = await client.send(
            client.build_request("POST", upstream_url, json=body, headers=headers),
            stream=True,
        )

        if upstream_resp.status_code != 200:
            error_body = await upstream_resp.aread()
            await upstream_resp.aclose()
            await client.aclose()
            return Response(
                content=error_body,
                status_code=upstream_resp.status_code,
            )

        response_headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }

        async def generate():
            try:
                async for chunk in _stream_proxy(upstream_resp, mappings, api_format):
                    yield chunk.encode()
            finally:
                await upstream_resp.aclose()
                await client.aclose()

        return StreamingResponse(generate(), status_code=200, headers=response_headers)

    else:
        # Non-streaming: full request/response
        try:
            upstream_resp = await client.post(upstream_url, json=body, headers=headers)

            if upstream_resp.status_code != 200:
                return Response(
                    content=upstream_resp.content,
                    status_code=upstream_resp.status_code,
                )

            # Rehydrate the full response
            resp_data = upstream_resp.json()
            if mappings:
                resp_text = json.dumps(resp_data, ensure_ascii=False)
                for codename, original in sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True):
                    resp_text = resp_text.replace(codename, original)
                resp_data = json.loads(resp_text)

            return JSONResponse(resp_data)
        finally:
            await client.aclose()


async def handle_anthropic(request: Request) -> Response:
    try:
        return await _proxy_request(request, "anthropic")
    except Exception as e:
        logger.error("Proxy error (anthropic): %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


async def handle_openai(request: Request) -> Response:
    try:
        return await _proxy_request(request, "openai")
    except Exception as e:
        logger.error("Proxy error (openai): %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


async def handle_health(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "proxy": "austrai",
        "api_url": "lokal",
        "anthropic": bool(_config and _config.anthropic_api_key),
        "openai": bool(_config and _config.openai_api_key),
    })


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config: ProxyConfig | None = None) -> Starlette:
    global _config
    _config = config or ProxyConfig.load()
    _init_file_logging()

    return Starlette(
        routes=[
            Route("/v1/messages", handle_anthropic, methods=["POST"]),
            Route("/v1/chat/completions", handle_openai, methods=["POST"]),
            Route("/health", handle_health, methods=["GET"]),
        ],
    )

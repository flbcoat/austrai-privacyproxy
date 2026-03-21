#!/usr/bin/env python3
"""AUSTR.AI PrivacyProxy MCP Server — privacy firewall for LLM interactions.

Anonymizes sensitive text before it reaches any LLM, then rehydrates
the response so the user sees the original names and data.

Two tools:
  aai_process  — Full pipeline: anonymize → LLM → rehydrate
  aai_settings — Manage persistent deny_list and configuration

Setup:
  claude mcp add austrai -- python3 /path/to/privacyproxy_mcp.py

Requirements:
  pip install mcp httpx
"""

import json
import logging
import os
import sys
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL = os.environ.get("PRIVACYPROXY_API_URL", "https://austr.ai")
TIMEOUT = float(os.environ.get("PRIVACYPROXY_TIMEOUT", "90"))
SETTINGS_FILE = Path.home() / ".privacyproxy" / "mcp_settings.json"

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("austrai-mcp")

server = Server("austrai")


# ---------------------------------------------------------------------------
# Persistent settings
# ---------------------------------------------------------------------------

def _load_settings() -> dict:
    """Load persistent settings from disk."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {"deny_list": [], "prompt": ""}


def _save_settings(settings: dict) -> None:
    """Save settings to disk."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="aai_process",
            description=(
                "AUSTR.AI Privacy Pipeline: Erkennt sensible Daten im Text, "
                "anonymisiert sie mit Codenames, sendet den anonymisierten Text "
                "ans LLM, und ersetzt die Codenames in der Antwort wieder durch "
                "die Originaldaten. Der User sieht das fertige Ergebnis — "
                "auf dem LLM-Server landen nur anonymisierte Inhalte."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Der zu verarbeitende Text",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Anweisung ans LLM (z.B. 'Fasse zusammen', 'Beantworte diese E-Mail')",
                        "default": "Beantworte diese Nachricht professionell auf Deutsch.",
                    },
                    "deny_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Zusaetzliche Begriffe die anonymisiert werden sollen (Firmen, Projekte, etc.). Werden mit den gespeicherten Settings zusammengefuehrt.",
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="aai_settings",
            description=(
                "AUSTR.AI Einstellungen verwalten: Deny-List (Begriffe die immer "
                "anonymisiert werden), Standard-Prompt, API-URL. "
                "Aenderungen werden persistent gespeichert."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["show", "add_terms", "remove_terms", "set_prompt", "clear"],
                        "description": "Aktion: show=aktuelle Settings anzeigen, add_terms=Begriffe zur Deny-List hinzufuegen, remove_terms=Begriffe entfernen, set_prompt=Standard-Prompt setzen, clear=alles zuruecksetzen",
                    },
                    "terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Begriffe fuer add_terms/remove_terms",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Neuer Standard-Prompt fuer set_prompt",
                    },
                },
                "required": ["action"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "aai_process":
        return await _handle_process(arguments)
    elif name == "aai_settings":
        return _handle_settings(arguments)
    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def _handle_process(args: dict):
    """Full privacy pipeline: detect → anonymize → LLM → rehydrate."""
    try:
        settings = _load_settings()

        # Merge persistent deny_list with per-request deny_list
        deny_list = list(settings.get("deny_list", []))
        if args.get("deny_list"):
            deny_list.extend(args["deny_list"])
        # Deduplicate
        deny_list = list(dict.fromkeys(deny_list)) if deny_list else None

        # Use saved prompt as default, override with per-request prompt
        prompt = args.get("prompt") or settings.get("prompt") or \
            "Beantworte diese Nachricht professionell auf Deutsch."

        body = {"text": args["text"], "prompt": prompt}
        if deny_list:
            body["deny_list"] = deny_list

        async with httpx.AsyncClient(base_url=API_URL, timeout=TIMEOUT) as client:
            resp = await client.post("/api/process", json=body)
            resp.raise_for_status()
            data = resp.json()

        # Build clean output
        entities = data.get("entities", [])
        entity_lines = []
        for e in entities[:10]:
            entity_lines.append(f"  {e['entity_type']:20s} | {e['text']}")
        if len(entities) > 10:
            entity_lines.append(f"  ... +{len(entities) - 10} weitere")

        sensitivity = data.get("sensitivity", {})
        risk = sensitivity.get("risk_level", "?") if sensitivity else "?"

        output = [
            f"{len(entities)} sensible Begriffe erkannt (Risiko: {risk}):",
            *entity_lines,
            "",
            "--- Anonymisierter Text (auf dem LLM-Server) ---",
            data["anonymized_text"],
            "",
            "--- Antwort (rehydriert) ---",
            data["llm_response_rehydrated"],
        ]

        return [TextContent(type="text", text="\n".join(output))]

    except httpx.ConnectError:
        return [TextContent(
            type="text",
            text=f"Verbindung zu {API_URL} fehlgeschlagen. Laeuft der Server?",
        )]
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            detail = e.response.text[:200]
        return [TextContent(type="text", text=f"API-Fehler ({e.response.status_code}): {detail}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Fehler: {type(e).__name__}: {e}")]


def _handle_settings(args: dict):
    """Manage persistent settings."""
    action = args["action"]
    settings = _load_settings()

    if action == "show":
        deny_list = settings.get("deny_list", [])
        prompt = settings.get("prompt", "")
        lines = [
            f"API: {API_URL}",
            f"Settings: {SETTINGS_FILE}",
            "",
            f"Deny-List ({len(deny_list)} Begriffe):",
        ]
        if deny_list:
            for term in deny_list:
                lines.append(f"  - {term}")
        else:
            lines.append("  (leer)")
        lines.append("")
        lines.append(f"Standard-Prompt: {prompt or '(Standard)'}")
        return [TextContent(type="text", text="\n".join(lines))]

    elif action == "add_terms":
        terms = args.get("terms", [])
        if not terms:
            return [TextContent(type="text", text="Keine Begriffe angegeben.")]
        existing = set(settings.get("deny_list", []))
        new_terms = [t for t in terms if t not in existing]
        settings.setdefault("deny_list", []).extend(new_terms)
        _save_settings(settings)
        return [TextContent(
            type="text",
            text=f"{len(new_terms)} Begriffe hinzugefuegt: {', '.join(new_terms)}\n"
                 f"Deny-List hat jetzt {len(settings['deny_list'])} Begriffe.",
        )]

    elif action == "remove_terms":
        terms = args.get("terms", [])
        if not terms:
            return [TextContent(type="text", text="Keine Begriffe angegeben.")]
        remove_set = set(t.lower() for t in terms)
        before = len(settings.get("deny_list", []))
        settings["deny_list"] = [
            t for t in settings.get("deny_list", [])
            if t.lower() not in remove_set
        ]
        removed = before - len(settings["deny_list"])
        _save_settings(settings)
        return [TextContent(
            type="text",
            text=f"{removed} Begriffe entfernt. Deny-List hat jetzt {len(settings['deny_list'])} Begriffe.",
        )]

    elif action == "set_prompt":
        prompt = args.get("prompt", "")
        settings["prompt"] = prompt
        _save_settings(settings)
        return [TextContent(
            type="text",
            text=f"Standard-Prompt gesetzt: {prompt or '(zurueckgesetzt)'}",
        )]

    elif action == "clear":
        settings = {"deny_list": [], "prompt": ""}
        _save_settings(settings)
        return [TextContent(type="text", text="Alle Einstellungen zurueckgesetzt.")]

    return [TextContent(type="text", text=f"Unbekannte Aktion: {action}")]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    logger.info("AUSTR.AI MCP Server gestartet (API: %s)", API_URL)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

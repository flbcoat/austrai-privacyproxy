"""AUSTR.AI Auto-Router.

Intent classification + provider/model selection for the opt-in Auto-Routing
feature. Activated via Advanced Settings toggle.

PRIVACY INVARIANT (hard rule, enforced by call site in chat_api.py):
    Every text passed to classify_intent() MUST already be anonymized.
    The router is not allowed to see original user input. This mirrors the
    core AUSTR.AI guarantee: no raw PII ever leaves local processing.

Cascade strategy (graceful degradation depending on user's installed stack):
    Stage 1: Local LLM via Ollama/LMStudio  (if configured + reachable)
    Stage 2: sentence-transformers embeddings  (if [routing] extra installed)
    Stage 3: Keyword rules  (always available, last resort)

Prefer-Chains:
    Per task a ranked list of (provider, model) pairs. The first pair whose
    provider is configured (has an API key) and whose model is in that
    provider's model catalog wins.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger("austrai.router")

TASK_LABELS = ("trivial", "reasoning", "code", "long_context", "creative", "general")

# Ordered prefer-chains per task. Adjust to product-curated defaults.
# Users with at least one provider configured will always get a working pick,
# because the fallback at the end of pick_model iterates all configured
# providers.
#
# NOTE on model IDs: we stick to dated Anthropic IDs that are known to exist
# in the public API (claude-opus-4-20250514, claude-sonnet-4-20250514,
# claude-haiku-4-5-20251001). The newer marketing names in MODEL_CAPABILITIES
# (claude-opus-4-7 etc.) are exposed to power users via the dropdown, but
# auto-routing uses only confirmed IDs so it can never degrade a basic user
# to a 4xx error by surprise. Update these chains after verifying new IDs
# against Anthropic's API.
# Cost-aware default chains. Opus is reserved for explicit reasoning tasks
# only — for general writing, code, creative, even short answers, Sonnet
# is the right default (10× cheaper, comparable quality for non-proof
# work). Haiku for genuinely trivial Q&A. This reflects Florian's
# observation: "kurzes Mail soll nicht Opus sein".
DEFAULT_PREFER_CHAINS: dict[str, list[tuple[str, str]]] = {
    "trivial": [
        ("anthropic", "claude-haiku-4-5-20251001"),
        ("openai", "gpt-4.1-nano"),
        ("mistral", "mistral-small-latest"),
        ("google", "gemini-2.5-flash"),
    ],
    "reasoning": [
        # ONLY here is Opus first — for proofs, multi-step logic, tough math
        ("anthropic", "claude-opus-4-20250514"),
        ("openai", "o3"),
        ("anthropic", "claude-sonnet-4-20250514"),
        ("openai", "o4-mini"),
    ],
    "code": [
        # Sonnet handles >90% of code tasks fine; Opus is overkill for typical refactors
        ("anthropic", "claude-sonnet-4-20250514"),
        ("openai", "gpt-4.1"),
        ("mistral", "codestral-latest"),
        ("anthropic", "claude-opus-4-20250514"),
    ],
    "long_context": [
        # Long context: Sonnet first because cheaper-per-token matters more here
        ("anthropic", "claude-sonnet-4-20250514"),
        ("google", "gemini-2.5-pro"),
        ("anthropic", "claude-opus-4-20250514"),
    ],
    "creative": [
        # Sonnet for creative writing, emails, drafts. Opus only as fallback.
        ("anthropic", "claude-sonnet-4-20250514"),
        ("openai", "gpt-4.1"),
        ("mistral", "mistral-large-latest"),
        ("anthropic", "claude-opus-4-20250514"),
    ],
    "general": [
        ("anthropic", "claude-sonnet-4-20250514"),
        ("openai", "gpt-4.1"),
        ("mistral", "mistral-large-latest"),
        ("google", "gemini-2.5-flash"),
    ],
}

# Default anchor prompts for Stage 2 (sentence-transformers).
# Multilingual (DE + EN) because AUSTR.AI user base is DACH primarily.
# Power users can override via Advanced Settings > Anker-Prompts.
DEFAULT_ANCHORS: dict[str, list[str]] = {
    "trivial": [
        "Wie viele Stunden hat eine Woche?",
        "Was ist die Hauptstadt von Frankreich?",
        "Wann wurde Österreich gegründet?",
        "Wie spät ist es gerade?",
        "What is 5 plus 3?",
        "Convert 10 kilometers to miles.",
    ],
    "reasoning": [
        # Logik / Analyse
        "Löse diese logische Aufgabe: Wenn A immer B impliziert und B immer C, folgt daraus dass A immer C impliziert?",
        "Erkläre mir die Kausalität zwischen Inflation und Zinsen schrittweise.",
        "Analysiere die Vor- und Nachteile einer Mikroservice-Architektur.",
        "Warum widerspricht diese Aussage der Thermodynamik?",
        "Why does quantum entanglement violate Bell's inequality?",
        "Break down this proof step by step.",
        # Mathe-spezifisch (real-world Anker, der Florian's "Mathe-Rätsel" matcht)
        "Ich brauche ein schwieriges Mathe-Rätsel.",
        "Gib mir das härteste Logik-Rätsel das es gibt.",
        "Berechne das Integral von x² von 0 bis 1.",
        "Beweise den Satz von Pythagoras.",
        "Eine knifflige Mathe-Aufgabe bitte, möglichst komplex.",
        "Give me a really hard math puzzle.",
        "Solve this complex equation system step by step.",
        # User-meta-intent ("brauche das beste Modell")
        "Nutze dein bestes Modell für diese komplexe Aufgabe.",
        "Ich brauche dein klügstes Modell für ein schwieriges Problem.",
        "Use your best model for this hard reasoning task.",
    ],
    "code": [
        "Schreib mir eine Python-Funktion zur Fibonacci-Berechnung.",
        "Warum funktioniert dieser JavaScript-Code nicht?",
        "Refactor this TypeScript React component for better performance.",
        "Wie implementiere ich einen Binary-Search-Tree in Rust?",
        "Debug this stack trace and propose a fix.",
        "Erkläre mir was dieser Regex macht.",
    ],
    "long_context": [
        "Fasse dieses Dokument in drei Sätzen zusammen.",
        "Extrahiere alle Erwähnungen von Zeitangaben aus diesem Vertrag.",
        "Analyze this 20-page policy document for inconsistencies.",
        "Vergleiche die Argumentation in diesen beiden Artikeln.",
    ],
    "creative": [
        "Schreib mir eine kurze Erzählung über einen Drachen in Wien.",
        "Brainstorme Namen für eine KI-Firma.",
        "Compose a haiku about autumn leaves.",
        "Erfinde einen Werbeslogan für ein Kaffeehaus in der Josefstadt.",
        "Write a short dialogue between two rivals.",
    ],
}

# Short, constrained prompt sent to the local LLM in Stage 1.
# Deliberately minimal and in English to avoid triggering system-prompt
# defensiveness in instruction-tuned local models.
_STAGE1_PROMPT_TEMPLATE = (
    "Classify this user request into EXACTLY ONE label. Default to the "
    "cheapest sufficient label — only escalate to 'reasoning' when the task "
    "REALLY needs multi-step proof or hard math.\n\n"
    "Labels (cheapest → most expensive):\n"
    "- trivial: short factual Q&A, greetings, definitions, simple lookups, short emails, small edits\n"
    "- creative: writing emails, summaries, brainstorms, drafts, rephrasings\n"
    "- code: programming, debugging, code explanations\n"
    "- long_context: input is >3000 chars or asks to summarize a long document\n"
    "- reasoning: ONLY for hard logic puzzles, mathematical proofs, multi-step analysis "
    "that genuinely needs deep thinking. NOT for normal questions.\n"
    "- general: none of the above\n\n"
    "Respond with EXACTLY ONE word from the list. Nothing else.\n\n"
    "Request: {text}"
)


def classify_intent(
    anonymized_text: str,
    local_llm_provider: Optional[str] = None,
    local_llm_model: Optional[str] = None,
    anchors: Optional[dict[str, list[str]]] = None,
) -> Tuple[str, str]:
    """Classify a (already-anonymized) prompt into one of TASK_LABELS.

    Returns:
        (label, stage_name). stage_name is "local_llm" | "embeddings" | "rules".

    Privacy: Caller MUST pass already-anonymized text. The router has no
    facility to anonymize input; it trusts that pipeline invariant.
    """
    text = (anonymized_text or "").strip()
    if not text:
        return "trivial", "rules"

    # --- Stage 0: Hard user-meta-override ---
    # If the user explicitly requests the strongest model (e.g. "verwende dein
    # bestes Modell", "schwerste Aufgabe"), short-circuit to reasoning. This
    # gives users a "speak to the router" knob without opening Settings.
    override = _user_intent_override(text)
    if override:
        return override, "user_hint"

    # --- Stage 1: Local LLM (if a local provider is configured) ---
    if local_llm_provider and local_llm_model:
        try:
            label = _classify_via_local_llm(text, local_llm_provider, local_llm_model)
            if label in TASK_LABELS:
                return label, "local_llm"
        except Exception as e:
            logger.warning("Router Stage 1 (local LLM) failed: %s", e)

    # --- Stage 2: sentence-transformers embeddings ---
    try:
        from ._embedding_classifier import classify_via_embeddings  # type: ignore

        label = classify_via_embeddings(text, anchors or DEFAULT_ANCHORS)
        if label in TASK_LABELS:
            return label, "embeddings"
    except ImportError:
        # [routing] extra not installed — expected for lean installs
        pass
    except Exception as e:
        logger.warning("Router Stage 2 (embeddings) failed: %s", e)

    # --- Stage 3: Keyword rules ---
    return keyword_classify(text), "rules"


# Hard user-meta hints. When ANY of these phrases appear in the prompt,
# we route to "reasoning" regardless of what the semantic classifier thinks.
# Rationale: the user is explicitly asking for the strongest model. That signal
# beats whatever soft classification an embedding similarity would yield.
_USER_REASONING_HINTS = (
    # German
    "bestes modell", "stärkstes modell", "smartestes modell", "klügstes modell",
    "intelligentestes modell", "leistungsfähigstes modell", "stärkere ki", "bestes ki",
    "verwende dein bestes", "nutze dein bestes", "nimm dein bestes",
    "schwerste", "schwerstes", "härteste", "härtestes", "schwierigste", "kniffligste",
    "möglichst komplex", "möglichst schwer", "so schwer wie möglich",
    # English
    "best model", "smartest model", "strongest model", "most capable model",
    "use your best", "your best model", "your strongest",
    "hardest", "toughest", "most difficult", "most challenging",
    "as hard as possible", "as complex as possible",
)


def _user_intent_override(text: str) -> Optional[str]:
    """Detect explicit user-meta-intent that overrides the semantic classifier.

    Returns a task label if the user has explicitly signalled they want the
    strongest model, else None. Currently only "reasoning" is overridden;
    extend this list if other categories accumulate user-meta-cues over time.
    """
    t = text.lower()
    if any(h in t for h in _USER_REASONING_HINTS):
        return "reasoning"
    return None


def keyword_classify(text: str) -> str:
    """Last-resort keyword heuristic. Coarse but deterministic."""
    t = text.lower()

    # Code wins over everything if fences or strong code markers present
    if "```" in text or any(
        kw in t for kw in (
            "python", "javascript", "typescript",
            "funktion schreib", "def ", "class ", "function ",
            "stack trace", "regex", "segfault", "compile error",
        )
    ):
        return "code"

    if len(text) > 3000:
        return "long_context"

    # Reasoning: logic, math, puzzles, analytical tasks. Big keyword set
    # because Stage 3 (rules) needs to catch what Stage 2 (embeddings) misses.
    if any(kw in t for kw in (
        # Logik / Analyse (DE)
        "warum", "erkläre", "erklaer", "analysiere", "beweise", "löse", "loese",
        "berechne", "rechne", "schlussfolge", "leite ab", "begründe", "beweis",
        # Mathe (DE)
        "mathe", "mathematik", "algebra", "geometrie", "analysis",
        "rätsel", "raetsel", "knobel", "knifflig", "kniffelig", "puzzle",
        "gleichung", "formel", "theorem", "integral", "ableitung", "matrix",
        "aufgabe", "rechenaufgabe", "knobelaufgabe",
        # Intensifier (DE)
        "schwer", "schwierig", "komplex", "kompliziert", "anspruchsvoll",
        # English
        "why does", "explain", "analyze", "prove", "derive", "compute",
        "math", "mathematics", "equation", "theorem", "integral", "matrix",
        "puzzle", "tricky", "riddle",
        "hard", "difficult", "complex", "challenging",
    )):
        return "reasoning"

    if any(kw in t for kw in (
        "schreib mir", "schreibe mir", "erfinde", "brainstorm", "gedicht", "geschichte",
        "write me", "compose", "haiku", "slogan",
    )):
        return "creative"

    # Short prompts without reasoning/code/creative cues are treated as
    # trivial fact-questions. Fragezeichen sind explizit erlaubt (Faktenfragen
    # wie "Wie viele Stunden hat eine Woche?" gehoeren hierher, nicht zu
    # "general"). The earlier branches already caught code/reasoning/creative.
    if len(text) < 150:
        return "trivial"

    return "general"


def _classify_via_local_llm(text: str, provider: str, model: str) -> Optional[str]:
    """Single-prompt classification via local Ollama/LMStudio instance.

    No Tool-Calling, no fancy function schemas — just a strict-format prompt.
    Latency on qwen2.5:0.5b is ~100-200ms, which is invisible in the send flow.
    """
    import httpx

    if provider not in ("ollama", "lmstudio"):
        return None

    base_url = (
        "http://localhost:11434" if provider == "ollama" else "http://localhost:1234"
    )
    # Both Ollama and LMStudio expose an OpenAI-compatible endpoint.
    url = f"{base_url}/v1/chat/completions"

    prompt = _STAGE1_PROMPT_TEMPLATE.format(text=text[:2000])

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 12,
                    "temperature": 0.0,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            raw = (
                resp.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
                .lower()
            )
    except Exception as e:
        logger.debug("Local LLM router call failed: %s", e)
        return None

    # Parse: pick the first TASK_LABEL token that appears
    for label in TASK_LABELS:
        if label in raw:
            return label
    return None


def pick_model(
    task: str,
    configured_providers: dict,
    prefer_chains: Optional[dict[str, list[tuple[str, str]]]] = None,
) -> Tuple[str, str]:
    """Resolve (provider, model) from prefer-chain based on configured providers.

    Args:
        task: One of TASK_LABELS.
        configured_providers: dict[provider_id -> {configured: bool, models: [...]}].
        prefer_chains: Override default chains (Power-User setting).

    Returns:
        (provider, model) guaranteed to reference a configured provider that
        exposes this model. Falls back to first configured provider's first
        model if no chain match. Last-resort fallback prevents hard error.
    """
    chains = prefer_chains or DEFAULT_PREFER_CHAINS
    chain = chains.get(task, chains.get("general", []))

    for provider, model in chain:
        prov = configured_providers.get(provider)
        if prov and prov.get("configured") and _model_in_catalog(prov, model):
            return provider, model

    # Fallback: first configured provider with at least one model
    for pid, prov in configured_providers.items():
        if prov.get("configured") and prov.get("models"):
            return pid, prov["models"][0]["id"]

    # Ultimate fallback (should only hit if no provider is configured)
    return "anthropic", "claude-sonnet-4-20250514"


def _model_in_catalog(prov: dict, model_id: str) -> bool:
    return any(m.get("id") == model_id for m in prov.get("models", []))


def detect_local_llm_router(configured_providers: dict) -> Tuple[Optional[str], Optional[str]]:
    """Pick a small local model to use for Stage-1 routing decisions.

    Preference: Ollama > LMStudio. Picks the first available model in that
    provider's catalog, preferring small/fast model names when obvious.
    """
    for provider in ("ollama", "lmstudio"):
        prov = configured_providers.get(provider)
        if not prov:
            continue
        models = prov.get("models", [])
        if not models:
            continue
        # Heuristic: prefer small models for routing (qwen2.5:0.5b, phi3:mini, etc.)
        small_hints = ("0.5b", "1.5b", "1b", "mini", "small", "tiny", "0_5", "0.5")
        for m in models:
            mid = (m.get("id") or "").lower()
            if any(h in mid for h in small_hints):
                return provider, m["id"]
        # Fall back to first model if no small hint matched
        return provider, models[0]["id"]
    return None, None

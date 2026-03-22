"""LLM-basierte Detection — zweite Erkennungsschicht (optional).

Nutzt ein lokales LLM (via llama-cpp-python oder Ollama) um sensible Daten
zu erkennen, die Presidio/SpaCy nicht fangen. Das LLM versteht KONTEXT
und kann z.B. erkennen dass "Projekt Phoenix" ein vertraulicher Projektname ist.

Laeuft komplett lokal. Optional — wenn kein LLM verfuegbar, wird nur Presidio genutzt.
"""

import json
import logging
import subprocess

logger = logging.getLogger("austrai.llm_detector")

# System prompt for entity extraction
SYSTEM_PROMPT = """Du bist ein Datenschutz-Experte. Analysiere den folgenden Text und liste ALLE Begriffe auf, die personenbezogen, vertraulich oder identifizierend sind.

Kategorien:
- Personennamen (auch Vornamen allein)
- Firmennamen und Organisationen
- Adressen und Orte
- Telefonnummern, E-Mails
- Kontonummern, IBANs, Kreditkarten
- Passwörter, API Keys, Tokens
- Diagnosen, Medikamente
- Projektnamen, interne Begriffe
- Alles was eine Person oder Firma identifizierbar macht

Antworte NUR als JSON-Array mit den gefundenen Begriffen. Keine Erklärung.
Beispiel: ["Thomas Gruber", "Innovatech GmbH", "AT48 3200 0000 1234"]"""


def detect_with_llm(text: str, method: str = "ollama", model: str = "qwen2.5:0.5b") -> list[str]:
    """Use a local LLM to find sensitive terms that rule-based detection misses.

    Args:
        text: The text to analyze.
        method: "ollama" (requires Ollama running) or "llamacpp" (requires llama-cpp-python).
        model: Model name/path.

    Returns:
        List of detected sensitive terms (strings).
    """
    if method == "ollama":
        return _detect_ollama(text, model)
    elif method == "llamacpp":
        return _detect_llamacpp(text, model)
    else:
        logger.warning("Unbekannte LLM-Methode: %s", method)
        return []


def _detect_ollama(text: str, model: str) -> list[str]:
    """Detect via Ollama API (must be running locally)."""
    try:
        import httpx
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": f"{SYSTEM_PROMPT}\n\nText:\n{text[:2000]}",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500},
            },
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json().get("response", "")
        return _parse_json_array(result)
    except Exception as e:
        logger.debug("Ollama nicht verfuegbar: %s", e)
        return []


def _detect_llamacpp(text: str, model: str) -> list[str]:
    """Detect via llama-cpp-python (local GGUF model)."""
    try:
        from llama_cpp import Llama
    except ImportError:
        logger.debug("llama-cpp-python nicht installiert.")
        return []

    try:
        llm = Llama(model_path=model, n_ctx=2048, n_threads=2, verbose=False)
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
            max_tokens=500,
            temperature=0.1,
        )
        result = response["choices"][0]["message"]["content"]
        return _parse_json_array(result)
    except Exception as e:
        logger.debug("llama-cpp Fehler: %s", e)
        return []


def _parse_json_array(text: str) -> list[str]:
    """Parse a JSON array from LLM output, handling common formatting issues."""
    text = text.strip()

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return [str(item) for item in result if isinstance(item, str) and len(item) >= 2]
    except json.JSONDecodeError:
        pass

    # Try extracting JSON array from surrounding text
    import re
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return [str(item) for item in result if isinstance(item, str) and len(item) >= 2]
        except json.JSONDecodeError:
            pass

    return []


def is_ollama_available(model: str = "qwen2.5:0.5b") -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        models = [m["name"] for m in resp.json().get("models", [])]
        return any(model in m for m in models)
    except Exception:
        return False

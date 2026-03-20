"""Local LLM for privacy-preserving text summarization.

Uses Qwen2.5-0.5B-Instruct (GGUF Q4_K_M, ~350MB) via llama-cpp-python.
Runs entirely on CPU, no GPU required. Designed for minimal hardware.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
MODEL_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    "/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
MODEL_DIR = Path.home() / ".privacyproxy" / "models"
EXPECTED_MIN_SIZE_BYTES = 300_000_000  # ~350MB, sanity check

# ---------------------------------------------------------------------------
# System prompts (German)
# ---------------------------------------------------------------------------
SUMMARIZE_SYSTEM_PROMPT = (
    "Du bist ein Datenschutz-Assistent. Fasse den folgenden Text zusammen, aber:\n"
    "1. Ersetze ALLE Eigennamen (Personen, Firmen, Orte) durch generische "
    "Beschreibungen wie \"eine Person\", \"ein Unternehmen\", \"eine Stadt\"\n"
    "2. Ersetze alle Zahlen, Betraege, Daten und Adressen durch \"[REDACTED]\"\n"
    "3. Fasse in 3-5 Saetzen zusammen\n"
    "4. Beschreibe nur die ART des Inhalts, keine spezifischen Details\n"
    "5. Antworte in der gleichen Sprache wie der Eingabetext"
)

CLASSIFY_SYSTEM_PROMPT = (
    "Du bist ein Dokumenten-Klassifikator. Bestimme den Dokumenttyp des "
    "folgenden Textes. Antworte NUR mit einem einzelnen Wort aus dieser Liste:\n"
    "brief, vertrag, medizinisch, technisch, finanzbericht, rechnung, "
    "bewerbung, protokoll, gutachten, sonstiges\n"
    "Antworte NUR mit dem Dokumenttyp, ohne weitere Erklaerung."
)

# ---------------------------------------------------------------------------
# Module-level state (lazy-loaded)
# ---------------------------------------------------------------------------
_llm_instance = None
_llama_cpp_available: bool | None = None


def is_available() -> bool:
    """Check if llama-cpp-python is installed.

    Returns:
        True if llama-cpp-python can be imported, False otherwise.
    """
    global _llama_cpp_available
    if _llama_cpp_available is not None:
        return _llama_cpp_available
    try:
        import llama_cpp  # noqa: F401
        _llama_cpp_available = True
        logger.info("llama-cpp-python ist verfuegbar — lokale LLM-Features aktiviert.")
    except ImportError:
        _llama_cpp_available = False
        logger.info(
            "llama-cpp-python ist nicht installiert — lokale LLM-Features deaktiviert. "
            "Installieren mit: pip install llama-cpp-python"
        )
    return _llama_cpp_available


def ensure_model() -> str:
    """Download the GGUF model if not already present.

    Uses huggingface_hub for reliable downloads (proxy support, resume, progress).

    Returns:
        Absolute path to the downloaded GGUF file.

    Raises:
        RuntimeError: If the download fails or the file is corrupted.
    """
    model_path = MODEL_DIR / MODEL_FILENAME

    # Check if already downloaded and valid
    if model_path.exists() and model_path.stat().st_size >= EXPECTED_MIN_SIZE_BYTES:
        logger.debug("Modell bereits vorhanden: %s", model_path)
        return str(model_path)

    # Create model directory
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Lade lokales LLM-Modell herunter: %s (%s) ...",
        MODEL_FILENAME,
        MODEL_REPO,
    )

    try:
        from huggingface_hub import hf_hub_download

        downloaded_path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILENAME,
            local_dir=str(MODEL_DIR),
            local_dir_use_symlinks=False,
        )

        # Verify file size
        actual_size = os.path.getsize(downloaded_path)
        if actual_size < EXPECTED_MIN_SIZE_BYTES:
            os.remove(downloaded_path)
            raise RuntimeError(
                f"Heruntergeladene Datei ist zu klein ({actual_size} Bytes). "
                f"Erwartet mindestens {EXPECTED_MIN_SIZE_BYTES} Bytes. "
                f"Download moeglicherweise unvollstaendig."
            )

        logger.info(
            "Modell erfolgreich heruntergeladen: %s (%.1f MB)",
            downloaded_path,
            actual_size / (1024 * 1024),
        )
        return str(downloaded_path)

    except ImportError:
        raise RuntimeError(
            "huggingface_hub ist nicht installiert. "
            "Bitte installieren: pip install huggingface_hub"
        )
    except Exception as e:
        raise RuntimeError(
            f"Fehler beim Herunterladen des Modells: {type(e).__name__}: {e}"
        ) from e


def init_local_llm() -> None:
    """Load the local LLM model into memory.

    Downloads the model on first call if not present.
    Keeps the model in memory for subsequent calls.

    Raises:
        RuntimeError: If llama-cpp-python is not installed or model loading fails.
    """
    global _llm_instance

    if _llm_instance is not None:
        logger.debug("Lokales LLM bereits geladen.")
        return

    if not is_available():
        raise RuntimeError(
            "llama-cpp-python ist nicht installiert. "
            "Lokale LLM-Features sind nicht verfuegbar."
        )

    model_path = ensure_model()

    logger.info("Lade lokales LLM in den Speicher: %s ...", MODEL_FILENAME)

    try:
        from llama_cpp import Llama

        _llm_instance = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_threads=2,
            n_batch=64,
            verbose=False,
            use_mlock=False,
        )

        logger.info("Lokales LLM erfolgreich geladen (Qwen2.5-0.5B-Instruct Q4_K_M).")

    except Exception as e:
        _llm_instance = None
        raise RuntimeError(
            f"Fehler beim Laden des lokalen LLM: {type(e).__name__}: {e}"
        ) from e


def _get_llm():
    """Get the loaded LLM instance, initializing if needed.

    Returns:
        The Llama model instance.

    Raises:
        RuntimeError: If the model cannot be loaded.
    """
    if _llm_instance is None:
        init_local_llm()
    return _llm_instance


def summarize_locally(text: str, max_tokens: int = 512) -> str:
    """Summarize text locally, stripping all proper names and specifics.

    Uses the local Qwen2.5-0.5B model to generate a privacy-preserving summary.
    The system prompt instructs the model to:
    1. Summarize the content in 3-5 sentences
    2. Replace ALL proper names with generic descriptions
    3. Replace specific numbers, dates, addresses with "[REDACTED]"
    4. Focus on the type/category of content, not specifics
    5. Output in the same language as input

    Args:
        text: The input text to summarize.
        max_tokens: Maximum number of tokens in the summary (default 512).

    Returns:
        A privacy-preserving summary of the text.

    Raises:
        RuntimeError: If the local LLM is not available or fails.
    """
    if not is_available():
        raise RuntimeError("Lokales LLM ist nicht verfuegbar (llama-cpp-python nicht installiert).")

    llm = _get_llm()

    # Truncate input to fit within context window (reserve space for system prompt + output)
    # Rough estimate: 1 token ~ 4 chars for German text
    max_input_chars = (2048 - max_tokens - 200) * 4  # ~5400 chars
    truncated_text = text[:max_input_chars] if len(text) > max_input_chars else text

    try:
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": truncated_text},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            top_p=0.9,
        )

        content = response["choices"][0]["message"]["content"]
        if content is None:
            return "[Fehler: Leere Antwort vom lokalen LLM]"

        return content.strip()

    except Exception as e:
        logger.error("Fehler bei lokaler Zusammenfassung: %s", e, exc_info=True)
        return f"[Fehler bei lokaler Zusammenfassung: {type(e).__name__}]"


def classify_document(text: str) -> str:
    """Classify document type locally.

    Possible types: brief, vertrag, medizinisch, technisch, finanzbericht,
    rechnung, bewerbung, protokoll, gutachten, sonstiges.

    Args:
        text: The input text to classify.

    Returns:
        A single-word document type classification.

    Raises:
        RuntimeError: If the local LLM is not available or fails.
    """
    if not is_available():
        raise RuntimeError("Lokales LLM ist nicht verfuegbar (llama-cpp-python nicht installiert).")

    llm = _get_llm()

    # Only need first ~1000 chars for classification
    truncated_text = text[:1000] if len(text) > 1000 else text

    try:
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": truncated_text},
            ],
            max_tokens=20,
            temperature=0.1,
        )

        content = response["choices"][0]["message"]["content"]
        if content is None:
            return "sonstiges"

        # Clean up: take first word, lowercase, strip punctuation
        doc_type = content.strip().split()[0].lower().rstrip(".,;:!?")

        valid_types = {
            "brief", "vertrag", "medizinisch", "technisch", "finanzbericht",
            "rechnung", "bewerbung", "protokoll", "gutachten", "sonstiges",
        }

        if doc_type not in valid_types:
            logger.debug(
                "Unbekannter Dokumenttyp vom LLM: '%s' — verwende 'sonstiges'.",
                doc_type,
            )
            return "sonstiges"

        return doc_type

    except Exception as e:
        logger.error("Fehler bei lokaler Dokumentklassifikation: %s", e, exc_info=True)
        return "sonstiges"

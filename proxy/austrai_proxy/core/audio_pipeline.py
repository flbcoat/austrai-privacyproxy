"""Audio-Pipeline — Sprachnachrichten anonymisieren via Whisper.

Transkribiert Audio lokal mit OpenAI Whisper, erkennt PII im Transkript,
und gibt den anonymisierten Text zurück.

Unterstützt: MP3, WAV, M4A, OGG, FLAC, WEBM

Benötigt: faster-whisper (im Standard-Install enthalten)
"""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger("austrai.audio")


def transcribe_and_anonymize(
    audio_path: str,
    model_size: str = "base",
    language: str = "de",
    deny_list: list[str] | None = None,
) -> dict:
    """Transkribiert eine Audiodatei und anonymisiert das Transkript.

    1. Whisper transkribiert Audio → Text (lokal)
    2. Privacy Engine erkennt PII im Transkript
    3. Anonymisierter Text wird zurückgegeben

    Args:
        audio_path: Pfad zur Audiodatei
        model_size: Whisper-Modellgröße ("tiny", "base", "small", "medium", "large")
        language: Sprache ("de" für Deutsch)
        deny_list: Zusätzliche Begriffe

    Returns:
        dict mit: transcript, anonymized_text, mappings, duration, model
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audiodatei nicht gefunden: {audio_path}")

    supported = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".mpeg"}
    if path.suffix.lower() not in supported:
        raise ValueError(f"Audioformat '{path.suffix}' nicht unterstützt. "
                        f"Unterstützt: {', '.join(sorted(supported))}")

    # Try faster-whisper first (more efficient), fall back to openai-whisper
    transcript, duration = _transcribe(audio_path, model_size, language)

    if not transcript.strip():
        return {
            "transcript": "",
            "anonymized_text": "",
            "mappings": {},
            "duration_seconds": duration,
            "model": f"whisper-{model_size}",
            "entity_count": 0,
        }

    # Anonymize the transcript
    from austrai_proxy.core import get_engine
    engine = get_engine(memory_enabled=False)
    result = engine.anonymize(transcript, deny_list=deny_list)

    logger.info(
        "Audio anonymisiert: %.1fs, %d Zeichen, %d Entities.",
        duration, len(transcript), len(result.mappings),
    )

    return {
        "transcript": transcript,
        "anonymized_text": result.anonymized_text,
        "mappings": result.mappings,
        "session_id": result.session_id,
        "duration_seconds": duration,
        "model": f"whisper-{model_size}",
        "entity_count": len(result.mappings),
    }


def _transcribe(audio_path: str, model_size: str, language: str) -> tuple[str, float]:
    """Transcribe audio file. Tries faster-whisper, then openai-whisper."""

    # Try faster-whisper first (uses CTranslate2, much faster on CPU)
    try:
        return _transcribe_faster_whisper(audio_path, model_size, language)
    except ImportError:
        pass

    # Fall back to openai-whisper
    try:
        return _transcribe_openai_whisper(audio_path, model_size, language)
    except ImportError:
        pass

    raise ImportError(
        "Audio-Pipeline braucht Whisper. Installiere eine der Optionen:\n"
        "  pip install faster-whisper    (empfohlen, schneller)\n"
        "  pip install openai-whisper    (Original von OpenAI)\n"
        "  Oder: pip install austrai"
    )


def _transcribe_faster_whisper(audio_path: str, model_size: str, language: str) -> tuple[str, float]:
    """Transcribe using faster-whisper (CTranslate2-based)."""
    from faster_whisper import WhisperModel

    logger.info("Transkribiere mit faster-whisper (Modell: %s)...", model_size)

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, language=language, beam_size=5)

    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    transcript = " ".join(text_parts)
    duration = info.duration if hasattr(info, 'duration') else 0.0

    return transcript, duration


def _transcribe_openai_whisper(audio_path: str, model_size: str, language: str) -> tuple[str, float]:
    """Transcribe using openai-whisper."""
    import whisper

    logger.info("Transkribiere mit openai-whisper (Modell: %s)...", model_size)

    model = whisper.load_model(model_size)
    result = model.transcribe(audio_path, language=language)

    transcript = result.get("text", "").strip()
    # Estimate duration from segments
    segments = result.get("segments", [])
    duration = segments[-1]["end"] if segments else 0.0

    return transcript, duration

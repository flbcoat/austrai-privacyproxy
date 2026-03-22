"""GLiNER-basierte PII-Erkennung — Schicht 1 der Detection Pipeline.

GLiNER (Generalist and Lightweight model for Named Entity Recognition)
erreicht F1 0.98 bei PII-Erkennung und ist deutlich schneller als
SpaCy NER + Presidio.

Modell: urchade/gliner_multi_pii-v1 (~400 MB, wird beim ersten Start geladen)
"""

import logging
import os

logger = logging.getLogger("austrai.gliner")

# PII-Label-Kategorien für GLiNER
PII_LABELS = [
    "person",
    "organization",
    "phone number",
    "email",
    "iban",
    "credit card number",
    "address",
    "date of birth",
    "password",
    "ip address",
    "medical condition",
    "social security number",
    "passport number",
    "license plate",
]

# Map GLiNER labels to AUSTR.AI entity types
LABEL_MAP = {
    "person": "PERSON",
    "organization": "ORGANIZATION",
    "phone number": "PHONE_NUMBER",
    "email": "EMAIL_ADDRESS",
    "iban": "AT_IBAN",
    "credit card number": "CREDIT_CARD",
    "address": "LOCATION",
    "date of birth": "EU_PII",
    "password": "CREDENTIAL",
    "ip address": "EU_PII",
    "medical condition": "SENSITIVE_DATA",
    "social security number": "AT_SVNR",
    "passport number": "EU_PII",
    "license plate": "EU_PII",
}

_model = None


def _get_model():
    """Lazy-load GLiNER model (downloads on first use, ~400 MB)."""
    global _model
    if _model is not None:
        return _model

    try:
        # Suppress warnings
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        import warnings
        warnings.filterwarnings("ignore", message=".*resume_download.*")
        from gliner import GLiNER
    except ImportError:
        raise ImportError("GLiNER braucht: pip install gliner")

    logger.info("Lade GLiNER PII-Modell (einmalig, ~400 MB)...")
    _model = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")
    logger.info("GLiNER bereit.")
    return _model


def detect_with_gliner(
    text: str,
    threshold: float = 0.4,
    labels: list[str] | None = None,
) -> list[dict]:
    """Detect PII entities using GLiNER.

    Args:
        text: Input text
        threshold: Minimum confidence score (0-1)
        labels: Custom labels (default: PII_LABELS)

    Returns:
        List of dicts with: entity_type, start, end, score, text
    """
    model = _get_model()

    entities = model.predict_entities(
        text,
        labels or PII_LABELS,
        threshold=threshold,
    )

    results = []
    for e in entities:
        entity_type = LABEL_MAP.get(e["label"], "CUSTOM")
        results.append({
            "entity_type": entity_type,
            "start": e["start"],
            "end": e["end"],
            "score": e["score"],
            "text": e["text"],
            "gliner_label": e["label"],
        })

    return results


def is_available() -> bool:
    """Check if GLiNER can be imported."""
    try:
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        from gliner import GLiNER
        return True
    except ImportError:
        return False

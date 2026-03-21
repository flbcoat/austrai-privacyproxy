"""AUSTR.AI Core — local privacy engine for PII detection and anonymization.

Usage:
    from austrai_proxy.core import get_engine

    engine = get_engine()
    result = engine.anonymize("Thomas Gruber, IBAN AT48 3200 0000 1234 5678")
    print(result.anonymized_text)  # "Arion, IBAN [AT_IBAN_1]"
    print(result.mappings)         # {"Arion": "Thomas Gruber", ...}

    restored = engine.rehydrate("Arion said hello", result.mappings)
    print(restored)                # "Thomas Gruber said hello"
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("austrai.core")

_engine = None


@dataclass
class AnonymizeResult:
    """Result of an anonymization operation."""
    anonymized_text: str
    mappings: dict[str, str]
    entities: list
    session_id: str | None = None


class PrivacyEngine:
    """Single entry point for all local anonymization.

    Lazily initializes SpaCy + Presidio on first use.
    Thread-safe after initialization.
    """

    def __init__(self, confidence_threshold: float = 0.6, spacy_model: str = "de_core_news_lg"):
        self._initialized = False
        self._confidence_threshold = confidence_threshold
        self._spacy_model = spacy_model
        self._session_store = None

    def _ensure_initialized(self):
        if self._initialized:
            return

        logger.info("Initialisiere AUSTR.AI Privacy Engine...")

        # Auto-download SpaCy model if needed
        from .setup import ensure_spacy_model
        if not ensure_spacy_model(self._spacy_model):
            raise RuntimeError(f"SpaCy-Modell '{self._spacy_model}' nicht verfuegbar.")

        # Initialize Presidio analyzer
        from . import detector
        detector.CONFIDENCE_THRESHOLD = self._confidence_threshold
        detector.init_analyzer()

        # Initialize session store
        from .session_store import SessionStore
        self._session_store = SessionStore()

        self._initialized = True
        logger.info("Privacy Engine bereit.")

    def anonymize(
        self,
        text: str,
        deny_list: list[str] | None = None,
        entity_types: list[str] | None = None,
    ) -> AnonymizeResult:
        """Detect and anonymize PII in text. Returns AnonymizeResult."""
        self._ensure_initialized()

        from .detector import detect
        from .anonymizer import anonymize

        entities = detect(text, entity_types=entity_types, deny_list=deny_list)
        anonymized_text, mappings = anonymize(text, entities)

        session_id = None
        if mappings and self._session_store:
            session_id = self._session_store.create_session(mappings)

        return AnonymizeResult(
            anonymized_text=anonymized_text,
            mappings=mappings,
            entities=entities,
            session_id=session_id,
        )

    def rehydrate(self, text: str, mappings: dict[str, str]) -> str:
        """Restore original values in text using mappings."""
        from .rehydrator import rehydrate
        return rehydrate(text, mappings)

    def rehydrate_session(self, text: str, session_id: str) -> tuple[str, int]:
        """Restore original values using a stored session. Returns (text, replacements_count)."""
        self._ensure_initialized()

        if not self._session_store:
            return text, 0

        mappings = self._session_store.get_session(session_id)
        if not mappings:
            return text, 0

        original = text
        restored = self.rehydrate(text, mappings)
        replacements = sum(
            1 for codename in mappings
            if codename in original or codename.lower() in original.lower()
        )
        return restored, replacements


def get_engine(**kwargs) -> PrivacyEngine:
    """Get or create the singleton PrivacyEngine."""
    global _engine
    if _engine is None:
        _engine = PrivacyEngine(**kwargs)
    return _engine

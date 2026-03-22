"""AUSTR.AI Core — local privacy engine for PII detection and anonymization.

Modules:
  - Detection Layer: Presidio + SpaCy + Context Learner + optional LLM
  - Codename Engine: Non-reversible abstract codenames
  - Mapping Store: SQLite + AES encryption, persistent across sessions
  - Memory Layer: ChromaDB + Embeddings, semantic long-term memory
  - Rehydrator: 3-pass restoration of original values

Usage:
    from austrai_proxy.core import get_engine

    engine = get_engine()
    result = engine.anonymize("Thomas Gruber, IBAN AT48 3200 0000 1234 5678")
    print(result.anonymized_text)  # "Arion, IBAN [AT_IBAN_1]"

    # Memory: store anonymized conversation
    engine.remember(result.anonymized_text, "LLM response here")

    # Memory: retrieve relevant context for new prompt
    context = engine.recall("Workshop für Versicherungskunden")
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
    """Single entry point for all local privacy operations.

    Integrates all modules:
    - Detection (Presidio + Context Learner + optional LLM)
    - Anonymization (Codename Engine)
    - Persistent Mapping Store (SQLite + encryption)
    - Memory Layer (ChromaDB + Embeddings)
    - Rehydration
    """

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        spacy_model: str = "de_core_news_sm",
        use_gliner: bool = True,
        use_llm_detector: bool = False,
        llm_method: str = "ollama",
        llm_model: str = "qwen3.5:0.8b",
        memory_enabled: bool = True,
    ):
        self._initialized = False
        self._confidence_threshold = confidence_threshold
        self._spacy_model = spacy_model
        self._use_gliner = use_gliner
        self._use_llm_detector = use_llm_detector
        self._llm_method = llm_method
        self._llm_model = llm_model
        self._memory_enabled = memory_enabled
        self._mapping_store = None
        self._memory = None
        self._gliner_available = False

    def _ensure_initialized(self):
        if self._initialized:
            return

        logger.info("Initialisiere AUSTR.AI Privacy Engine v3.2...")

        # Layer 1: GLiNER (primary PII detection, F1 0.98)
        if self._use_gliner:
            try:
                from .gliner_detector import is_available, _get_model
                if is_available():
                    _get_model()  # Pre-load
                    self._gliner_available = True
                    logger.info("Schicht 1: GLiNER PII-Modell geladen (F1 0.98).")
                else:
                    logger.info("GLiNER nicht verfuegbar — Fallback auf Presidio.")
            except Exception as e:
                logger.info("GLiNER Fehler: %s — Fallback auf Presidio.", e)

        # Layer 2: SpaCy + Presidio (regex patterns + NER fallback)
        from .setup import ensure_spacy_model
        if not ensure_spacy_model(self._spacy_model):
            raise RuntimeError(f"SpaCy-Modell '{self._spacy_model}' nicht verfuegbar.")

        from . import detector
        detector.CONFIDENCE_THRESHOLD = self._confidence_threshold
        detector.init_analyzer()
        logger.info("Schicht 2: Presidio + SpaCy (%s) + Regex-Patterns geladen.", self._spacy_model)

        # Layer 3: LLM detector (optional, for contextual detection)
        if self._use_llm_detector:
            from .llm_detector import is_ollama_available
            if is_ollama_available(self._llm_model):
                logger.info("Schicht 3: LLM Detector aktiv (Ollama: %s).", self._llm_model)
            else:
                logger.info("Schicht 3: LLM Detector nicht verfuegbar.")
                self._use_llm_detector = False

        # Persistent mapping store (encrypted SQLite)
        from .mapping_store import MappingStore
        self._mapping_store = MappingStore()
        logger.info("Mapping Store initialisiert (verschluesselt, persistent).")

        # Memory layer (optional)
        if self._memory_enabled:
            try:
                from .memory import MemoryLayer
                self._memory = MemoryLayer()
                logger.info("Memory Layer verfuegbar.")
            except Exception:
                logger.info("Memory Layer nicht verfuegbar.")
                self._memory = None

        self._initialized = True
        logger.info("Privacy Engine bereit (3-Schichten-Erkennung).")

    def anonymize(
        self,
        text: str,
        deny_list: list[str] | None = None,
        entity_types: list[str] | None = None,
    ) -> AnonymizeResult:
        """Detect and anonymize PII in text.

        Three-layer detection:
        1. GLiNER (F1 0.98, primary PII detection)
        2. Presidio + SpaCy + Regex (structured data, custom patterns)
        3. Optional: Local LLM (contextual understanding)

        Results from all layers are merged, deduplicated by position.
        """
        self._ensure_initialized()

        from .anonymizer import anonymize
        from .models import Entity

        all_entities: list[Entity] = []

        # Layer 1: GLiNER (high-precision PII detection)
        if self._gliner_available:
            try:
                from .gliner_detector import detect_with_gliner
                gliner_results = detect_with_gliner(text, threshold=0.4)
                for r in gliner_results:
                    all_entities.append(Entity(
                        entity_type=r["entity_type"],
                        start=r["start"],
                        end=r["end"],
                        score=r["score"],
                        text=r["text"],
                    ))
                if gliner_results:
                    logger.info("GLiNER: %d Entities erkannt.", len(gliner_results))
            except Exception as e:
                logger.warning("GLiNER Fehler: %s", e)

        # Layer 2: Presidio + SpaCy + Custom Recognizers
        from .detector import detect
        combined_deny = list(deny_list or [])

        # Layer 3: LLM-based detection (optional)
        if self._use_llm_detector:
            try:
                from .llm_detector import detect_with_llm
                llm_terms = detect_with_llm(text, self._llm_method, self._llm_model)
                if llm_terms:
                    combined_deny.extend(llm_terms)
                    logger.info("LLM Detector: %d zusaetzliche Begriffe.", len(llm_terms))
            except Exception as e:
                logger.debug("LLM Detector Fehler: %s", e)

        presidio_entities = detect(text, entity_types=entity_types, deny_list=combined_deny or None)
        all_entities.extend(presidio_entities)

        # Merge & deduplicate: resolve overlapping entities from different layers
        from .models import resolve_overlaps
        merged = resolve_overlaps(all_entities)

        anonymized_text, mappings = anonymize(text, merged)

        # Store in persistent mapping store
        session_id = None
        if mappings and self._mapping_store:
            session_id = self._mapping_store.create_session(mappings)

        return AnonymizeResult(
            anonymized_text=anonymized_text,
            mappings=mappings,
            entities=merged,
            session_id=session_id,
        )

    def rehydrate(self, text: str, mappings: dict[str, str]) -> str:
        """Restore original values in text using mappings."""
        from .rehydrator import rehydrate
        return rehydrate(text, mappings)

    def rehydrate_session(self, text: str, session_id: str) -> tuple[str, int]:
        """Restore original values using a stored session."""
        self._ensure_initialized()

        if not self._mapping_store:
            return text, 0

        mappings = self._mapping_store.get_session(session_id)
        if not mappings:
            return text, 0

        original = text
        restored = self.rehydrate(text, mappings)
        replacements = sum(
            1 for codename in mappings
            if codename in original or codename.lower() in original.lower()
        )
        return restored, replacements

    def get_latest_mappings(self) -> dict[str, str] | None:
        """Get mappings from the most recent session (for CLI deanon)."""
        if not self._mapping_store:
            return None
        result = self._mapping_store.get_latest_session()
        return result[1] if result else None

    # --- Memory Layer ---

    def remember(self, anonymized_prompt: str, anonymized_response: str, **metadata) -> str | None:
        """Store an anonymized conversation in long-term memory."""
        self._ensure_initialized()
        if not self._memory:
            return None
        return self._memory.store(anonymized_prompt, anonymized_response, metadata or None)

    def recall(self, anonymized_prompt: str) -> list[str]:
        """Retrieve relevant context from memory for a new prompt."""
        self._ensure_initialized()
        if not self._memory:
            return []
        return self._memory.retrieve(anonymized_prompt)

    def build_context_prompt(self, anonymized_prompt: str) -> str:
        """Enhance a prompt with relevant context from memory."""
        self._ensure_initialized()
        if not self._memory:
            return anonymized_prompt
        return self._memory.build_context_prompt(anonymized_prompt)

    def memory_count(self) -> int:
        """Number of stored memory entries."""
        if not self._memory:
            return 0
        try:
            return self._memory.count()
        except Exception:
            return 0

    def memory_clear(self) -> int:
        """Clear all stored memories."""
        if not self._memory:
            return 0
        return self._memory.clear()


def get_engine(**kwargs) -> PrivacyEngine:
    """Get or create the singleton PrivacyEngine."""
    global _engine
    if _engine is None:
        _engine = PrivacyEngine(**kwargs)
    return _engine

CONFIDENCE_THRESHOLD = 0.6

"""PII detection service using Presidio Analyzer with SpaCy NLP backend."""

import html
import logging
import re

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider


from .models import Entity
from .austrian_recognizers import get_all_austrian_recognizers

logger = logging.getLogger(__name__)

# Color mapping for entity types in annotated HTML
ENTITY_COLORS: dict[str, str] = {
    "PERSON": "#3b82f6",            # blue
    "AT_IBAN": "#22c55e",           # green
    "IBAN_CODE": "#22c55e",         # green
    "PHONE_NUMBER": "#f97316",      # orange
    "AT_UID_NR": "#a855f7",         # purple
    "AT_SVNR": "#ef4444",           # red
    "AT_FIRMENBUCH_NR": "#ec4899",  # pink
    "LOCATION": "#14b8a6",          # teal
    "DATE_TIME": "#eab308",         # yellow
    "EMAIL_ADDRESS": "#6366f1",     # indigo
    "ORGANIZATION": "#06b6d4",      # cyan
    "NRP": "#84cc16",               # lime
    "CREDIT_CARD": "#f43f5e",       # rose
    "DOC_METADATA": "#d946ef",      # fuchsia
}

DEFAULT_COLOR = "#9ca3af"  # gray fallback

# Entity types that should actually be anonymized. Others (LOCATION, DATE_TIME,
# NRP, MISC) produce too many false positives on technical/business texts.
ALLOWED_ENTITY_TYPES = {
    "PERSON", "AT_IBAN", "IBAN_CODE", "PHONE_NUMBER", "AT_UID_NR",
    "AT_SVNR", "AT_FIRMENBUCH_NR", "EMAIL_ADDRESS", "DOC_METADATA",
    "ORGANIZATION", "ORG", "CREDIT_CARD", "CUSTOM", "CREDENTIAL",
    "EU_PII", "SENSITIVE_DATA",
}

# Known false-positive LOCATIONs to filter out
LOCATION_FALSE_POSITIVES = {
    "tel", "tel.", "dr", "dr.", "nr", "nr.", "str", "str.",
    "gmbh", "ag", "kg", "og", "e.u.", "eur", "usd", "chf",
    "bic", "iban", "svnr", "sv-nr", "uid", "fn",
    "mrt", "ct", "ekg",
}

# Module-level analyzer instance, initialized via init_analyzer()
_analyzer: AnalyzerEngine | None = None


def init_analyzer() -> AnalyzerEngine:
    """Initialize the Presidio AnalyzerEngine with SpaCy de_core_news_lg."""
    global _analyzer

    logger.info("Initialisiere Presidio AnalyzerEngine mit SpaCy de_core_news_lg...")

    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "de", "model_name": "de_core_news_lg"},
        ],
    }

    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()

    _analyzer = AnalyzerEngine(
        nlp_engine=nlp_engine,
        supported_languages=["de"],
    )

    # Register all Austrian custom recognizers
    for recognizer in get_all_austrian_recognizers():
        _analyzer.registry.add_recognizer(recognizer)
        logger.info("Registriert: %s", recognizer.name)

    logger.info("AnalyzerEngine erfolgreich initialisiert.")
    return _analyzer


def get_analyzer() -> AnalyzerEngine:
    """Get the initialized analyzer instance."""
    if _analyzer is None:
        raise RuntimeError("AnalyzerEngine wurde noch nicht initialisiert.")
    return _analyzer


def get_spacy_nlp():
    """Get the SpaCy nlp model from the Presidio analyzer engine.

    Reuses the model already loaded by Presidio — no extra RAM needed.
    """
    analyzer = get_analyzer()
    try:
        return analyzer.nlp_engine.nlp["de"]
    except (AttributeError, KeyError):
        # Fallback: load model directly (costs extra RAM)
        import spacy
        return spacy.load("de_core_news_lg")


def detect(
    text: str,
    language: str = "de",
    entity_types: list[str] | None = None,
    deny_list: list[str] | None = None,
) -> list[Entity]:
    """Detect PII entities using two-pass detection with context learning.

    Phase 1: Standard Presidio detection (rule-based + NER).
    Phase 2: Context Learner analyzes Phase 1 results, finds additional
             identifying terms via PROPN tags, NER re-check, and embedding
             similarity. Re-runs Presidio with expanded deny_list.

    Args:
        text: Input text to analyze.
        language: Language code (default "de").
        entity_types: Optional list of entity types to detect.
        deny_list: Optional list of additional words/phrases to detect as PII.

    Returns:
        List of detected Entity objects filtered by confidence threshold.
    """
    # Phase 1: Standard Presidio detection
    entities = _detect_once(text, language, entity_types, deny_list)

    # Phase 2: Context learning — find additional identifying terms
    if entities:
        try:
            from .context_learner import learn_document
            nlp = get_spacy_nlp()
            additional_terms = learn_document(text, entities, nlp)

            if additional_terms:
                # Re-run Presidio with expanded deny_list
                expanded_deny = list(deny_list or []) + additional_terms
                entities = _detect_once(text, language, entity_types, expanded_deny)
                logger.info(
                    "Zwei-Pass-Erkennung: %d zusaetzliche Begriffe, %d Entities gesamt.",
                    len(additional_terms), len(entities),
                )
        except Exception as e:
            logger.warning("Context-Learner fehlgeschlagen: %s", e)

    return entities


def _detect_once(
    text: str,
    language: str = "de",
    entity_types: list[str] | None = None,
    deny_list: list[str] | None = None,
) -> list[Entity]:
    """Single-pass Presidio detection (internal helper)."""
    analyzer = get_analyzer()

    # Merge persistent custom terms with per-request deny_list
    merged_deny_list: list[str] = []
    # Custom terms are passed in via deny_list parameter
    if deny_list:
        merged_deny_list.extend(deny_list)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_deny: list[str] = []
    for term in merged_deny_list:
        if term not in seen:
            seen.add(term)
            unique_deny.append(term)

    # If custom deny_list provided, create a temporary recognizer
    ad_hoc_recognizers = None
    if unique_deny:
        from presidio_analyzer import PatternRecognizer
        deny_recognizer = PatternRecognizer(
            supported_entity="CUSTOM",
            deny_list=unique_deny,
            name="Custom Deny List",
            supported_language=language,
        )
        ad_hoc_recognizers = [deny_recognizer]

    results = analyzer.analyze(
        text=text,
        language=language,
        entities=entity_types,
        ad_hoc_recognizers=ad_hoc_recognizers,
    )

    entities: list[Entity] = []
    for result in results:
        if result.score >= CONFIDENCE_THRESHOLD:
            entity_text = text[result.start : result.end]

            # Only keep entity types we actually want to anonymize
            if result.entity_type not in ALLOWED_ENTITY_TYPES:
                continue

            # Filter false-positive LOCATIONs
            if result.entity_type == "LOCATION":
                if entity_text.strip().lower() in LOCATION_FALSE_POSITIVES:
                    continue
                if len(entity_text.strip()) <= 2:
                    continue

            entities.append(
                Entity(
                    entity_type=result.entity_type,
                    start=result.start,
                    end=result.end,
                    score=result.score,
                    text=entity_text,
                )
            )

    # Sort by start position
    entities.sort(key=lambda e: e.start)

    # Remove entities that are fully contained within a higher-scored entity
    entities = _remove_contained(entities)

    return entities


def generate_annotated_html(text: str, entities: list[Entity]) -> str:
    """Generate HTML with colored <mark> spans for each detected entity."""
    if not entities:
        return html.escape(text)

    # Remove overlapping entities: keep the one with higher score
    filtered = _resolve_overlaps(entities)

    filtered.sort(key=lambda e: e.start)

    parts: list[str] = []
    last_end = 0

    for entity in filtered:
        # Add text before this entity
        parts.append(html.escape(text[last_end : entity.start]))

        # Add the marked entity
        color = ENTITY_COLORS.get(entity.entity_type, DEFAULT_COLOR)
        entity_text = html.escape(text[entity.start : entity.end])
        parts.append(
            f'<mark style="background-color: {color}20; border: 1px solid {color}; '
            f'border-radius: 3px; padding: 1px 4px;" '
            f'data-entity="{html.escape(entity.entity_type)}" '
            f'title="{html.escape(entity.entity_type)} ({entity.score:.0%})">'
            f"{entity_text}</mark>"
        )
        last_end = entity.end

    # Add remaining text after last entity
    parts.append(html.escape(text[last_end:]))

    return "".join(parts)


def _remove_contained(entities: list[Entity]) -> list[Entity]:
    """Remove entities that are fully contained within a higher-scored entity."""
    if len(entities) <= 1:
        return entities

    result = []
    for i, ent in enumerate(entities):
        is_contained = False
        for j, other in enumerate(entities):
            if i == j:
                continue
            # Check if ent is fully inside other AND other has higher/equal score
            if (other.start <= ent.start and ent.end <= other.end
                    and other.score >= ent.score
                    and (other.end - other.start) > (ent.end - ent.start)):
                is_contained = True
                break
        if not is_contained:
            result.append(ent)
    return result


def _resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """Remove overlapping entities, keeping the one with the highest score.

    When two entities overlap:
    - Prefer the one with higher score
    - On equal score, prefer the longer span (more specific match)
    """
    if not entities:
        return []

    # Sort by score descending, then by span length descending
    sorted_entities = sorted(entities, key=lambda e: (-e.score, -(e.end - e.start)))

    selected: list[Entity] = []
    occupied: list[tuple[int, int]] = []

    for entity in sorted_entities:
        overlaps = False
        for start, end in occupied:
            if entity.start < end and entity.end > start:
                overlaps = True
                break
        if not overlaps:
            selected.append(entity)
            occupied.append((entity.start, entity.end))

    # Sort by start position for output
    selected.sort(key=lambda e: e.start)
    return selected

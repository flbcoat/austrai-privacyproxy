"""PII detection service using Presidio Analyzer with SpaCy NLP backend."""

import html
import logging

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from app.config import settings
from app.models import Entity
from app.services.austrian_recognizers import get_all_austrian_recognizers

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
}

DEFAULT_COLOR = "#9ca3af"  # gray fallback

# Module-level analyzer instance, initialized via init_analyzer()
_analyzer: AnalyzerEngine | None = None


def init_analyzer() -> AnalyzerEngine:
    """Initialize the Presidio AnalyzerEngine with SpaCy de_core_news_lg.

    This should be called once at application startup.
    """
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
        raise RuntimeError("AnalyzerEngine wurde noch nicht initialisiert. Bitte init_analyzer() aufrufen.")
    return _analyzer


def detect(text: str, language: str = "de") -> list[Entity]:
    """Detect PII entities in the given text.

    Args:
        text: Input text to analyze.
        language: Language code (default "de" for German).

    Returns:
        List of detected Entity objects filtered by confidence threshold.
    """
    analyzer = get_analyzer()

    results = analyzer.analyze(
        text=text,
        language=language,
        entities=None,  # detect all supported entities
    )

    entities: list[Entity] = []
    for result in results:
        if result.score >= settings.CONFIDENCE_THRESHOLD:
            entities.append(
                Entity(
                    entity_type=result.entity_type,
                    start=result.start,
                    end=result.end,
                    score=result.score,
                    text=text[result.start : result.end],
                )
            )

    # Sort by start position
    entities.sort(key=lambda e: e.start)

    return entities


def generate_annotated_html(text: str, entities: list[Entity]) -> str:
    """Generate HTML with colored <mark> spans for each detected entity.

    Args:
        text: Original input text.
        entities: List of detected entities.

    Returns:
        HTML string with entity annotations.
    """
    if not entities:
        return html.escape(text)

    # Remove overlapping entities: keep the one with higher score
    filtered = _resolve_overlaps(entities)

    # Sort by start position descending so we can replace from the end
    filtered.sort(key=lambda e: e.start, reverse=True)

    # Work on the text as a list for efficient manipulation
    result = html.escape(text)

    # We need to map positions from original text to escaped text
    # Instead, build the result by iterating forward through non-overlapping entities
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


def _resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """Remove overlapping entities, keeping the one with the highest score.

    Args:
        entities: List of entities, possibly overlapping.

    Returns:
        List of non-overlapping entities.
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

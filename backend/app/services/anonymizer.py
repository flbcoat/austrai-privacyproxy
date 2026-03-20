"""Anonymization service: replaces PII entities with numbered placeholders."""

from app.models import Entity


def anonymize(text: str, entities: list[Entity]) -> tuple[str, dict[str, str]]:
    """Anonymize text by replacing entities with typed placeholders.

    Creates placeholders like [PERSON_1], [AT_IBAN_1], etc.
    Handles overlapping entities by keeping the one with the highest score.
    Processes entities from end to start to preserve character positions.

    Args:
        text: Original input text.
        entities: List of detected entities.

    Returns:
        Tuple of (anonymized_text, mappings) where mappings is
        {placeholder: original_text}.
    """
    if not entities:
        return text, {}

    # Resolve overlapping entities: keep highest score
    resolved = _resolve_overlaps(entities)

    # Track counters per entity type
    type_counters: dict[str, int] = {}

    # First pass: assign placeholders in forward order (for consistent numbering)
    entity_placeholders: list[tuple[Entity, str]] = []
    for entity in resolved:
        entity_type = entity.entity_type
        if entity_type not in type_counters:
            type_counters[entity_type] = 0
        type_counters[entity_type] += 1
        placeholder = f"[{entity_type}_{type_counters[entity_type]}]"
        entity_placeholders.append((entity, placeholder))

    # Build mappings
    mappings: dict[str, str] = {}
    for entity, placeholder in entity_placeholders:
        original_text = text[entity.start : entity.end]
        mappings[placeholder] = original_text

    # Process replacements from end to start to preserve positions
    anonymized = text
    for entity, placeholder in reversed(entity_placeholders):
        anonymized = anonymized[: entity.start] + placeholder + anonymized[entity.end :]

    return anonymized, mappings


def _resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """Remove overlapping entities, keeping the one with the highest score.

    Args:
        entities: List of entities, possibly overlapping.

    Returns:
        List of non-overlapping entities sorted by start position.
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

    # Sort by start position for consistent processing
    selected.sort(key=lambda e: e.start)
    return selected

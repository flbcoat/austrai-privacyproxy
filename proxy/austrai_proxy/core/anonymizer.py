"""Anonymization service with codename-based obfuscation.

Replaces PII entities with abstract fictional codenames (for semantic types
like PERSON, ORG) or bracket references (for structured data like IBANs).

Codenames are:
- Not reversible (no language to translate back from, not real names)
- LLM-friendly (look like proper nouns, processed naturally by the LLM)
- Consistent within a session (same input -> same codename)
- Meaningless without the local mapping table

On the foreign LLM server, a text like:
  "Thomas Gruber arbeitet bei Innovatech GmbH, IBAN AT48 3200..."
becomes:
  "Arion arbeitet bei Nexon Corp, IBAN [AT_IBAN_1]..."

A human reading the server logs sees a story about "Arion at Nexon Corp" —
useless without the mapping. And unlike foreign-language fakes, codenames
can't be translated back by an LLM.
"""

from .models import Entity, resolve_overlaps
from .codename_engine import CodeNameEngine


def anonymize(text: str, entities: list[Entity]) -> tuple[str, dict[str, str]]:
    """Anonymize text by replacing entities with codenames or bracket references.

    Args:
        text: Original input text.
        entities: List of detected entities.

    Returns:
        Tuple of (anonymized_text, mappings) where mappings is
        {codename: original_text}.
    """
    if not entities:
        return text, {}

    resolved = resolve_overlaps(entities)
    engine = CodeNameEngine()

    entity_replacements: list[tuple[Entity, str]] = []
    for entity in resolved:
        original = text[entity.start : entity.end]
        codename = engine.get_codename(entity.entity_type, original)
        entity_replacements.append((entity, codename))

    # Build mappings: codename -> original_text
    mappings: dict[str, str] = {}
    for entity, codename in entity_replacements:
        original = text[entity.start : entity.end]
        mappings[codename] = original

    # Replace from end to start to preserve character positions
    anonymized = text
    for entity, codename in reversed(entity_replacements):
        anonymized = anonymized[: entity.start] + codename + anonymized[entity.end :]

    return anonymized, mappings

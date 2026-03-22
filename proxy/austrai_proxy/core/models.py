"""Core data models for AUSTR.AI."""

from pydantic import BaseModel, Field


class Entity(BaseModel):
    """A single detected PII entity."""

    entity_type: str = Field(..., description="Entity type (e.g. PERSON, AT_IBAN)")
    start: int = Field(..., description="Start position in text")
    end: int = Field(..., description="End position in text")
    score: float = Field(..., description="Detection confidence (0-1)")
    text: str = Field(..., description="The detected text")


def resolve_overlaps(entities: list[Entity]) -> list[Entity]:
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

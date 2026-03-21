"""Core data models for AUSTR.AI."""

from pydantic import BaseModel, Field


class Entity(BaseModel):
    """A single detected PII entity."""

    entity_type: str = Field(..., description="Entity type (e.g. PERSON, AT_IBAN)")
    start: int = Field(..., description="Start position in text")
    end: int = Field(..., description="End position in text")
    score: float = Field(..., description="Detection confidence (0-1)")
    text: str = Field(..., description="The detected text")

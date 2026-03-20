from pydantic import BaseModel, Field


class TextRequest(BaseModel):
    """Request model for text input."""

    text: str = Field(..., max_length=2000, description="Eingabetext zur Analyse")


class Entity(BaseModel):
    """A single detected PII entity."""

    entity_type: str = Field(..., description="Typ der erkannten Entität (z.B. PERSON, AT_IBAN)")
    start: int = Field(..., description="Startposition im Text")
    end: int = Field(..., description="Endposition im Text")
    score: float = Field(..., description="Konfidenzwert der Erkennung (0-1)")
    text: str = Field(..., description="Der erkannte Text")


class AnalyzeResponse(BaseModel):
    """Response for the /api/analyze endpoint."""

    entities: list[Entity] = Field(default_factory=list, description="Liste erkannter Entitäten")
    annotated_html: str = Field(..., description="HTML mit farbigen Markierungen")


class AnonymizeResponse(BaseModel):
    """Response for the /api/anonymize endpoint."""

    anonymized_text: str = Field(..., description="Anonymisierter Text mit Platzhaltern")
    mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Zuordnung Platzhalter → Originaltext",
    )
    session_id: str = Field(..., description="Session-ID für spätere Rehydrierung")


class ProcessRequest(BaseModel):
    """Request model for the full pipeline."""

    text: str = Field(..., max_length=2000, description="Eingabetext")
    prompt: str = Field(
        default="Beantworte diese Nachricht professionell und hilfsbereit auf Deutsch.",
        description="Anweisung für das Sprachmodell",
    )


class ProcessResponse(BaseModel):
    """Response for the full /api/process pipeline."""

    original_text: str = Field(..., description="Originaltext")
    entities: list[Entity] = Field(default_factory=list, description="Erkannte Entitäten")
    annotated_html: str = Field(..., description="HTML mit farbigen Markierungen")
    anonymized_text: str = Field(..., description="Anonymisierter Text")
    mappings: dict[str, str] = Field(default_factory=dict, description="Platzhalter-Zuordnungen")
    llm_response_anonymized: str = Field(..., description="LLM-Antwort (anonymisiert)")
    llm_response_rehydrated: str = Field(..., description="LLM-Antwort (rehydriert)")
    session_id: str = Field(..., description="Session-ID")


class HealthResponse(BaseModel):
    """Response for the /api/health endpoint."""

    status: str = Field(..., description="Service-Status")
    version: str = Field(..., description="API-Version")

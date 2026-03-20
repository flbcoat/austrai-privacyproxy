from pydantic import BaseModel, Field


class TextRequest(BaseModel):
    """Request model for text input."""

    text: str = Field(..., max_length=2000, description="Eingabetext zur Analyse")
    entity_types: list[str] | None = Field(
        default=None,
        description="Optionale Liste von Entity-Typen die erkannt werden sollen (z.B. ['PERSON', 'AT_IBAN']). Wenn leer: alle Typen.",
    )
    deny_list: list[str] | None = Field(
        default=None,
        description="Optionale Liste zusätzlicher Begriffe die als PII erkannt werden sollen (z.B. Firmennamen, Projektnamen).",
    )


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
    entity_types: list[str] | None = Field(
        default=None,
        description="Optionale Liste von Entity-Typen (z.B. ['PERSON', 'AT_IBAN']). Wenn leer: alle Typen.",
    )
    deny_list: list[str] | None = Field(
        default=None,
        description="Optionale Liste zusätzlicher Begriffe die als PII erkannt werden sollen.",
    )


class SensitivityFlag(BaseModel):
    """Ein einzelnes Sensitivity-Finding im Text."""

    category: str = Field(..., description="Kategorie (z.B. ARCHITECTURE, CREDENTIALS)")
    label: str = Field(..., description="Menschenlesbare Bezeichnung (z.B. Softwarearchitektur & Systemdesign)")
    score: float = Field(..., description="Aehnlichkeitswert (0-1)")
    excerpt: str = Field(..., description="Betroffener Textausschnitt (max. 200 Zeichen)")


class SensitivityReport(BaseModel):
    """Ergebnis der Inhalts-Sensitivitaetsanalyse."""

    is_sensitive: bool = Field(..., description="True wenn sensible Inhalte erkannt wurden")
    risk_level: str = Field(..., description="Risikostufe: low, medium, high")
    flags: list[SensitivityFlag] = Field(default_factory=list, description="Erkannte Sensitivity-Flags")
    summary: str = Field(..., description="Menschenlesbare Zusammenfassung auf Deutsch")


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
    sensitivity: SensitivityReport | None = Field(
        default=None,
        description="Ergebnis der Inhalts-Sensitivitaetsanalyse (optional)",
    )
    local_summary: str | None = Field(
        default=None,
        description="Lokale datenschutzkonforme Zusammenfassung (nur bei hohem Risiko und verfuegbarem lokalem LLM)",
    )


class UploadResponse(BaseModel):
    """Response for the /api/upload endpoint — includes file metadata and full pipeline results."""

    # Datei-Metadaten
    filename: str = Field(..., description="Name der hochgeladenen Datei")
    format: str = Field(..., description="Erkanntes Dateiformat (PDF, DOCX, XLSX, TEXT, IMAGE)")
    pages: int = Field(..., description="Anzahl der Seiten/Blaetter")
    file_size_bytes: int = Field(..., description="Dateigroesse in Bytes")
    extracted_text: str = Field(..., description="Extrahierter Rohtext aus der Datei")
    metadata_warnings: list[str] = Field(
        default_factory=list,
        description="Warnungen zu EXIF-Metadaten, Verschluesselung, etc.",
    )

    # Pipeline-Ergebnisse (identisch zu ProcessResponse)
    original_text: str = Field(..., description="Originaltext (= extrahierter Text)")
    entities: list[Entity] = Field(default_factory=list, description="Erkannte Entitaeten")
    annotated_html: str = Field(..., description="HTML mit farbigen Markierungen")
    anonymized_text: str = Field(..., description="Anonymisierter Text")
    mappings: dict[str, str] = Field(default_factory=dict, description="Platzhalter-Zuordnungen")
    llm_response_anonymized: str = Field(..., description="LLM-Antwort (anonymisiert)")
    llm_response_rehydrated: str = Field(..., description="LLM-Antwort (rehydriert)")
    session_id: str = Field(..., description="Session-ID")
    sensitivity: SensitivityReport | None = Field(
        default=None,
        description="Ergebnis der Inhalts-Sensitivitaetsanalyse (optional)",
    )
    local_summary: str | None = Field(
        default=None,
        description="Lokale datenschutzkonforme Zusammenfassung (nur bei hohem Risiko und verfuegbarem lokalem LLM)",
    )


class HealthResponse(BaseModel):
    """Response for the /api/health endpoint."""

    status: str = Field(..., description="Service-Status")
    version: str = Field(..., description="API-Version")

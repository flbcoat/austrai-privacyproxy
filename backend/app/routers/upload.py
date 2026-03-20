"""Datei-Upload-Endpoint fuer Dokument- und Bildverarbeitung."""

import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.models import Entity, UploadResponse
from app.services.anonymizer import anonymize
from app.services.detector import detect, generate_annotated_html
from app.services.extractor import MAX_FILE_SIZE, extract_text
from app.services.llm_client import call_llm
from app.services.rate_limiter import rate_limiter
from app.services.rehydrator import rehydrate
from app.services.sensitivity_analyzer import analyze_sensitivity
from app.services.session_store import session_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/upload", response_model=UploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="Datei zum Hochladen (max. 10 MB)"),
    prompt: str = Form(
        default="Beantworte diese Nachricht professionell und hilfsbereit auf Deutsch.",
        description="Anweisung fuer das Sprachmodell",
    ),
    deny_list: str = Form(
        default="",
        description="Zusaetzliche Begriffe die als PII erkannt werden sollen (zeilenweise getrennt)",
    ),
) -> UploadResponse:
    """Verarbeitet eine hochgeladene Datei durch die komplette PrivacyProxy-Pipeline.

    Schritte:
    1. Datei validieren (Groesse, Format)
    2. Text extrahieren (PDF, DOCX, XLSX, TXT, Bild-OCR)
    3. PII-Entitaeten erkennen
    4. Text anonymisieren
    5. Anonymisierten Text an LLM senden
    6. LLM-Antwort rehydrieren

    Args:
        request: HTTP-Request (fuer IP-basiertes Rate-Limiting).
        file: Die hochgeladene Datei.
        prompt: Optionale Anweisung fuer das Sprachmodell.
        deny_list: Optionale zusaetzliche PII-Begriffe (zeilenweise getrennt).

    Returns:
        UploadResponse mit Extraktionsergebnis und Pipeline-Resultaten.
    """
    # Rate-Limiting pruefen
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    # Dateiname validieren
    filename = file.filename or "unknown"

    # Datei lesen und Groesse pruefen
    try:
        file_bytes = await file.read()
    except Exception as e:
        logger.error("Fehler beim Lesen der hochgeladenen Datei: %s", e)
        raise HTTPException(
            status_code=400,
            detail=f"Datei konnte nicht gelesen werden: {type(e).__name__}",
        )

    file_size = len(file_bytes)

    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Datei ist zu gross ({size_mb:.1f} MB). Maximale Groesse: 10 MB.",
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Die hochgeladene Datei ist leer.")

    # Schritt 1: Text extrahieren
    try:
        extracted = extract_text(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=file.content_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not extracted.text.strip():
        raise HTTPException(
            status_code=422,
            detail="Aus der Datei konnte kein Text extrahiert werden.",
        )

    # Deny-List parsen (zeilenweise getrennt)
    parsed_deny_list: list[str] | None = None
    if deny_list.strip():
        parsed_deny_list = [
            term.strip()
            for term in deny_list.strip().split("\n")
            if term.strip()
        ]

    # Schritt 1b: Sensitivity-Analyse
    sensitivity_report = analyze_sensitivity(extracted.text)

    # Schritt 2: PII-Entitaeten erkennen
    entities: list[Entity] = detect(
        extracted.text,
        deny_list=parsed_deny_list,
    )

    # Schritt 3: Annotiertes HTML generieren
    annotated_html = generate_annotated_html(extracted.text, entities)

    # Schritt 4: Text anonymisieren
    anonymized_text, mappings = anonymize(extracted.text, entities)

    # Schritt 5: Session erstellen
    session_id = session_store.create_session(mappings)

    # Schritt 6: LLM-Aufruf mit anonymisiertem Text
    llm_response_anonymized = await call_llm(anonymized_text, prompt)

    # Schritt 7: LLM-Antwort rehydrieren
    llm_response_rehydrated = rehydrate(llm_response_anonymized, mappings)

    logger.info(
        "Upload-Pipeline abgeschlossen: datei=%s, format=%s, seiten=%d, "
        "groesse=%d bytes, entitaeten=%d",
        filename,
        extracted.format,
        extracted.pages,
        file_size,
        len(entities),
    )

    return UploadResponse(
        filename=filename,
        format=extracted.format,
        pages=extracted.pages,
        file_size_bytes=file_size,
        extracted_text=extracted.text,
        metadata_warnings=extracted.warnings,
        original_text=extracted.text,
        entities=entities,
        annotated_html=annotated_html,
        anonymized_text=anonymized_text,
        mappings=mappings,
        llm_response_anonymized=llm_response_anonymized,
        llm_response_rehydrated=llm_response_rehydrated,
        session_id=session_id,
        sensitivity=sensitivity_report,
    )

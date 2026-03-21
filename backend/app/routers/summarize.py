"""Lokaler Zusammenfassungs-Endpoint: Erzeugt datenschutzkonforme Zusammenfassungen
ohne externen API-Aufruf.

Strategie: Erst PII anonymisieren (Presidio), dann optional lokales LLM
fuer eine kuerzere Zusammenfassung. Die Anonymisierung allein ist bereits
ein sicheres Ergebnis.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import TextRequest
from app.services.detector import detect
from app.services.anonymizer import anonymize
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter()


class SummarizeResponse(BaseModel):
    """Response fuer den /api/summarize Endpoint."""

    summary: str = Field(..., description="Anonymisierte Version des Textes")
    document_type: str = Field(..., description="Erkannter Dokumenttyp")
    entities_removed: int = Field(..., description="Anzahl anonymisierter Entitaeten")


@router.post("/api/summarize", response_model=SummarizeResponse)
async def summarize_text(request: Request, body: TextRequest) -> SummarizeResponse:
    """Erzeugt eine datenschutzkonforme, anonymisierte Version des Textes.

    Entfernt alle erkannten PII-Entitaeten und ersetzt sie durch Platzhalter.
    Klassifiziert den Dokumenttyp lokal. Kein externer API-Aufruf.
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    # PII erkennen und anonymisieren
    entities = detect(body.text, deny_list=body.deny_list if hasattr(body, 'deny_list') else None)
    anonymized_text, mappings = anonymize(body.text, entities)

    # Dokumenttyp lokal klassifizieren
    doc_type = "sonstiges"
    try:
        from app.services.local_llm import classify_document, is_available
        if is_available():
            doc_type = classify_document(body.text)
    except Exception:
        pass

    logger.info(
        "Lokale Zusammenfassung: %d Entitaeten entfernt, dokumenttyp=%s",
        len(entities), doc_type,
    )

    return SummarizeResponse(
        summary=anonymized_text,
        document_type=doc_type,
        entities_removed=len(entities),
    )

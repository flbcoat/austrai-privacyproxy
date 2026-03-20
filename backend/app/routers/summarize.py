"""Lokaler Zusammenfassungs-Endpoint: Erzeugt datenschutzkonforme Zusammenfassungen
ohne externen API-Aufruf.

Verwendet das lokale LLM (Qwen2.5-0.5B-Instruct) fuer:
- Textzusammenfassung mit Entfernung aller personenbezogenen Daten
- Dokumenttyp-Klassifikation
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import TextRequest
from app.services.local_llm import classify_document, is_available, summarize_locally
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter()


class SummarizeResponse(BaseModel):
    """Response fuer den /api/summarize Endpoint."""

    summary: str = Field(..., description="Datenschutzkonforme Zusammenfassung des Textes")
    document_type: str = Field(..., description="Erkannter Dokumenttyp (brief, vertrag, medizinisch, etc.)")


@router.post("/api/summarize", response_model=SummarizeResponse)
async def summarize_text(request: Request, body: TextRequest) -> SummarizeResponse:
    """Erzeugt eine datenschutzkonforme Zusammenfassung mittels lokalem LLM.

    Die Zusammenfassung entfernt automatisch:
    - Alle Eigennamen (Personen, Firmen, Orte)
    - Zahlen, Betraege, Daten und Adressen
    - Spezifische Details

    Es wird NUR das lokale LLM verwendet — kein externer API-Aufruf.

    Args:
        request: HTTP-Request (fuer IP-basiertes Rate-Limiting).
        body: Der zu analysierende Text.

    Returns:
        SummarizeResponse mit Zusammenfassung und Dokumenttyp.

    Raises:
        HTTPException 503: Wenn das lokale LLM nicht verfuegbar ist.
        HTTPException 429: Bei Rate-Limit-Ueberschreitung.
    """
    # Rate-Limiting pruefen
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    # Pruefen ob lokales LLM verfuegbar ist
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Lokales LLM ist nicht verfuegbar. "
                "llama-cpp-python muss installiert sein, um diese Funktion zu nutzen."
            ),
        )

    # Zusammenfassung und Klassifikation ausfuehren
    try:
        summary = summarize_locally(body.text)
        document_type = classify_document(body.text)
    except RuntimeError as e:
        logger.error("Fehler beim lokalen LLM: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Fehler beim lokalen LLM: {e}",
        )

    logger.info(
        "Lokale Zusammenfassung erstellt: dokumenttyp=%s, eingabe_laenge=%d, zusammenfassung_laenge=%d",
        document_type,
        len(body.text),
        len(summary),
    )

    return SummarizeResponse(
        summary=summary,
        document_type=document_type,
    )

"""Sensitivity-Check-Endpoint: Analysiert Text auf inhaltliche Sensitivitaet.

Dieses Endpoint wird VOR dem eigentlichen /api/process aufgerufen,
um den Benutzer zu warnen, falls der Text sensible Inhalte enthaelt.
"""

from fastapi import APIRouter, HTTPException, Request

from app.models import SensitivityReport, TextRequest
from app.services.rate_limiter import rate_limiter
from app.services.sensitivity_analyzer import analyze_sensitivity

router = APIRouter()


@router.post("/api/sensitivity-check", response_model=SensitivityReport)
async def sensitivity_check(request: Request, body: TextRequest) -> SensitivityReport:
    """Prueft Text auf inhaltliche Sensitivitaet (Pre-Check vor LLM-Aufruf).

    Analysiert den Text lokal mittels Sentence Embeddings auf:
    - Geschaeftsgeheimnisse
    - Softwarearchitektur-Details
    - Zugangsdaten / Credentials
    - Finanzdaten
    - Rechtliche Dokumente
    - Personalinterna
    - Medizinische Daten

    Args:
        request: HTTP-Request (fuer IP-basiertes Rate-Limiting).
        body: Der zu analysierende Text.

    Returns:
        SensitivityReport mit Flags, Risikostufe und Zusammenfassung.
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    return analyze_sensitivity(body.text)

"""Analyze endpoint: detect PII entities in text."""

from fastapi import APIRouter, HTTPException, Request

from app.models import AnalyzeResponse, TextRequest
from app.services.detector import detect, generate_annotated_html
from app.services.rate_limiter import rate_limiter

router = APIRouter()


@router.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_text(request: Request, body: TextRequest) -> AnalyzeResponse:
    """Analyze text for PII entities and return annotated HTML.

    Args:
        request: The incoming HTTP request (for IP extraction).
        body: The text to analyze.

    Returns:
        Detected entities and annotated HTML.
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    entities = detect(body.text)
    annotated_html = generate_annotated_html(body.text, entities)

    return AnalyzeResponse(
        entities=entities,
        annotated_html=annotated_html,
    )

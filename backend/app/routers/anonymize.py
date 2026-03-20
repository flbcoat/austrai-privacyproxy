"""Anonymize endpoint: detect and replace PII with placeholders."""

from fastapi import APIRouter, HTTPException, Request

from app.models import AnonymizeResponse, TextRequest
from app.services.anonymizer import anonymize
from app.services.detector import detect
from app.services.rate_limiter import rate_limiter
from app.services.session_store import session_store

router = APIRouter()


@router.post("/api/anonymize", response_model=AnonymizeResponse)
async def anonymize_text(request: Request, body: TextRequest) -> AnonymizeResponse:
    """Anonymize text by detecting PII and replacing it with placeholders.

    Args:
        request: The incoming HTTP request (for IP extraction).
        body: The text to anonymize.

    Returns:
        Anonymized text, mappings, and a session ID.
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    entities = detect(body.text, entity_types=body.entity_types, deny_list=body.deny_list)
    anonymized_text, mappings = anonymize(body.text, entities)
    session_id = session_store.create_session(mappings)

    return AnonymizeResponse(
        anonymized_text=anonymized_text,
        mappings=mappings,
        session_id=session_id,
    )

"""Rehydrate endpoint: restores original PII values from codenames using session mappings."""

import logging

from fastapi import APIRouter, HTTPException

from app.models import RehydrateRequest, RehydrateResponse
from app.services.rehydrator import rehydrate
from app.services.session_store import session_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/rehydrate", response_model=RehydrateResponse)
async def rehydrate_text(body: RehydrateRequest) -> RehydrateResponse:
    """Restore original PII values in text using a stored session mapping.

    Requires a valid session_id from a previous /api/anonymize or /api/process call.
    Sessions expire after 30 minutes.
    """
    mappings = session_store.get_session(body.session_id)
    if mappings is None:
        raise HTTPException(
            status_code=404,
            detail="Session nicht gefunden oder abgelaufen. Sessions sind 30 Minuten gueltig.",
        )

    original_text = body.text
    rehydrated_text = rehydrate(body.text, mappings)

    # Count how many replacements were actually made
    replacements = sum(
        1 for codename in mappings
        if codename in original_text or codename.lower() in original_text.lower()
    )

    logger.info(
        "Rehydrierung: session=%s, %d Ersetzungen durchgefuehrt.",
        body.session_id[:8], replacements,
    )

    return RehydrateResponse(
        rehydrated_text=rehydrated_text,
        replacements_made=replacements,
    )

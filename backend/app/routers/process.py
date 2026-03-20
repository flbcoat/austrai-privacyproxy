"""Full pipeline endpoint: detect, anonymize, LLM call, rehydrate."""

from fastapi import APIRouter, HTTPException, Request

from app.models import ProcessRequest, ProcessResponse
from app.services.anonymizer import anonymize
from app.services.detector import detect, generate_annotated_html
from app.services.llm_client import call_llm
from app.services.local_llm import is_available as local_llm_available, summarize_locally
from app.services.rate_limiter import rate_limiter
from app.services.rehydrator import rehydrate
from app.services.sensitivity_analyzer import analyze_sensitivity
from app.services.session_store import session_store

logger = __import__("logging").getLogger(__name__)

router = APIRouter()


@router.post("/api/process", response_model=ProcessResponse)
async def process_text(request: Request, body: ProcessRequest) -> ProcessResponse:
    """Run the full PrivacyProxy pipeline.

    Steps:
    1. Detect PII entities
    2. Generate annotated HTML
    3. Anonymize text with placeholders
    4. Send anonymized text to LLM
    5. Rehydrate LLM response with original PII data

    Args:
        request: The incoming HTTP request (for IP extraction).
        body: Text and optional prompt.

    Returns:
        All intermediate results for demo visualization.
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    # Step 0: Sensitivity analysis
    sensitivity_report = analyze_sensitivity(body.text)

    # Step 1: Detect PII entities
    entities = detect(body.text, entity_types=body.entity_types, deny_list=body.deny_list)

    # Step 2: Generate annotated HTML
    annotated_html = generate_annotated_html(body.text, entities)

    # Step 3: Anonymize text
    anonymized_text, mappings = anonymize(body.text, entities)

    # Step 4: Create session for mapping storage
    session_id = session_store.create_session(mappings)

    # Step 5: Generate local summary for high-risk content (if local LLM available)
    local_summary: str | None = None
    if (
        sensitivity_report
        and sensitivity_report.risk_level == "high"
        and local_llm_available()
    ):
        try:
            local_summary = summarize_locally(body.text)
            logger.info("Lokale Zusammenfassung fuer hochsensiblen Text erstellt.")
        except Exception as e:
            logger.warning("Lokale Zusammenfassung fehlgeschlagen: %s", e)

    # Step 6: Call LLM with anonymized text
    llm_response_anonymized = await call_llm(anonymized_text, body.prompt)

    # Step 7: Rehydrate LLM response
    llm_response_rehydrated = rehydrate(llm_response_anonymized, mappings)

    return ProcessResponse(
        original_text=body.text,
        entities=entities,
        annotated_html=annotated_html,
        anonymized_text=anonymized_text,
        mappings=mappings,
        llm_response_anonymized=llm_response_anonymized,
        llm_response_rehydrated=llm_response_rehydrated,
        session_id=session_id,
        sensitivity=sensitivity_report,
        local_summary=local_summary,
    )

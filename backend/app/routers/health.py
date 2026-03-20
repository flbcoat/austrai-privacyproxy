"""Health check endpoint."""

from fastapi import APIRouter

from app.models import HealthResponse

router = APIRouter()

APP_VERSION = "1.0.0"


@router.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return the service health status and version."""
    return HealthResponse(status="ok", version=APP_VERSION)

"""FastAPI application for the AUSTR.AI PrivacyProxy backend."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.data.examples import EXAMPLES
from app.services.extractor import SUPPORTED_FORMATS
from app.routers import analyze, anonymize, health, process, sensitivity, upload
from app.services.detector import init_analyzer
from app.services.sensitivity_analyzer import init_sensitivity_model
from app.services.session_store import session_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _periodic_session_cleanup() -> None:
    """Background task to clean up expired sessions every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        removed = session_store.cleanup()
        if removed > 0:
            logger.info("Session-Cleanup: %d abgelaufene Sessions entfernt.", removed)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize resources at startup, clean up at shutdown."""
    # Startup
    logger.info("Starte AUSTR.AI PrivacyProxy Backend...")
    init_analyzer()
    logger.info("SpaCy-Modell und Presidio Analyzer geladen.")
    init_sensitivity_model()
    logger.info("Sensitivity-Modell geladen.")

    # Start periodic session cleanup task
    cleanup_task = asyncio.create_task(_periodic_session_cleanup())

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("AUSTR.AI PrivacyProxy Backend beendet.")


app = FastAPI(
    title="AUSTR.AI PrivacyProxy",
    description="Anonymisierungs-Proxy für LLM-Anfragen — Schützt personenbezogene Daten nach österreichischem/EU-Datenschutzrecht.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(analyze.router, tags=["Analyse"])
app.include_router(anonymize.router, tags=["Anonymisierung"])
app.include_router(process.router, tags=["Pipeline"])
app.include_router(upload.router, tags=["Upload"])
app.include_router(sensitivity.router, tags=["Sensitivitaet"])


@app.get("/api/examples")
async def get_examples() -> list[dict[str, str]]:
    """Return example texts for the demo interface."""
    return EXAMPLES


@app.get("/api/supported-formats")
async def get_supported_formats() -> list[dict[str, str]]:
    """Return the list of supported file formats for upload."""
    return SUPPORTED_FORMATS

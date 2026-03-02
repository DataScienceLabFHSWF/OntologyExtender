"""Health and status endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from ontology_hitl.api.schemas import ServiceHealth
from ontology_hitl.api.dependencies import get_fuseki_client, get_ollama_client

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/health", response_model=ServiceHealth)
async def health() -> ServiceHealth:
    """Check connectivity to Fuseki and Ollama."""
    fuseki_ok = "unknown"
    ollama_ok = "unknown"

    try:
        resp = get_fuseki_client().get("/$/ping")
        fuseki_ok = "ok" if resp.status_code == 200 else "error"
    except Exception:
        fuseki_ok = "error"

    try:
        resp = get_ollama_client().get("/api/tags")
        ollama_ok = "ok" if resp.status_code == 200 else "error"
    except Exception:
        ollama_ok = "error"

    overall = "ok" if fuseki_ok == "ok" and ollama_ok == "ok" else "degraded"
    return ServiceHealth(status=overall, fuseki=fuseki_ok, ollama=ollama_ok)

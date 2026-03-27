"""OntologyExtender FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    logger.info(
        "ontology_extender_api_starting",
        port=os.getenv("UVICORN_PORT", "8003"),
    )
    yield
    logger.info("ontology_extender_api_stopping")


app = FastAPI(
    title="OntologyExtender API",
    version="0.1.0",
    description="Ontology extension, browsing, and SHACL validation service.",
    lifespan=lifespan,
)

# CORS – allow platform frontend (Streamlit) and other local services
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and mount routers after app creation to avoid circular imports
def _setup_routes():
    """Lazy-load and mount all route modules."""
    from ontology_hitl.api.routes.status import router as status_router
    from ontology_hitl.api.routes.browse import router as browse_router
    from ontology_hitl.api.routes.extend import router as extend_router
    from ontology_hitl.api.routes.validate import router as validate_router

    app.include_router(status_router, prefix="/api/v1", tags=["status"])
    app.include_router(browse_router, prefix="/api/v1/ontology", tags=["browse"])
    app.include_router(extend_router, prefix="/api/v1", tags=["extend"])
    app.include_router(validate_router, prefix="/api/v1", tags=["validate"])


_setup_routes()


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"service": "ontology-extender", "docs": "/docs"}

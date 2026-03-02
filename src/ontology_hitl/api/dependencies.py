"""Dependency injection – lazy singletons for backend connections."""

from __future__ import annotations

import os
from functools import lru_cache

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ── Settings ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_settings() -> dict[str, str]:
    """Gather all env-based settings in one place."""
    return {
        "fuseki_url": os.getenv("HITL_FUSEKI_URL", "http://localhost:3030"),
        "fuseki_dataset": os.getenv("HITL_FUSEKI_DATASET", "kgbuilder"),
        "fuseki_staging": os.getenv("HITL_FUSEKI_STAGING_DATASET", "kgbuilder-staging"),
        "ollama_url": os.getenv("HITL_OLLAMA_URL", "http://localhost:11434"),
        "ollama_model": os.getenv("HITL_OLLAMA_MODEL", "qwen3:8b"),
        "kgbuilder_api_url": os.getenv("KGBUILDER_API_URL", "http://localhost:8001"),
    }


# ── Fuseki client ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_fuseki_client() -> httpx.Client:
    """HTTP client pre-configured for Fuseki SPARQL endpoint."""
    settings = get_settings()
    return httpx.Client(
        base_url=settings["fuseki_url"],
        timeout=30.0,
    )


def sparql_query(query: str, dataset: str | None = None) -> list[dict]:
    """Execute a SPARQL SELECT and return bindings as dicts."""
    settings = get_settings()
    ds = dataset or settings["fuseki_dataset"]
    client = get_fuseki_client()
    resp = client.post(
        f"/{ds}/sparql",
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
    )
    resp.raise_for_status()
    results = resp.json().get("results", {}).get("bindings", [])
    return [
        {k: v["value"] for k, v in row.items()}
        for row in results
    ]


def sparql_update(update: str, dataset: str | None = None) -> None:
    """Execute a SPARQL UPDATE (INSERT / DELETE)."""
    settings = get_settings()
    ds = dataset or settings["fuseki_dataset"]
    client = get_fuseki_client()
    resp = client.post(
        f"/{ds}/update",
        data={"update": update},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()


# ── Ollama / LLM client ─────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_ollama_client() -> httpx.Client:
    """HTTP client for Ollama API."""
    settings = get_settings()
    return httpx.Client(
        base_url=settings["ollama_url"],
        timeout=120.0,
    )


def llm_generate(prompt: str, system: str = "") -> str:
    """Call Ollama /api/generate and return the response text."""
    settings = get_settings()
    client = get_ollama_client()
    payload: dict = {
        "model": settings["ollama_model"],
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system
    resp = client.post("/api/generate", json=payload)
    resp.raise_for_status()
    return resp.json().get("response", "")


# ── Cross-service helpers ────────────────────────────────────────────────

def notify_kgbuilder_rebuild() -> bool:
    """Best-effort POST to KGBuilder to trigger a rebuild after ontology changes."""
    settings = get_settings()
    url = settings["kgbuilder_api_url"]
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{url}/api/v1/build", json={})
            return resp.status_code == 200
    except Exception:
        logger.warning("kgbuilder_rebuild_notify_failed", url=url)
        return False

"""Dependency injection – lazy singletons for backend connections."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

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


# ── Core config Settings (for AgentTeam) ────────────────────────────────

@lru_cache(maxsize=1)
def get_core_settings():
    """Return a core Settings instance (pydantic-settings) for agent/pipeline use."""
    from ontology_hitl.core.config import Settings

    return Settings()


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


# ── AgentTeam factory ────────────────────────────────────────────────────

def create_agent_team(
    document_context: str = "",
    output_dir: Path | None = None,
) -> "AgentTeam":
    """Create an AgentTeam configured from environment settings.

    This is the bridge between the lightweight API dependency layer
    and the full multi-agent debate system.
    """
    from ontology_hitl.agents.team import AgentTeam

    settings = get_core_settings()

    if output_dir is None:
        output_dir = Path(settings.iterations_dir) / "api_debates"

    team = AgentTeam(
        settings=settings,
        document_context=document_context,
        max_debate_rounds=2,
        output_dir=output_dir,
    )
    return team


def fetch_fuseki_hierarchy() -> str:
    """Fetch the current class hierarchy from Fuseki as a text summary.

    Returns a formatted string showing parent → child relationships
    that agents can use as context for hierarchy-aware debates.
    """
    try:
        rows = sparql_query("""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX owl:  <http://www.w3.org/2002/07/owl#>
            SELECT ?class ?label ?parent ?parentLabel WHERE {
                ?class a owl:Class .
                OPTIONAL { ?class rdfs:label ?label }
                OPTIONAL {
                    ?class rdfs:subClassOf ?parent .
                    ?parent a owl:Class .
                    OPTIONAL { ?parent rdfs:label ?parentLabel }
                }
            }
            ORDER BY ?parent ?class
        """)
    except Exception as e:
        logger.warning("hierarchy_fetch_failed", error=str(e))
        return "(Could not fetch current hierarchy from Fuseki)"

    if not rows:
        return "(No classes found in Fuseki)"

    lines: list[str] = []
    for row in rows:
        uri = row.get("class", "")
        label = row.get("label", uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1])
        parent_label = row.get("parentLabel", "")
        parent_uri = row.get("parent", "")
        if parent_uri:
            p_display = parent_label or parent_uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            lines.append(f"  {p_display} → {label}")
        else:
            lines.append(f"  {label} (root)")

    return "Current ontology hierarchy:\n" + "\n".join(lines)


def fetch_fuseki_class_labels() -> list[str]:
    """Fetch just the class labels from Fuseki for seed context."""
    try:
        rows = sparql_query("""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX owl:  <http://www.w3.org/2002/07/owl#>
            SELECT ?label WHERE {
                ?class a owl:Class .
                ?class rdfs:label ?label .
            }
        """)
        return [r["label"] for r in rows if "label" in r]
    except Exception:
        return []

"""Async Fuseki connector — reads ontology TBox via SPARQL.

Adapted from GraphQAAgent ``FusekiConnector``.  Provides class hierarchy
expansion, synonym lookup, and property queries used by the gap analyzer
and domain expert.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import OntologyClass, OntologyProperty

logger = structlog.get_logger(__name__)

_SPARQL_PREFIXES = """\
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
"""


class FusekiConnector:
    """Async client for the Fuseki SPARQL endpoint.

    Provides ontology TBox access — class labels, hierarchies, synonyms,
    and property domains/ranges.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        auth = None
        if self._settings.fuseki_user and self._settings.fuseki_password:
            auth = httpx.BasicAuth(self._settings.fuseki_user, self._settings.fuseki_password)
        self._client = httpx.AsyncClient(
            base_url=self._settings.fuseki_url,
            timeout=30.0,
            auth=auth,
        )
        try:
            resp = await self._client.get(f"/{self._settings.fuseki_dataset}")
            resp.raise_for_status()
            logger.info("fuseki.connected", url=self._settings.fuseki_url,
                        dataset=self._settings.fuseki_dataset)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("fuseki.dataset_not_found",
                               dataset=self._settings.fuseki_dataset)
            else:
                raise
        except Exception as exc:
            logger.error("fuseki.connect_failed", error=str(exc))
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            logger.info("fuseki.closed")

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Fuseki client not initialised — call connect() first.")
        return self._client

    # -- SPARQL queries -----------------------------------------------------

    async def query(self, sparql: str) -> list[dict[str, Any]]:
        """Execute a SPARQL SELECT and return bindings as dicts."""
        if self._client is None:
            logger.warning("fuseki.not_connected")
            return []
        try:
            if not sparql.strip().upper().startswith("PREFIX"):
                sparql = _SPARQL_PREFIXES + sparql
            resp = await self._client.post(
                f"/{self._settings.fuseki_dataset}/sparql",
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {k: v.get("value", "") for k, v in binding.items()}
                for binding in data.get("results", {}).get("bindings", [])
            ]
        except Exception as exc:
            logger.warning("fuseki.query_failed", error=str(exc))
            return []

    # -- ontology helpers ---------------------------------------------------

    async def get_all_classes(self) -> list[OntologyClass]:
        """Return all ``owl:Class`` instances with labels."""
        sparql = """
        SELECT DISTINCT ?class ?label WHERE {
            ?class a owl:Class .
            OPTIONAL { ?class rdfs:label ?label . }
        }
        ORDER BY ?class
        """
        rows = await self.query(sparql)
        results: list[OntologyClass] = []
        for r in rows:
            label = r.get("label", "")
            if not label:
                uri = r.get("class", "")
                label = uri.split("#")[-1].split("/")[-1]
            if label:
                results.append(OntologyClass(uri=r.get("class", ""), label=label))
        return results

    async def get_subclasses(self, class_uri: str) -> list[OntologyClass]:
        """Get all transitive subclasses of a given class."""
        sparql = f"""
        SELECT ?sub ?label WHERE {{
            ?sub rdfs:subClassOf* <{class_uri}> .
            ?sub rdfs:label ?label .
        }}
        """
        rows = await self.query(sparql)
        return [OntologyClass(uri=r["sub"], label=r["label"]) for r in rows]

    async def get_synonyms(self, class_uri: str) -> list[str]:
        """Get ``skos:altLabel`` synonyms for a class."""
        sparql = f"""
        SELECT ?altLabel WHERE {{
            <{class_uri}> skos:altLabel ?altLabel .
        }}
        """
        rows = await self.query(sparql)
        return [r["altLabel"] for r in rows]

    async def get_class_properties(self, class_uri: str) -> list[OntologyProperty]:
        """Get properties whose ``rdfs:domain`` is the given class."""
        sparql = f"""
        SELECT ?prop ?range ?propLabel WHERE {{
            ?prop rdfs:domain <{class_uri}> .
            ?prop rdfs:range ?range .
            ?prop rdfs:label ?propLabel .
        }}
        """
        rows = await self.query(sparql)
        return [
            OntologyProperty(
                uri=r["prop"], label=r["propLabel"],
                domain_uri=class_uri, range_uri=r["range"],
            )
            for r in rows
        ]

    async def get_class_by_label(self, label: str) -> OntologyClass | None:
        """Look up an ontology class by ``rdfs:label`` (case-insensitive)."""
        sparql = f"""
        SELECT ?cls ?label WHERE {{
            ?cls a owl:Class .
            ?cls rdfs:label ?label .
            FILTER(LCASE(STR(?label)) = LCASE("{label}"))
        }}
        LIMIT 1
        """
        rows = await self.query(sparql)
        if not rows:
            return None
        return OntologyClass(uri=rows[0]["cls"], label=rows[0]["label"])

"""B — Entity Linking: align proposed classes to external ontologies.

Inspired by the arXiv HITL paper (John et al., 2025) which identified
entity linking as critical but unsolved, and the Azure DTDL pattern of
referencing industry-standard ontologies.

This module links proposed ontology classes to external resources
(Wikidata, BFO, EMMO, schema.org) via label + embedding similarity.
Each linked class gets ``owl:sameAs`` or ``rdfs:seeAlso`` annotations,
preventing reinvention of existing concepts.

Uses Ollama embeddings for similarity computation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)


# ── Well-known external ontology prefixes ───────────────────────────

EXTERNAL_ONTOLOGIES: dict[str, dict[str, str]] = {
    "bfo": {
        "prefix": "http://purl.obolibrary.org/obo/",
        "label": "Basic Formal Ontology",
        "sparql": "https://query.wikidata.org/sparql",
    },
    "emmo": {
        "prefix": "https://w3id.org/emmo#",
        "label": "European Materials Modelling Ontology",
    },
    "schema": {
        "prefix": "https://schema.org/",
        "label": "Schema.org",
    },
    "wikidata": {
        "prefix": "http://www.wikidata.org/entity/",
        "label": "Wikidata",
        "sparql": "https://query.wikidata.org/sparql",
    },
    "saref": {
        "prefix": "https://saref.etsi.org/core/",
        "label": "SAREF — Smart Applications REFerence ontology",
    },
}


@dataclass
class EntityLink:
    """A link between a proposed class and an external resource."""

    proposed_label: str
    external_uri: str
    external_label: str
    ontology_source: str          # e.g. "wikidata", "bfo"
    similarity_score: float       # 0.0 – 1.0
    link_type: str = "seeAlso"    # "sameAs" | "seeAlso" | "closeMatch"
    verified: bool = False        # human-verified?


@dataclass
class EntityLinkReport:
    """Output of the entity linking phase."""

    links: list[EntityLink] = field(default_factory=list)
    unlinked_classes: list[str] = field(default_factory=list)
    coverage_pct: float = 0.0     # % of proposed classes with at least one link


class EntityLinker:
    """Link proposed ontology classes to external resources.

    Uses Ollama embeddings to compute similarity between proposed class
    labels and a local registry of well-known ontology terms.  Can also
    query Wikidata SPARQL for live matches.

    Parameters
    ----------
    settings:
        Application configuration (Ollama URL for embeddings).
    similarity_threshold:
        Minimum cosine similarity to consider a link (default 0.75).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        similarity_threshold: float = 0.75,
    ) -> None:
        self.settings = settings or Settings()
        self.similarity_threshold = similarity_threshold
        self._embedding_cache: dict[str, list[float]] = {}

    # ── Public API ──────────────────────────────────────────────────

    def link_classes(
        self,
        proposed_labels: list[str],
        reference_terms: dict[str, list[dict[str, str]]] | None = None,
    ) -> EntityLinkReport:
        """Find external matches for each proposed class label.

        Args:
            proposed_labels: Class labels to link.
            reference_terms: Optional dict  {ontology: [{label, uri}]}.
                If None, uses the built-in registry + Wikidata search.

        Returns:
            ``EntityLinkReport`` with links and coverage stats.
        """
        all_links: list[EntityLink] = []
        unlinked: list[str] = []

        for label in proposed_labels:
            links = self._find_links_for(label, reference_terms)
            if links:
                all_links.extend(links)
            else:
                unlinked.append(label)

        coverage = (
            (len(proposed_labels) - len(unlinked)) / len(proposed_labels)
            if proposed_labels else 0.0
        )

        report = EntityLinkReport(
            links=all_links,
            unlinked_classes=unlinked,
            coverage_pct=coverage,
        )
        logger.info(
            "entity_linking_complete",
            total=len(proposed_labels),
            linked=len(proposed_labels) - len(unlinked),
            coverage=f"{coverage:.0%}",
        )
        return report

    # ── Wikidata search ─────────────────────────────────────────────

    def search_wikidata(self, label: str, limit: int = 5) -> list[dict[str, str]]:
        """Search Wikidata for entities matching *label*.

        Uses the Wikidata search API (wbsearchentities).

        Returns:
            List of {uri, label, description} dicts.
        """
        try:
            resp = httpx.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbsearchentities",
                    "search": label,
                    "language": "en",
                    "format": "json",
                    "limit": limit,
                },
                headers={
                    "User-Agent": "OntologyExtender/1.0 (https://github.com/your-repo/ontology-extender)"
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            results = resp.json().get("search", [])
            return [
                {
                    "uri": f"http://www.wikidata.org/entity/{r['id']}",
                    "label": r.get("label", ""),
                    "description": r.get("description", ""),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("wikidata_search_failed", label=label, error=str(e))
            return []

    # ── Ollama embeddings ───────────────────────────────────────────

    def get_embedding(self, text: str) -> list[float] | None:
        """Get an embedding vector from Ollama for *text*.

        Uses the ``/api/embed`` endpoint introduced in Ollama 0.4+.
        Results are cached per session.
        """
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        try:
            resp = httpx.post(
                f"{self.settings.ollama_url}/api/embed",
                json={
                    "model": self.settings.ollama_model,
                    "input": text,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama returns {"embeddings": [[...]]} for single input
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                vec = embeddings[0]
                self._embedding_cache[text] = vec
                return vec
            return None
        except Exception as e:
            logger.warning("embedding_failed", text=text[:50], error=str(e))
            return None

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ── Internal helpers ────────────────────────────────────────────

    def _find_links_for(
        self,
        label: str,
        reference_terms: dict[str, list[dict[str, str]]] | None,
    ) -> list[EntityLink]:
        """Find all external matches for a single label."""
        links: list[EntityLink] = []

        # 1. Check against reference terms (if provided)
        if reference_terms:
            label_emb = self.get_embedding(label)
            if label_emb:
                for ont_name, terms in reference_terms.items():
                    for term in terms:
                        term_emb = self.get_embedding(term.get("label", ""))
                        if term_emb:
                            sim = self.cosine_similarity(label_emb, term_emb)
                            if sim >= self.similarity_threshold:
                                link_type = "sameAs" if sim > 0.92 else "seeAlso"
                                links.append(EntityLink(
                                    proposed_label=label,
                                    external_uri=term.get("uri", ""),
                                    external_label=term.get("label", ""),
                                    ontology_source=ont_name,
                                    similarity_score=sim,
                                    link_type=link_type,
                                ))

        # 2. Search Wikidata
        wd_results = self.search_wikidata(label, limit=3)
        label_emb = label_emb if reference_terms else self.get_embedding(label)
        for wd in wd_results:
            if label_emb:
                wd_emb = self.get_embedding(wd["label"])
                if wd_emb:
                    sim = self.cosine_similarity(label_emb, wd_emb)
                    if sim >= self.similarity_threshold:
                        links.append(EntityLink(
                            proposed_label=label,
                            external_uri=wd["uri"],
                            external_label=wd["label"],
                            ontology_source="wikidata",
                            similarity_score=sim,
                            link_type="seeAlso",
                        ))

        return links

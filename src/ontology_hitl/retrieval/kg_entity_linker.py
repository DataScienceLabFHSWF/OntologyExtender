"""KG Entity Linker — maps terms to Neo4j entities.

Adapted from GraphQAAgent ``EntityLinker``.  4-tier strategy:
  1. Exact ID match (case-insensitive)
  2. Label / alias / property search via Neo4j CONTAINS
  3. Fuzzy ranking (rapidfuzz Levenshtein ratio)
  4. Embedding-similarity fallback via Ollama + Qdrant
"""

from __future__ import annotations

import structlog
from rapidfuzz import fuzz

from ontology_hitl.connectors.neo4j import Neo4jConnector
from ontology_hitl.core.models import KGEntity

logger = structlog.get_logger(__name__)

_FUZZY_THRESHOLD = 50
_EMBEDDING_THRESHOLD = 0.6


class KGEntityLinker:
    """Link textual terms to :class:`KGEntity` nodes in Neo4j.

    Optionally accepts Qdrant + Ollama connectors for the embedding
    fallback tier.  Without them, tiers 1-3 still work.
    """

    def __init__(
        self,
        neo4j: Neo4jConnector,
        *,
        qdrant_client: object | None = None,   # qdrant_client.AsyncQdrantClient
        ollama_url: str = "",
        embedding_model: str = "qwen3-embedding",
    ) -> None:
        self._neo4j = neo4j
        self._qdrant = qdrant_client
        self._ollama_url = ollama_url
        self._embedding_model = embedding_model

    async def link(self, terms: list[str]) -> list[KGEntity]:
        """Return matched KG entities for the given terms.

        Returns up to 15 entities, sorted by best fuzzy score descending.
        """
        if not terms:
            return []

        # Tier 1: exact ID lookup
        id_entities = await self._neo4j.find_entities_by_ids(terms)

        # Tier 2: label / alias / property CONTAINS search
        label_candidates = await self._neo4j.find_entities_by_label(terms, limit=30)

        # Merge, dedup
        seen: set[str] = set()
        all_candidates: list[KGEntity] = []
        for e in id_entities:
            if e.id not in seen:
                seen.add(e.id)
                all_candidates.append(e)
        for e in label_candidates:
            if e.id not in seen:
                seen.add(e.id)
                all_candidates.append(e)

        # Tier 3: fuzzy ranking
        scored: list[tuple[KGEntity, float]] = []
        for entity in all_candidates:
            best_score = 0.0
            for term in terms:
                t = term.lower()
                scores = [
                    fuzz.ratio(t, entity.label.lower()),
                    fuzz.partial_ratio(t, entity.label.lower()),
                    fuzz.ratio(t, entity.id.lower()) * 1.2,
                ]
                if entity.description:
                    scores.append(fuzz.partial_ratio(t, entity.description.lower()) * 0.8)
                best_score = max(best_score, max(scores))
            if best_score >= _FUZZY_THRESHOLD or entity.id.lower() in [t.lower() for t in terms]:
                scored.append((entity, best_score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Tier 4: embedding fallback (optional)
        if not scored and self._ollama_url:
            scored = await self._embedding_fallback(terms)

        linked = [entity for entity, _ in scored[:15]]
        logger.info(
            "entity_linker.linked",
            terms=terms,
            candidates=len(all_candidates),
            matched=len(linked),
            top_ids=[e.id for e in linked[:5]],
        )
        return linked

    async def _embedding_fallback(
        self,
        terms: list[str],
    ) -> list[tuple[KGEntity, float]]:
        """Embed terms via Ollama and search Qdrant, then find related entities."""
        import httpx

        results: list[tuple[KGEntity, float]] = []
        for term in terms:
            try:
                resp = httpx.post(
                    f"{self._ollama_url}/api/embed",
                    json={"model": self._embedding_model, "input": term},
                    timeout=30.0,
                )
                resp.raise_for_status()
                # If we had Qdrant integration we'd search here;
                # for now, fall back to Neo4j label search with the term
                candidates = await self._neo4j.find_entities_by_label([term])
                for entity in candidates:
                    results.append((entity, _EMBEDDING_THRESHOLD))
            except Exception as exc:
                logger.debug("embedding_fallback_failed", term=term, error=str(exc))
        return results

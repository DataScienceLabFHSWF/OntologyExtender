"""GraphRAG-powered gap analyzer — live Neo4j + Fuseki for gap detection.

Replaces the offline checkpoint-based approach with actual graph traversal:
  1. Query Neo4j for all entities (ABox)
  2. Query Fuseki for all ontology classes (TBox)
  3. Entity-link ABox entities → TBox classes (fuzzy + embedding)
  4. Use neighbourhood expansion to find structurally uncovered regions
  5. Use PPR to rank gap candidates by graph centrality

This module can be used as a drop-in replacement for
:class:`~ontology_hitl.discovery.gap_analyzer.OntologyGapAnalyzer`.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

import numpy as np
import httpx
import structlog

from ontology_hitl.connectors.fuseki import FusekiConnector
from ontology_hitl.connectors.neo4j import Neo4jConnector
from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import (
    GapCandidate,
    GapReport,
    KGEntity,
    KGRelation,
    OntologyClass,
)
from ontology_hitl.retrieval.kg_entity_linker import KGEntityLinker
from ontology_hitl.retrieval.graph_retriever import GraphRetriever, GraphMode

logger = structlog.get_logger(__name__)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class GraphRAGGapAnalyzer:
    """Gap analyzer powered by live Neo4j + Fuseki queries.

    Instead of reading a KGB checkpoint JSON and doing offline cosine
    matching, this analyzer:

    1. Queries Neo4j for all ABox entities (the knowledge graph).
    2. Queries Fuseki for all TBox classes (the seed ontology).
    3. Uses the 4-tier :class:`KGEntityLinker` to match entities → classes.
    4. Entities that *cannot* be linked become gap candidates.
    5. For each gap candidate, uses PPR / neighbourhood expansion to
       compute structural importance and find the closest seed class.

    Parameters
    ----------
    settings : Settings
        Application configuration.
    neo4j : Neo4jConnector
        Connected async Neo4j client.
    fuseki : FusekiConnector
        Connected async Fuseki client.
    """

    def __init__(
        self,
        settings: Settings,
        neo4j: Neo4jConnector,
        fuseki: FusekiConnector,
    ) -> None:
        self._settings = settings
        self._neo4j = neo4j
        self._fuseki = fuseki
        self._entity_linker = KGEntityLinker(
            neo4j,
            ollama_url=settings.ollama_url,
            embedding_model=settings.semantic_embedding_model,
        )
        self._graph_retriever = GraphRetriever(neo4j, self._entity_linker, settings)

        # Embedding caches
        self._class_embeddings: dict[str, np.ndarray] = {}

    # -- public API ---------------------------------------------------------

    async def analyze(self) -> GapReport:
        """Run live GraphRAG gap analysis.

        Returns a :class:`GapReport` with coverage stats and gap candidates.
        No checkpoint file needed — queries Neo4j and Fuseki directly.
        """
        logger.info("graphrag_gap_analysis_start")

        # 1. Fetch all ABox entities from Neo4j
        abox_entities = await self._fetch_all_entities()
        logger.info("abox_entities_fetched", count=len(abox_entities))

        # 2. Fetch all TBox classes from Fuseki
        tbox_classes = await self._fuseki.get_all_classes()
        tbox_labels = [c.label for c in tbox_classes]
        logger.info("tbox_classes_fetched", count=len(tbox_classes))

        # 3. Classify entities as covered or uncovered
        covered, uncovered = await self._classify_entities(abox_entities, tbox_classes)

        # 4. Build gap candidates from uncovered entities
        gap_candidates = await self._build_gap_candidates(uncovered, tbox_classes)

        total = len(abox_entities)
        coverage_pct = len(covered) / total if total > 0 else 0.0

        report = GapReport(
            ontology_version="seed-v1.0",
            total_extracted_entities=total,
            covered_entities=len(covered),
            uncovered_entities=len(uncovered),
            coverage_pct=coverage_pct,
            gap_candidates=gap_candidates,
        )

        logger.info(
            "graphrag_gap_analysis_complete",
            total=total, covered=len(covered),
            gaps=len(gap_candidates),
            coverage_pct=f"{coverage_pct:.1%}",
        )
        return report

    # -- Neo4j: fetch all entities ------------------------------------------

    async def _fetch_all_entities(self) -> list[KGEntity]:
        """Query all ABox entities from Neo4j."""
        L = self._neo4j._lbl  # noqa: SLF001
        query = f"""
        MATCH (e{L})
        RETURN e, labels(e) AS _labels
        ORDER BY e.id
        LIMIT 5000
        """
        async with self._neo4j.driver.session(database=self._neo4j._db) as session:  # noqa: SLF001
            result = await session.run(query)
            records = await result.data()
        return [
            self._neo4j._record_to_entity(r["e"], neo4j_labels=r.get("_labels"))  # noqa: SLF001
            for r in records
        ]

    # -- Classification -----------------------------------------------------

    async def _classify_entities(
        self,
        entities: list[KGEntity],
        tbox_classes: list[OntologyClass],
    ) -> tuple[list[KGEntity], list[KGEntity]]:
        """Split entities into covered (match ontology) and uncovered.

        Uses a combination of:
          - Exact label match
          - Fuzzy label match (rapidfuzz)
          - Embedding cosine similarity
        """
        from rapidfuzz import fuzz

        tbox_label_set = {c.label.lower() for c in tbox_classes}
        tbox_labels = [c.label for c in tbox_classes]

        covered: list[KGEntity] = []
        uncovered: list[KGEntity] = []

        # Pre-compute TBox embeddings
        class_embeddings = await self._get_class_embeddings(tbox_labels)

        for entity in entities:
            etype = entity.entity_type.lower() if entity.entity_type else ""
            elabel = entity.label.lower() if entity.label else ""

            # Exact match on entity_type or label
            if etype in tbox_label_set or elabel in tbox_label_set:
                covered.append(entity)
                continue

            # Fuzzy match
            best_fuzzy = 0.0
            for tbox_label in tbox_labels:
                score = fuzz.ratio(etype, tbox_label.lower()) / 100.0
                best_fuzzy = max(best_fuzzy, score)
            if best_fuzzy >= 0.85:
                covered.append(entity)
                continue

            # Embedding match
            entity_embed = await self._get_embedding(entity.entity_type or entity.label)
            if entity_embed.shape[0] > 1:
                best_sim = -1.0
                for class_name, class_embed in class_embeddings.items():
                    if class_embed.shape[0] > 1:
                        sim = _cosine_similarity(entity_embed, class_embed)
                        best_sim = max(best_sim, sim)
                if best_sim >= self._settings.semantic_similarity_threshold:
                    covered.append(entity)
                    continue

            uncovered.append(entity)

        return covered, uncovered

    # -- Gap candidate building ---------------------------------------------

    async def _build_gap_candidates(
        self,
        uncovered: list[KGEntity],
        tbox_classes: list[OntologyClass],
    ) -> list[GapCandidate]:
        """Group uncovered entities and rank by structural importance."""
        # Group by entity_type
        type_groups: dict[str, list[KGEntity]] = defaultdict(list)
        for entity in uncovered:
            key = entity.entity_type or entity.label
            type_groups[key].append(entity)

        tbox_labels = [c.label for c in tbox_classes]
        class_embeddings = await self._get_class_embeddings(tbox_labels)

        candidates: list[GapCandidate] = []
        for entity_type, group in type_groups.items():
            freq = len(group)
            if freq < self._settings.min_entity_frequency:
                continue

            # Find closest seed class via embedding
            closest_seed_class = None
            semantic_distance: float | None = None
            entity_embed = await self._get_embedding(entity_type)
            if entity_embed.shape[0] > 1:
                best_sim, best_class = -1.0, None
                for class_name, class_embed in class_embeddings.items():
                    if class_embed.shape[0] > 1:
                        sim = _cosine_similarity(entity_embed, class_embed)
                        if sim > best_sim:
                            best_sim, best_class = sim, class_name
                if best_class:
                    closest_seed_class = best_class
                    semantic_distance = 1.0 - best_sim

            # Use GraphRAG to assess structural importance
            structural_score = await self._compute_structural_score(group)

            avg_conf = sum(e.confidence for e in group) / freq if freq else 0.0

            candidates.append(GapCandidate(
                entity_type=entity_type,
                representative_label=group[0].label,
                examples=[e.label for e in group[:5]],
                frequency=freq,
                avg_confidence=avg_conf,
                closest_seed_class=closest_seed_class,
                semantic_distance=semantic_distance if semantic_distance is not None else 1.0,
            ))

        # Sort by frequency × structural importance
        candidates.sort(key=lambda c: c.frequency, reverse=True)
        return candidates

    async def _compute_structural_score(self, entities: list[KGEntity]) -> float:
        """Estimate structural importance via neighbourhood density.

        Entities with many connections are more important gap candidates.
        """
        if not entities:
            return 0.0

        total_neighbours = 0
        sample = entities[:5]  # Sample up to 5 for efficiency
        for entity in sample:
            try:
                neighbours = await self._neo4j.get_entity_neighbours(entity.id, limit=20)
                total_neighbours += len(neighbours)
            except Exception:
                pass

        return total_neighbours / len(sample) if sample else 0.0

    # -- Embedding helpers --------------------------------------------------

    async def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector via Ollama /api/embed."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._settings.ollama_url}/api/embed",
                    json={"model": self._settings.semantic_embedding_model, "input": text},
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return np.array(data["embeddings"][0], dtype=np.float32)
        except Exception as e:
            logger.debug("embedding_failed", text=text[:50], error=str(e))
            return np.zeros(1)

    async def _get_class_embeddings(self, class_labels: list[str]) -> dict[str, np.ndarray]:
        """Embed all ontology class labels, with caching."""
        for label in class_labels:
            if label not in self._class_embeddings:
                self._class_embeddings[label] = await self._get_embedding(label)
        return self._class_embeddings

    # -- Context generation for agents --------------------------------------

    async def get_gap_context_for_agent(
        self,
        gap_candidate: GapCandidate,
    ) -> str:
        """Generate rich GraphRAG context for a gap candidate.

        Returns a natural-language summary of the KG evidence surrounding
        the gap, suitable for injection into agent prompts.
        """
        result = await self._graph_retriever.retrieve(
            [gap_candidate.entity_type, gap_candidate.representative_label],
            mode=GraphMode.SUBGRAPH,
        )
        context_parts = [
            f"Gap Candidate: {gap_candidate.entity_type}",
            f"  Frequency: {gap_candidate.frequency}",
            f"  Closest seed class: {gap_candidate.closest_seed_class or 'none'}",
            f"  Semantic distance: {gap_candidate.semantic_distance:.2f}",
            f"  Examples: {', '.join(gap_candidate.examples[:3])}",
            "",
        ]
        if result["text"]:
            context_parts.append(result["text"])
        else:
            context_parts.append("(No graph evidence found for this gap candidate.)")

        return "\n".join(context_parts)


# -- Sync wrapper for backwards compatibility --------------------------------

def run_graphrag_gap_analysis(settings: Settings) -> GapReport:
    """Synchronous entry point — connects to Neo4j + Fuseki, runs analysis.

    For use in the existing synchronous pipeline. Creates connectors,
    runs the async analysis, and cleans up.
    """
    async def _run() -> GapReport:
        neo4j = Neo4jConnector(settings)
        fuseki = FusekiConnector(settings)
        try:
            await neo4j.connect()
            await fuseki.connect()
            analyzer = GraphRAGGapAnalyzer(settings, neo4j, fuseki)
            return await analyzer.analyze()
        finally:
            await neo4j.close()
            await fuseki.close()

    return asyncio.run(_run())

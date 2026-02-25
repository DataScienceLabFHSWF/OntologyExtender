"""HybridRetriever — three-way fusion with RRF and cross-encoder reranking.

Ported from GraphQAAgent.  Combines vector + graph retrieval with ontology-
informed adaptive weighting, Reciprocal Rank Fusion, and optional cross-
encoder reranking.

**Key contribution**: ontology-informed fusion where graph results are weighted
higher when the question targets known ontology relations.

Pipeline:
1. Parallel retrieval: vector + graph
2. Ontology-informed adaptive weight adjustment
3. Relation-aware path ranking on graph contexts
4. Reciprocal Rank Fusion (RRF) merge
5. Cross-encoder reranking
6. Deduplication + provenance attachment
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import structlog

from ontology_hitl.connectors.fuseki import FusekiConnector
from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import (
    GraphExplorationState,
    Provenance,
    QAQuery,
    QuestionType,
    RetrievalSource,
    RetrievedContext,
)
from ontology_hitl.retrieval.graph_retriever import GraphRetriever
from ontology_hitl.retrieval.path_ranker import PathRanker
from ontology_hitl.retrieval.reranker import CrossEncoderReranker
from ontology_hitl.retrieval.vector import VectorRetriever

logger = structlog.get_logger(__name__)


class HybridRetriever:
    """FusionRAG: three-way retrieval with RRF, path ranking, and adaptive fusion."""

    def __init__(
        self,
        vector: VectorRetriever,
        graph: GraphRetriever,
        fuseki: FusekiConnector,
        reranker: CrossEncoderReranker,
        settings: Settings,
        *,
        path_ranker: PathRanker | None = None,
    ) -> None:
        self._vector = vector
        self._graph = graph
        self._fuseki = fuseki
        self._reranker = reranker
        self._settings = settings
        self._path_ranker = path_ranker or PathRanker()

    async def retrieve(self, query: QAQuery) -> list[RetrievedContext]:
        """Full hybrid retrieval pipeline.

        1. Parallel vector + graph retrieval.
        2. Relation-aware path ranking on graph results.
        3. Adaptive weight computation.
        4. RRF merge.
        5. Cross-encoder reranking.
        6. Provenance finalization.
        """
        t0 = time.perf_counter()

        # Phase 1 — Parallel retrieval
        vector_task = asyncio.create_task(self._vector.retrieve(query))
        graph_task = asyncio.create_task(
            self._graph_retrieve_wrapper(query)
        )

        vector_ctx = await vector_task
        graph_ctx = await graph_task

        # Phase 2 — Relation-aware path ranking on graph contexts
        if graph_ctx and query.expected_relations:
            graph_ctx = self._path_ranker.rank_paths(graph_ctx, query)

        # Phase 3 — Adaptive weights
        weights = await self._compute_adaptive_weights(query)

        # Phase 4 — Reciprocal Rank Fusion
        ranked_lists: dict[str, list[RetrievedContext]] = {
            "vector": vector_ctx,
            "graph": graph_ctx,
        }
        fused = reciprocal_rank_fusion(ranked_lists, weights)

        # Phase 5 — Cross-encoder reranking
        reranked = self._reranker.rerank(
            query=query.raw_question,
            contexts=fused,
            top_k=self._settings.vector_top_k,
        )

        # Phase 6 — Mark provenance as hybrid
        for ctx in reranked:
            if ctx.provenance:
                ctx.provenance.retrieval_strategy = (
                    f"hybrid({ctx.provenance.retrieval_strategy})"
                )
            ctx.source = RetrievalSource.HYBRID

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "hybrid.retrieve",
            vector_count=len(vector_ctx),
            graph_count=len(graph_ctx),
            fused_count=len(fused),
            final_count=len(reranked),
            weights=weights,
            latency_ms=round(elapsed, 1),
        )
        return reranked

    async def _graph_retrieve_wrapper(self, query: QAQuery) -> list[RetrievedContext]:
        """Wrap the GraphRetriever (which returns a dict) into RetrievedContext list."""
        try:
            result = await self._graph.retrieve(query.detected_entities or [query.raw_question])
            # Convert graph retriever dict output to RetrievedContext list
            text = result.get("text", "")
            entities = result.get("entities", [])
            relations = result.get("relations", [])

            if not text:
                return []

            return [
                RetrievedContext(
                    source=RetrievalSource.GRAPH,
                    text=text,
                    score=0.9,
                    subgraph=[*entities, *relations] if entities or relations else None,
                    provenance=Provenance(
                        entity_ids=[e.id for e in entities[:10]],
                        retrieval_strategy="graph",
                        retrieval_score=0.9,
                    ),
                )
            ]
        except Exception as exc:
            logger.warning("hybrid.graph_error", error=str(exc))
            return []

    async def _compute_adaptive_weights(
        self,
        query: QAQuery,
    ) -> dict[str, float]:
        """Adjust fusion weights based on query characteristics."""
        base: dict[str, float] = {
            "vector": self._settings.fusion_weight_vector,
            "graph": self._settings.fusion_weight_graph,
        }

        # Boost graph for structured question types
        if query.question_type in (QuestionType.CAUSAL, QuestionType.COMPARATIVE):
            base["graph"] = base.get("graph", 0.4) + 0.15
            base["vector"] = base.get("vector", 0.4) - 0.10

        # Boost graph when entities are detected
        if query.detected_entities:
            base["graph"] = base.get("graph", 0.4) + 0.05
        else:
            base["vector"] = base.get("vector", 0.4) + 0.15
            base["graph"] = base.get("graph", 0.4) - 0.10

        # Boost graph when ontology types have rich relations
        if query.detected_types:
            for type_uri in query.detected_types[:3]:
                try:
                    props = await self._fuseki.get_class_properties(type_uri)
                    if len(props) > 5:
                        base["graph"] = base.get("graph", 0.4) + 0.05
                        break
                except Exception:
                    pass

        # Normalise to sum to 1
        total = sum(base.values())
        if total > 0:
            base = {k: v / total for k, v in base.items()}

        return base


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[RetrievedContext]],
    weights: dict[str, float],
    k: int = 60,
) -> list[RetrievedContext]:
    """Standard RRF with per-source weights.

    For each document *d* appearing in any ranked list:

        rrf_score(d) = sum_{source} weight[source] / (k + rank[source](d))

    Returns merged list sorted by RRF score descending.
    """
    scores: dict[str, float] = defaultdict(float)
    context_map: dict[str, RetrievedContext] = {}

    for source, contexts in ranked_lists.items():
        weight = weights.get(source, 1.0)
        for rank, ctx in enumerate(contexts, start=1):
            key = ctx.text[:200]
            scores[key] += weight / (k + rank)
            if key not in context_map:
                context_map[key] = ctx

    sorted_keys = sorted(scores, key=lambda k_: scores[k_], reverse=True)
    result: list[RetrievedContext] = []
    for key in sorted_keys:
        ctx = context_map[key]
        ctx.score = scores[key]
        result.append(ctx)

    return result

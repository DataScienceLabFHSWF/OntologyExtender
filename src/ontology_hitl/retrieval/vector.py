"""VectorRetriever — classic RAG baseline.

Ported from GraphQAAgent.  Embeds the question via Ollama and retrieves
top-k nearest document chunks from Qdrant.
"""

from __future__ import annotations

import time

import structlog

from ontology_hitl.connectors.ollama import OllamaConnector
from ontology_hitl.connectors.qdrant import QdrantConnector
from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import (
    Provenance,
    QAQuery,
    RetrievalSource,
    RetrievedContext,
)

logger = structlog.get_logger(__name__)


class VectorRetriever:
    """Classic RAG: embed question → search Qdrant → return top-k chunks."""

    def __init__(
        self,
        qdrant: QdrantConnector,
        ollama: OllamaConnector,
        settings: Settings,
    ) -> None:
        self._qdrant = qdrant
        self._ollama = ollama
        self._settings = settings

    async def retrieve(self, query: QAQuery) -> list[RetrievedContext]:
        """Embed the raw question and search Qdrant for nearest chunks."""
        t0 = time.perf_counter()

        # 1. Embed the question
        query_vector = await self._ollama.embed(query.raw_question)
        if not query_vector:
            logger.warning("vector.embed_empty", question=query.raw_question[:80])
            return []

        # 2. Search Qdrant
        results = await self._qdrant.search(
            query_vector=query_vector,
            top_k=self._settings.vector_top_k,
        )

        # 3. Build RetrievedContext list
        contexts: list[RetrievedContext] = []
        for chunk, score in results:
            contexts.append(
                RetrievedContext(
                    source=RetrievalSource.VECTOR,
                    text=chunk.content,
                    score=score,
                    chunk=chunk,
                    provenance=Provenance(
                        doc_id=chunk.doc_id,
                        source_id=chunk.id,
                        retrieval_strategy="vector_only",
                        retrieval_score=score,
                    ),
                )
            )

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "vector.retrieve",
            question=query.raw_question[:80],
            num_results=len(contexts),
            latency_ms=round(elapsed, 1),
        )
        return contexts

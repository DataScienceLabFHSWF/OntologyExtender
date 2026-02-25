"""Async Qdrant connector — read-only vector similarity search.

Ported from GraphQAAgent ``QdrantConnector``.  Consumes the vector store
populated by KnowledgeGraphBuilder for document-chunk retrieval.
"""

from __future__ import annotations

from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import ScoredPoint

from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import DocumentChunk

logger = structlog.get_logger(__name__)


class QdrantConnector:
    """Async read-only client for Qdrant vector similarity search.

    Used by :class:`~ontology_hitl.retrieval.vector.VectorRetriever` to
    fetch the top-k document chunks nearest to an embedded query.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncQdrantClient | None = None

    # -- lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        """Open the connection and verify the collection exists."""
        try:
            self._client = AsyncQdrantClient(url=self._settings.qdrant_url)
            info = await self._client.get_collection(self._settings.qdrant_collection)
            vectors_count = getattr(
                info, "vectors_count", getattr(info, "points_count", "unknown")
            )
            logger.info(
                "qdrant.connected",
                url=self._settings.qdrant_url,
                collection=self._settings.qdrant_collection,
                vectors_count=vectors_count,
            )
        except Exception as exc:
            logger.error("qdrant.connect_failed", error=str(exc))
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            logger.info("qdrant.closed")

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("Qdrant client not initialised — call connect() first.")
        return self._client

    # -- search -------------------------------------------------------------

    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 10,
        score_threshold: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        """Search the collection for the top-k nearest neighbours.

        Returns ``(DocumentChunk, score)`` tuples sorted by similarity descending.
        """
        results = await self.client.query_points(
            collection_name=self._settings.qdrant_collection,
            query=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=filter_conditions,
        )

        return [
            (self._point_to_chunk(point), point.score)
            for point in results.points
        ]

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _point_to_chunk(point: ScoredPoint) -> DocumentChunk:
        payload = point.payload or {}
        return DocumentChunk(
            id=payload.get("id", str(point.id)),
            doc_id=payload.get("doc_id", ""),
            content=payload.get("content", ""),
            strategy=payload.get("strategy", ""),
            embedding=None,
        )

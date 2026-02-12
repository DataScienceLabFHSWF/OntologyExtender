"""Law collection source for legal documents in Qdrant.

Provides access to a dedicated Qdrant collection containing legal documents,
regulations, statutes, and compliance materials. This is separate from the
general document collection and contains specialized legal content.
"""

from __future__ import annotations

from typing import List, Optional

from ontology_hitl.sources.qdrant_source import QdrantDocumentSource


class LawCollectionSource(QdrantDocumentSource):
    """Access legal documents from a dedicated Qdrant collection.

    This source connects to a separate Qdrant collection containing
    legal documents, regulations, statutes, case law, and compliance
    materials. It provides specialized access to legal content for
    regulatory compliance and legal analysis.

    Parameters
    ----------
    qdrant_url : str
        Qdrant REST endpoint
    law_collection : str
        Name of the law collection (default: "law_documents")
    ollama_url : str
        Ollama endpoint for entity extraction
    ollama_model : str
        Model for entity extraction
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        law_collection: str = "lawgraph",  # Dedicated legal documents collection
        ollama_url: str = "http://localhost:18135",
        ollama_model: str = "qwen3-next",
    ) -> None:
        super().__init__(
            qdrant_url=qdrant_url,
            collection=law_collection,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
        )
        self.law_collection = law_collection

    def fetch_legal_chunks(
        self,
        limit: int = 200,
        jurisdiction: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """Fetch legal document chunks with optional filtering.

        Args:
            limit: Maximum number of chunks to return
            jurisdiction: Filter by jurisdiction (e.g., "nuclear", "environmental")
            document_type: Filter by document type (e.g., "regulation", "statute")

        Returns:
            List of legal document chunks
        """
        # Build filter conditions
        filter_conditions = []

        if jurisdiction:
            filter_conditions.append({
                "key": "jurisdiction",
                "match": {"value": jurisdiction}
            })

        if document_type:
            filter_conditions.append({
                "key": "document_type",
                "match": {"value": document_type}
            })

        # Use Qdrant's scroll with filtering if conditions exist
        if filter_conditions:
            return self._fetch_filtered_chunks(limit, filter_conditions)
        else:
            return self.fetch_chunks(limit=limit, prioritize_legal=True)

    def _fetch_filtered_chunks(
        self,
        limit: int,
        filter_conditions: List[dict],
    ) -> List[DocumentChunk]:
        """Fetch chunks with Qdrant filtering."""
        payload = {
            "limit": min(limit, 100),
            "filter": {
                "must": filter_conditions
            },
            "with_payload": True,
            "with_vector": False,
        }

        chunks = []
        collected = 0
        next_offset = None

        while collected < limit:
            if next_offset is not None:
                payload["offset"] = next_offset

            try:
                import httpx
                resp = httpx.post(
                    f"{self.qdrant_url}/collections/{self.collection}/points/scroll",
                    json=payload,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json().get("result", {})
            except httpx.HTTPError as e:
                logger.error("law_collection_scroll_failed", error=str(e))
                break

            points = data.get("points", [])
            if not points:
                break

            for pt in points:
                pl = pt.get("payload", {})
                chunk = DocumentChunk(
                    chunk_id=str(pt["id"]),
                    text=pl.get("text", pl.get("content", "")),
                    document_name=pl.get("document", pl.get("source", "unknown")),
                    metadata={k: v for k, v in pl.items()
                              if k not in ("text", "content")},
                )
                chunks.append(chunk)
                collected += 1
                if collected >= limit:
                    break

            next_offset = data.get("next_page_offset")
            if next_offset is None:
                break

        logger.info("law_chunks_fetched", count=len(chunks), filters=filter_conditions)
        return chunks

    def search_legal_precedents(
        self,
        query: str,
        limit: int = 50,
    ) -> List[DocumentChunk]:
        """Search for legal precedents using semantic search.

        Args:
            query: Search query for legal precedents
            limit: Maximum results to return

        Returns:
            Relevant legal precedent chunks
        """
        # This would require vector search capabilities
        # For now, return filtered chunks by precedent indicators
        chunks = self.fetch_legal_chunks(limit=limit * 2)

        # Filter for precedent-related content
        precedents = []
        for chunk in chunks:
            if self._is_precedent(chunk):
                precedents.append(chunk)
                if len(precedents) >= limit:
                    break

        return precedents

    def _is_precedent(self, chunk: DocumentChunk) -> bool:
        """Check if chunk contains legal precedent information."""
        text_lower = chunk.text.lower()
        precedent_indicators = [
            "precedent", "case law", "court decision", "judicial",
            "ruling", "judgment", "appellate", "supreme court",
            "district court", "legal opinion", "stare decisis"
        ]

        return any(indicator in text_lower for indicator in precedent_indicators)
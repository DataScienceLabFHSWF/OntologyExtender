"""Qdrant-based document and entity source.

Reads document chunks directly from the Qdrant vector store that is shared
with KnowledgeGraphBuilder.  This allows the OntologyExtender to run
**independently** of KGB — no extraction checkpoint needed.

Two modes of operation
---------------------
1. **Entity extraction mode** (standalone):
   Fetches document chunks → asks the LLM to extract entity types →
   returns ``ExtractedEntitySummary`` list (same interface as a
   KGB checkpoint).

2. **Document chunk mode** (for CQ generation):
   Fetches raw document text chunks so the CQ generator can derive
   competency questions from actual domain language.

Both modes read from the same Qdrant collection populated by KGB's
document ingestion pipeline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import httpx
import structlog

from ontology_hitl.core.models import ExtractedEntitySummary

logger = structlog.get_logger(__name__)


@dataclass
class DocumentChunk:
    """A single text chunk retrieved from Qdrant."""

    chunk_id: str
    text: str
    document_name: str
    metadata: dict = field(default_factory=dict)


class QdrantDocumentSource:
    """Read document chunks and extract entities directly from Qdrant.

    This makes the OntologyExtender independent of KGB — it can discover
    domain concepts by reading the same documents KGB uses, without
    requiring KGB to have been run first.

    Parameters
    ----------
    qdrant_url:
        Qdrant REST endpoint (default ``http://localhost:6333``).
    collection:
        Name of the Qdrant collection holding document chunks.
    ollama_url:
        Ollama endpoint for on-the-fly entity extraction.
    ollama_model:
        Model to use for entity extraction.
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        collection: str = "documents",
        ollama_url: str = "http://localhost:18135",
        ollama_model: str = "qwen3-next",
    ) -> None:
        self.qdrant_url = qdrant_url.rstrip("/")
        self.collection = collection
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model

    # ------------------------------------------------------------------
    # Public: fetch raw chunks
    # ------------------------------------------------------------------

    def fetch_chunks(
        self,
        limit: int = 500,
        offset: int | None = None,
    ) -> list[DocumentChunk]:
        """Scroll through the Qdrant collection and return text chunks.

        Uses the Qdrant REST ``/scroll`` endpoint so no query vector is
        needed — we simply iterate over all stored points.

        Args:
            limit: Maximum number of chunks to return.
            offset: Qdrant point-id to start after (for pagination).

        Returns:
            List of ``DocumentChunk`` with text + metadata.
        """
        payload: dict = {
            "limit": min(limit, 100),  # Qdrant caps per-request
            "with_payload": True,
            "with_vector": False,
        }
        if offset is not None:
            payload["offset"] = offset

        chunks: list[DocumentChunk] = []
        collected = 0
        next_offset = offset

        while collected < limit:
            if next_offset is not None:
                payload["offset"] = next_offset

            try:
                resp = httpx.post(
                    f"{self.qdrant_url}/collections/{self.collection}/points/scroll",
                    json=payload,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json().get("result", {})
            except httpx.HTTPError as e:
                logger.error("qdrant_scroll_failed", error=str(e))
                break

            points = data.get("points", [])
            if not points:
                break

            for pt in points:
                pl = pt.get("payload", {})
                chunks.append(DocumentChunk(
                    chunk_id=str(pt["id"]),
                    text=pl.get("text", pl.get("content", "")),
                    document_name=pl.get("document", pl.get("source", "unknown")),
                    metadata={k: v for k, v in pl.items()
                              if k not in ("text", "content")},
                ))
                collected += 1
                if collected >= limit:
                    break

            next_offset = data.get("next_page_offset")
            if next_offset is None:
                break

        logger.info("qdrant_chunks_fetched", count=len(chunks))
        return chunks

    # ------------------------------------------------------------------
    # Public: standalone entity extraction (no KGB needed)
    # ------------------------------------------------------------------

    def extract_entities(
        self,
        chunks: list[DocumentChunk] | None = None,
        max_chunks: int = 200,
    ) -> list[ExtractedEntitySummary]:
        """Extract entity types from document chunks via LLM.

        This is the **standalone alternative** to loading a KGB checkpoint.
        The LLM reads each chunk and identifies domain-specific entity types,
        which are then aggregated into the same ``ExtractedEntitySummary``
        format that ``OntologyGapAnalyzer.analyze()`` expects.

        Args:
            chunks: Pre-fetched chunks (fetched from Qdrant if ``None``).
            max_chunks: Maximum chunks to process.

        Returns:
            Deduplicated list of ``ExtractedEntitySummary``.
        """
        if chunks is None:
            chunks = self.fetch_chunks(limit=max_chunks)

        logger.info("standalone_extraction_start", chunks=len(chunks))

        # Accumulate: entity_type → {labels, docs, snippets, confidences}
        from collections import defaultdict
        accumulator: dict[str, dict] = defaultdict(lambda: {
            "labels": [],
            "docs": set(),
            "snippets": [],
            "confidences": [],
        })

        for chunk in chunks[:max_chunks]:
            extracted = self._extract_from_chunk(chunk)
            for ent in extracted:
                acc = accumulator[ent["entity_type"]]
                acc["labels"].append(ent["label"])
                acc["docs"].add(chunk.document_name)
                acc["snippets"].append(chunk.text[:200])
                acc["confidences"].append(ent.get("confidence", 0.7))

        # Convert to ExtractedEntitySummary
        entities: list[ExtractedEntitySummary] = []
        for etype, data in accumulator.items():
            # Generate a stable ID from entity type and label (mimics KGB pattern)
            label = data["labels"][0]
            entity_id = f"ent_{hashlib.sha256(f'{label}::{etype}'.encode()).hexdigest()[:12]}"
            entities.append(ExtractedEntitySummary(
                id=entity_id,
                label=label,  # representative
                entity_type=etype,
                description="",  # No description from Qdrant extraction
                aliases=data["labels"][1:] if len(data["labels"]) > 1 else [],
                confidence=sum(data["confidences"]) / len(data["confidences"]),
                frequency=len(data["labels"]),
                source_ids=sorted(data["docs"]),
                evidence_spans=data["snippets"][:5],
            ))

        entities.sort(key=lambda e: e.frequency, reverse=True)
        logger.info("standalone_extraction_done", entity_types=len(entities))
        return entities

    # ------------------------------------------------------------------
    # Internal: LLM-based entity extraction from a single chunk
    # ------------------------------------------------------------------

    def _extract_from_chunk(self, chunk: DocumentChunk) -> list[dict]:
        """Ask the LLM to identify entity types in a document chunk.

        Returns:
            List of dicts: [{"label": "...", "entity_type": "...", "confidence": 0.8}]
        """
        import json as json_mod

        prompt = (
            "Extract all domain-specific entities from this nuclear decommissioning "
            "document chunk. For each entity, provide:\n"
            "- label: the entity mention as it appears in text\n"
            "- entity_type: a short CamelCase class name (e.g. Facility, Permit, "
            "Regulation, Hazard, Strategy, Activity)\n"
            "- confidence: 0.0 to 1.0\n\n"
            "Return a JSON array. If no entities, return [].\n\n"
            f"--- CHUNK ---\n{chunk.text[:1500]}\n--- END ---"
        )

        try:
            resp = httpx.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3, "num_predict": 1024},
                },
                timeout=180.0,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            parsed = json_mod.loads(content)
            if isinstance(parsed, list):
                return parsed
            # Some models wrap in {"entities": [...]}
            return parsed.get("entities", [])
        except Exception as e:
            logger.warning("chunk_extraction_failed",
                           chunk=chunk.chunk_id, error=str(e))
            return []

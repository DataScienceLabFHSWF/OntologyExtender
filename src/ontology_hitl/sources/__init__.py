"""Data source adapters — Qdrant, KGB checkpoint, or direct documents."""

from ontology_hitl.sources.qdrant_ingestor import (
    QdrantKnowledgeIngestor,
    collection_name_for,
)

__all__ = ["QdrantKnowledgeIngestor", "collection_name_for"]

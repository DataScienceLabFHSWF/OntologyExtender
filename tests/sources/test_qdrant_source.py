"""Tests for Qdrant document source and standalone entity extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ontology_hitl.sources.qdrant_source import DocumentChunk, QdrantDocumentSource


@pytest.fixture
def qdrant_source():
    return QdrantDocumentSource(
        qdrant_url="http://localhost:6333",
        collection="test-docs",
        ollama_url="http://localhost:18135",
        ollama_model="qwen3-next",
    )


class TestFetchChunks:
    def test_fetch_chunks_parses_qdrant_response(self, qdrant_source):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "points": [
                    {
                        "id": "abc-123",
                        "payload": {
                            "text": "The Greifswald nuclear facility...",
                            "document": "doc_15.pdf",
                            "page": 3,
                        },
                    },
                    {
                        "id": "def-456",
                        "payload": {
                            "content": "Permit requirements for decommissioning...",
                            "source": "doc_22.pdf",
                        },
                    },
                ],
                "next_page_offset": None,
            }
        }

        with patch("httpx.post", return_value=mock_resp):
            chunks = qdrant_source.fetch_chunks(limit=10)

        assert len(chunks) == 2
        # Both chunks present (order may vary due to legal-doc prioritization)
        ids = {c.chunk_id for c in chunks}
        assert ids == {"abc-123", "def-456"}
        greifswald = [c for c in chunks if c.chunk_id == "abc-123"][0]
        permit = [c for c in chunks if c.chunk_id == "def-456"][0]
        assert greifswald.document_name == "doc_15.pdf"
        assert "Greifswald" in greifswald.text
        # Second chunk uses "content" and "source" keys
        assert "Permit" in permit.text
        assert permit.document_name == "doc_22.pdf"

    def test_fetch_chunks_handles_connection_error(self, qdrant_source):
        import httpx
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            chunks = qdrant_source.fetch_chunks(limit=10)
        assert chunks == []


class TestExtractEntities:
    def test_extract_entities_aggregates_by_type(self, qdrant_source):
        chunks = [
            DocumentChunk("1", "Facility A is a nuclear plant.", "doc1.pdf"),
            DocumentChunk("2", "Facility B requires a permit.", "doc2.pdf"),
        ]

        def mock_extract(chunk):
            if "Facility A" in chunk.text:
                return [
                    {"label": "Facility A", "entity_type": "Facility", "confidence": 0.9},
                ]
            return [
                {"label": "Facility B", "entity_type": "Facility", "confidence": 0.8},
                {"label": "Permit X", "entity_type": "Permit", "confidence": 0.85},
            ]

        qdrant_source._extract_from_chunk = mock_extract

        entities = qdrant_source.extract_entities(chunks=chunks)

        type_map = {e.entity_type: e for e in entities}
        assert "Facility" in type_map
        assert type_map["Facility"].frequency == 2
        assert type_map["Facility"].confidence == pytest.approx(0.85)
        assert "Permit" in type_map


class TestDocumentChunk:
    def test_document_chunk_fields(self):
        chunk = DocumentChunk(
            chunk_id="test-1",
            text="Some nuclear text.",
            document_name="test.pdf",
            metadata={"page": 5},
        )
        assert chunk.chunk_id == "test-1"
        assert chunk.metadata["page"] == 5

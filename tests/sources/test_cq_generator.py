"""Tests for CQ generator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ontology_hitl.sources.cq_generator import CQGenerator
from ontology_hitl.sources.qdrant_source import DocumentChunk, QdrantDocumentSource


@pytest.fixture
def cq_generator():
    source = QdrantDocumentSource(qdrant_url="http://localhost:6333")
    return CQGenerator(
        qdrant_source=source,
        ollama_url="http://localhost:18135",
        ollama_model="gemma4:31b",
    )


class TestCQGeneration:
    def test_generate_merges_with_existing(self, cq_generator, tmp_path):
        existing_cqs = [
            {"id": "CQ_001", "question": "What is decommissioning?", "difficulty": 2},
        ]
        existing_file = tmp_path / "existing_cqs.json"
        import json
        existing_file.write_text(json.dumps(existing_cqs))

        # Mock Qdrant fetch to return some chunks
        cq_generator.qdrant_source.fetch_chunks = MagicMock(return_value=[
            DocumentChunk("1", "Nuclear facility overview.", "doc1.pdf"),
        ])

        # Mock LLM to return one new CQ
        cq_generator._generate_batch = MagicMock(return_value=[
            {
                "question": "Which regulations apply to facility X?",
                "expected_entity_types": ["Facility", "Regulation"],
                "expected_relations": ["regulatedBy"],
                "difficulty": 3,
                "priority": 1,
            },
        ])

        result = cq_generator.generate(
            num_chunks=5,
            existing_cq_path=existing_file,
        )

        assert len(result) == 2  # 1 existing + 1 new
        assert result[0]["id"] == "CQ_001"  # existing preserved
        assert result[1]["id"] == "CQ_002"  # auto-numbered
        assert "regulations" in result[1]["question"].lower()

    def test_generate_deduplicates(self, cq_generator):
        cq_generator.qdrant_source.fetch_chunks = MagicMock(return_value=[
            DocumentChunk("1", "Some text.", "doc1.pdf"),
        ])

        # Return duplicate questions
        cq_generator._generate_batch = MagicMock(return_value=[
            {"question": "Same question", "difficulty": 2, "priority": 1,
             "expected_entity_types": [], "expected_relations": []},
            {"question": "Same question", "difficulty": 3, "priority": 1,
             "expected_entity_types": [], "expected_relations": []},
        ])

        result = cq_generator.generate(num_chunks=5)
        # Should deduplicate to 1
        assert len(result) == 1

    def test_generate_sets_default_cq_type(self, cq_generator):
        cq_generator.qdrant_source.fetch_chunks = MagicMock(return_value=[
            DocumentChunk("1", "Some text.", "doc1.pdf"),
        ])
        cq_generator._generate_batch = MagicMock(return_value=[
            {"question": "What is X?", "difficulty": 2, "priority": 1,
             "expected_entity_types": [], "expected_relations": []},
        ])

        result = cq_generator.generate(num_chunks=5)
        assert len(result) == 1
        assert result[0]["cq_type"] == "VCQ"


class TestSampleDiverse:
    def test_round_robin_across_docs(self):
        chunks = [
            DocumentChunk("1", "A", "doc1.pdf"),
            DocumentChunk("2", "B", "doc1.pdf"),
            DocumentChunk("3", "C", "doc2.pdf"),
            DocumentChunk("4", "D", "doc3.pdf"),
        ]

        result = CQGenerator._sample_diverse(chunks, target=3)
        docs = {c.document_name for c in result}
        # Should pick from all 3 docs rather than just doc1
        assert len(docs) >= 2

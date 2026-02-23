"""Tests for CompletenessAnalyzer."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ontology_hitl.evaluation.completeness import CompletenessAnalyzer


@pytest.fixture
def _mock_services():
    """Patch Fuseki SPARQL and Ollama embedding calls."""
    with (
        patch.object(
            CompletenessAnalyzer,
            "_get_ontology_classes",
            return_value=["Action", "DomainConstant", "Facility"],
        ),
        patch.object(
            CompletenessAnalyzer,
            "_get_embedding",
            return_value=[0.0] * 8,
        ),
    ):
        yield


class TestCompletenessAnalyzer:
    """Test entity schema coverage analysis."""

    def test_measure_coverage_returns_dict(self, tmp_path, _mock_services) -> None:
        """Test that measure_schema_coverage returns expected structure."""
        checkpoint = tmp_path / "checkpoint.json"
        checkpoint.write_text(
            json.dumps(
                {
                    "entities": [
                        {"label": "Plant A", "entity_type": "Facility", "confidence": 0.9},
                        {"label": "Cut", "entity_type": "Action", "confidence": 0.8},
                        {"label": "Uranium", "entity_type": "Material", "confidence": 0.7},
                    ]
                }
            )
        )

        analyzer = CompletenessAnalyzer()
        result = analyzer.measure_schema_coverage(checkpoint_path=str(checkpoint))

        assert "covered_entities" in result
        assert "total_entities" in result
        assert "coverage_pct" in result
        # Facility and Action should match exactly; Material has no match
        assert result["total_entities"] == 3
        assert result["covered_entities"] >= 2

    def test_empty_checkpoint(self, tmp_path, _mock_services) -> None:
        """Coverage of an empty checkpoint is 0%."""
        checkpoint = tmp_path / "empty.json"
        checkpoint.write_text(json.dumps({"entities": []}))

        analyzer = CompletenessAnalyzer()
        result = analyzer.measure_schema_coverage(checkpoint_path=str(checkpoint))

        assert result["total_entities"] == 0
        assert result["coverage_pct"] == 0.0

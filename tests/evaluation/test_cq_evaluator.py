"""Tests for CQEvaluator."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ontology_hitl.evaluation.cq_evaluator import CQEvaluator


@pytest.fixture
def _mock_cq_services():
    """Patch Fuseki SPARQL and Ollama LLM calls."""
    with (
        patch.object(
            CQEvaluator,
            "_sparql_query",
            return_value=[{"label": "Action"}, {"label": "Facility"}],
        ),
        patch.object(
            CQEvaluator,
            "_sparql_ask",
            return_value=True,
        ),
        patch.object(
            CQEvaluator,
            "_call_llm",
            return_value="ASK { ?x a <http://ex.org/Facility> }",
        ),
    ):
        yield


class TestCQEvaluator:
    """Test competency question evaluation."""

    def test_evaluate_coverage_returns_dict(self, tmp_path, _mock_cq_services) -> None:
        """Test that evaluate_coverage returns expected structure."""
        cq_file = tmp_path / "cqs.json"
        cq_file.write_text(
            json.dumps(
                [
                    {"question": "What facilities exist?", "expected_classes": ["Facility"]},
                    {"question": "What actions can be performed?", "expected_classes": ["Action"]},
                ]
            )
        )

        evaluator = CQEvaluator()
        result = evaluator.evaluate_coverage(cq_path=str(cq_file))

        assert "total_cqs" in result
        assert "answerable" in result
        assert "coverage_pct" in result
        assert result["total_cqs"] == 2

    def test_evaluate_empty_cqs(self, tmp_path, _mock_cq_services) -> None:
        """Empty CQ list gives 0% coverage."""
        cq_file = tmp_path / "empty_cqs.json"
        cq_file.write_text(json.dumps([]))

        evaluator = CQEvaluator()
        result = evaluator.evaluate_coverage(cq_path=str(cq_file))

        assert result["total_cqs"] == 0
        assert result["coverage_pct"] == 0.0

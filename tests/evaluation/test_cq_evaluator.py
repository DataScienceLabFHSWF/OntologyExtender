"""Tests for CQEvaluator."""

from __future__ import annotations

from ontology_hitl.evaluation.cq_evaluator import CQEvaluator


class TestCQEvaluator:
    """Test competency question evaluation."""

    def test_evaluate_coverage_returns_dict(self) -> None:
        """Test that evaluate_coverage returns expected structure."""
        evaluator = CQEvaluator()
        result = evaluator.evaluate_coverage(cq_path="dummy.json")
        assert "total_cqs" in result
        assert "answerable" in result
        assert "coverage_pct" in result

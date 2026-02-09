"""Tests for CompletenessAnalyzer."""

from __future__ import annotations

from ontology_hitl.evaluation.completeness import CompletenessAnalyzer


class TestCompletenessAnalyzer:
    """Test entity schema coverage analysis."""

    def test_measure_coverage_returns_dict(self) -> None:
        """Test that measure_schema_coverage returns expected structure."""
        analyzer = CompletenessAnalyzer()
        result = analyzer.measure_schema_coverage(checkpoint_path="dummy.json")
        assert "covered_entities" in result
        assert "total_entities" in result
        assert "coverage_pct" in result

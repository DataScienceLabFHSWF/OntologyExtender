"""Tests for OntologyGapAnalyzer."""

from __future__ import annotations

from pathlib import Path

from ontology_hitl.discovery.gap_analyzer import OntologyGapAnalyzer


class TestOntologyGapAnalyzer:
    """Test gap analysis functionality."""

    def test_load_checkpoint(self, sample_checkpoint: Path) -> None:
        """Test loading entities from checkpoint JSON."""
        analyzer = OntologyGapAnalyzer(min_frequency=1)
        entities = analyzer._load_checkpoint(sample_checkpoint)
        assert len(entities) == 3
        assert entities[0].label == "Kernkraftwerk Greifswald"
        assert entities[0].entity_type == "Facility"

    def test_analyze_returns_gap_report(self, sample_checkpoint: Path) -> None:
        """Test full gap analysis pipeline."""
        analyzer = OntologyGapAnalyzer(min_frequency=1)
        report = analyzer.analyze(sample_checkpoint)
        assert report.total_extracted_entities == 3
        # With no ontology classes, all should be uncovered
        assert report.uncovered_entities == 3
        assert report.coverage_pct == 0.0

    def test_gap_candidates_filtered_by_frequency(self, sample_checkpoint: Path) -> None:
        """Test that low-frequency entities are filtered out."""
        analyzer = OntologyGapAnalyzer(min_frequency=5)
        report = analyzer.analyze(sample_checkpoint)
        # All entity types appear only once in the checkpoint, so
        # with min_frequency=5 none should pass the filter
        assert len(report.gap_candidates) == 0

"""Tests for OntologyGapAnalyzer.

The gap analyzer is a *production-only* component used in the coupled
KGB pipeline for the nuclear decommissioning domain.  It compares KGB
extraction checkpoint entities against the current Fuseki ontology.

For benchmarking tests (OntoURL, TamingHallucinations, etc.) no KG is
built, so the gap analyzer is not invoked there.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np

from ontology_hitl.discovery.gap_analyzer import OntologyGapAnalyzer


def _zero_embedding(_self, _text: str) -> np.ndarray:
    """Return a deterministic zero vector so no real Ollama call is made.

    With zero vectors, cosine similarity is 0.0 for all pairs, which
    ensures that entities with no matching ontology class are correctly
    classified as uncovered.
    """
    return np.zeros(64, dtype=np.float32)


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
        """With no ontology classes and mocked embeddings all entities should be uncovered."""
        analyzer = OntologyGapAnalyzer(min_frequency=1)
        with patch.object(OntologyGapAnalyzer, "_get_ontology_classes", return_value=[]), \
             patch.object(OntologyGapAnalyzer, "_get_embedding", _zero_embedding):
            report = analyzer.analyze(sample_checkpoint)
        assert report.total_extracted_entities == 3
        # Fuseki mocked to return 0 classes → no match possible with zero embeddings
        assert report.uncovered_entities == 3
        assert report.coverage_pct == 0.0

    def test_gap_candidates_filtered_by_frequency(self, sample_checkpoint: Path) -> None:
        """Test that low-frequency entities are filtered out."""
        analyzer = OntologyGapAnalyzer(min_frequency=5)
        with patch.object(OntologyGapAnalyzer, "_get_ontology_classes", return_value=[]), \
             patch.object(OntologyGapAnalyzer, "_get_embedding", _zero_embedding):
            report = analyzer.analyze(sample_checkpoint)
        # All entity types appear only once in the checkpoint, so
        # with min_frequency=5 none should pass the filter
        assert len(report.gap_candidates) == 0

    @patch.object(OntologyGapAnalyzer, "_get_embedding", _zero_embedding)
    def test_exact_match_counts_as_covered(self, sample_checkpoint: Path) -> None:
        """An entity whose type exactly matches an ontology class is covered."""
        analyzer = OntologyGapAnalyzer(min_frequency=1)
        # Inject one class that matches "Facility" exactly
        with patch.object(
            OntologyGapAnalyzer,
            "_get_ontology_classes",
            return_value=["Facility"],
        ):
            report = analyzer.analyze(sample_checkpoint)
        # Facility → covered, Permit + Action → uncovered
        assert report.covered_entities == 1
        assert report.uncovered_entities == 2

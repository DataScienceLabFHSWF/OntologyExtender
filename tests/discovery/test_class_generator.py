"""Tests for ClassDefinitionGenerator."""

from __future__ import annotations

import pytest

from ontology_hitl.discovery.class_generator import ClassDefinitionGenerator
from ontology_hitl.core.models import GapCandidate


@pytest.mark.slow
class TestClassDefinitionGenerator:
    """Test class proposal generation."""

    def test_generate_from_gaps(self, sample_gap_candidates: list) -> None:
        """Test generating proposals from gap candidates."""
        gen = ClassDefinitionGenerator()
        proposals = gen.generate_from_gaps(sample_gap_candidates, max_proposals=5)
        assert len(proposals) == 2
        assert proposals[0].label == "Facility"
        assert proposals[0].id == "prop_001"

    def test_default_properties_generated(self, sample_gap_candidates: list) -> None:
        """Test that default properties are suggested."""
        gen = ClassDefinitionGenerator()
        proposals = gen.generate_from_gaps(sample_gap_candidates)
        assert len(proposals[0].suggested_properties) >= 1
        prop_names = [p.name for p in proposals[0].suggested_properties]
        assert "label" in prop_names

    def test_max_proposals_limit(self, sample_gap_candidates: list) -> None:
        """Test max_proposals parameter."""
        gen = ClassDefinitionGenerator()
        proposals = gen.generate_from_gaps(sample_gap_candidates, max_proposals=1)
        assert len(proposals) == 1

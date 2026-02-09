"""Tests for SHACLGenerator."""

from __future__ import annotations

from ontology_hitl.schema.shacl_generator import SHACLGenerator
from ontology_hitl.core.models import ProposedClass


class TestSHACLGenerator:
    """Test SHACL shape generation."""

    def test_generate_shape_returns_turtle(self, sample_proposed_class: ProposedClass) -> None:
        """Test that generate_shape returns valid Turtle-like string."""
        gen = SHACLGenerator()
        shape = gen.generate_shape(sample_proposed_class)
        assert "FacilityShape" in shape
        assert "sh:NodeShape" in shape
        assert "sh:targetClass" in shape

    def test_required_property_has_min_count(self, sample_proposed_class: ProposedClass) -> None:
        """Test that required properties get sh:minCount 1."""
        gen = SHACLGenerator()
        shape = gen.generate_shape(sample_proposed_class)
        assert "sh:minCount 1" in shape

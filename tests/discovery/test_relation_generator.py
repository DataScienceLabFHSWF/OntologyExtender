"""Tests for RelationProposalGenerator."""

from __future__ import annotations

from ontology_hitl.discovery.relation_generator import RelationProposalGenerator
from ontology_hitl.core.models import ProposedClass


class TestRelationProposalGenerator:
    """Test relation suggestion functionality."""

    def test_suggest_relations_returns_list(self, sample_proposed_class: ProposedClass) -> None:
        """Test that suggest_relations returns a list."""
        gen = RelationProposalGenerator()
        relations = gen.suggest_relations(
            proposed_class=sample_proposed_class,
            existing_classes=["Action", "DomainConstant"],
        )
        assert isinstance(relations, list)

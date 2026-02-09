"""Tests for OntologySchemaManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontology_hitl.schema.manager import OntologySchemaManager


class TestOntologySchemaManager:
    """Test ontology schema management."""

    def test_apply_decisions(self, tmp_path: Path) -> None:
        """Test loading proposals and filtering by decisions."""
        proposals = [
            {"id": "prop_001", "label": "Facility", "definition": "A facility.", "parent_uri": "", "parent_label": ""},
            {"id": "prop_002", "label": "Permit", "definition": "A permit.", "parent_uri": "", "parent_label": ""},
        ]
        decisions = [
            {"proposal_id": "prop_001", "decision": "accept"},
            {"proposal_id": "prop_002", "decision": "reject"},
        ]

        proposals_path = tmp_path / "proposals.json"
        decisions_path = tmp_path / "decisions.json"
        with open(proposals_path, "w") as f:
            json.dump(proposals, f)
        with open(decisions_path, "w") as f:
            json.dump(decisions, f)

        manager = OntologySchemaManager(seed_ontology_path="dummy.owl")
        accepted = manager.apply_decisions(proposals_path, decisions_path)

        assert len(accepted) == 1
        assert accepted[0].label == "Facility"

    def test_export_owl_not_implemented(self, tmp_path: Path) -> None:
        """Test that OWL export raises NotImplementedError."""
        manager = OntologySchemaManager(seed_ontology_path="dummy.owl")
        with pytest.raises(NotImplementedError):
            manager.export_owl(tmp_path / "out.owl")

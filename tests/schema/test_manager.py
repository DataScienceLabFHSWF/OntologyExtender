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

    def test_export_owl_writes_file(self, tmp_path: Path) -> None:
        """Exported OWL should be created and contain minimal RDF structure.

        The previous test expected a ``NotImplementedError``; the feature has
        been implemented so we now supply a tiny dummy seed ontology and verify
        that ``export_owl`` succeeds without error and produces a file with an
        RDF root element.
        """
        # create minimal seed ontology so rdflib can parse it
        seed = tmp_path / "seed.owl"
        seed.write_text(
            '<?xml version="1.0"?>\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '</rdf:RDF>'
        )
        manager = OntologySchemaManager(seed_ontology_path=seed)
        # no accepted classes at start
        manager.export_owl(tmp_path / "out.owl")
        out = tmp_path / "out.owl"
        assert out.exists(), "OWL export file was not created"
        content = out.read_text()
        assert "rdf:RDF" in content

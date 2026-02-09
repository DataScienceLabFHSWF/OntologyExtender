"""Tests for YARRRMLGenerator."""

from __future__ import annotations

from pathlib import Path

import yaml

from ontology_hitl.core.models import ProposedClass, PropertyDef, RelationDef
from ontology_hitl.mapping.yarrrml_generator import YARRRMLGenerator


class TestYARRRMLGenerator:
    """Test YARRRML mapping generation."""

    def _make_class(self) -> ProposedClass:
        return ProposedClass(
            id="prop_001",
            label="Facility",
            definition="A nuclear facility subject to decommissioning.",
            parent_uri="http://purl.org/2024/planning-ontology#DomainConstant",
            parent_label="DomainConstant",
            examples=["KKW Greifswald"],
            frequency=12,
            confidence=0.85,
            suggested_properties=[
                PropertyDef(
                    name="label",
                    datatype="xsd:string",
                    description="Name",
                    required=True,
                    max_count=1,
                ),
                PropertyDef(
                    name="capacity",
                    datatype="xsd:integer",
                    description="Capacity in MW",
                ),
            ],
            suggested_relations=[
                RelationDef(
                    name="requiresPermit",
                    domain="Facility",
                    range="Permit",
                    description="Facility requires a permit",
                ),
            ],
        )

    def test_generate_returns_valid_structure(self) -> None:
        gen = YARRRMLGenerator()
        doc = gen.generate([self._make_class()])
        assert "prefixes" in doc
        assert "mappings" in doc
        assert "Facility" in doc["mappings"]

    def test_mapping_has_source_and_po(self) -> None:
        gen = YARRRMLGenerator()
        doc = gen.generate([self._make_class()])
        mapping = doc["mappings"]["Facility"]
        assert "sources" in mapping
        assert "po" in mapping
        # Must have rdf:type + rdfs:label + 2 properties + 1 relation = 5
        assert len(mapping["po"]) == 5

    def test_write_produces_yaml_file(self, tmp_path: Path) -> None:
        gen = YARRRMLGenerator()
        doc = gen.generate([self._make_class()])
        out = gen.write(doc, tmp_path / "mapping.yml")
        assert out.exists()
        loaded = yaml.safe_load(out.read_text())
        assert "mappings" in loaded

    def test_integer_datatype_in_po(self) -> None:
        gen = YARRRMLGenerator()
        doc = gen.generate([self._make_class()])
        po_list = doc["mappings"]["Facility"]["po"]
        # The capacity property should have xsd:integer suffix
        capacity_po = [p for p in po_list if p[0] == "ex:capacity"]
        assert len(capacity_po) == 1
        assert "xsd:integer" in capacity_po[0][1]

    def test_relation_generates_iri_link(self) -> None:
        gen = YARRRMLGenerator()
        doc = gen.generate([self._make_class()])
        po_list = doc["mappings"]["Facility"]["po"]
        rel_po = [p for p in po_list if p[0] == "ex:requiresPermit"]
        assert len(rel_po) == 1
        assert "~iri" in rel_po[0][1]

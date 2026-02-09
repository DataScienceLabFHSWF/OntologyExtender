"""Shared test fixtures for ontology-hitl."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontology_hitl.core.models import (
    ExtractedEntitySummary,
    GapCandidate,
    ProposedClass,
    PropertyDef,
    ReviewDecision,
)


@pytest.fixture
def sample_entities() -> list[ExtractedEntitySummary]:
    """Sample extracted entities for testing."""
    return [
        ExtractedEntitySummary(
            id="ent_a1b2c3d4e5f6",
            label="Kernkraftwerk Greifswald",
            entity_type="Facility",
            description="A nuclear power plant in Mecklenburg-Vorpommern",
            aliases=["KGR", "Greifswald NPP"],
            confidence=0.87,
            frequency=5,
            source_ids=["chunk_01", "chunk_02"],
            evidence_spans=["Das Kernkraftwerk Greifswald..."],
        ),
        ExtractedEntitySummary(
            id="ent_b2c3d4e5f6a7",
            label="Sicherheitsgenehmigung A-2024",
            entity_type="Permit",
            confidence=0.92,
            frequency=3,
            source_ids=["chunk_03"],
            evidence_spans=["Sicherheitsgenehmigung..."],
        ),
        ExtractedEntitySummary(
            id="ent_c3d4e5f6a7b8",
            label="Demontage",
            entity_type="Action",
            confidence=0.78,
            frequency=8,
            source_ids=["chunk_01", "chunk_04"],
            evidence_spans=["Demontage..."],
        ),
    ]


@pytest.fixture
def sample_gap_candidates() -> list[GapCandidate]:
    """Sample gap candidates for testing."""
    return [
        GapCandidate(
            entity_type="Facility",
            representative_label="Kernkraftwerk Greifswald",
            examples=["KKW Greifswald", "KKW Lubmin", "AKW Stendal"],
            frequency=12,
            avg_confidence=0.85,
        ),
        GapCandidate(
            entity_type="Permit",
            representative_label="Sicherheitsgenehmigung",
            examples=["Genehmigung A-2024", "Betriebserlaubnis"],
            frequency=8,
            avg_confidence=0.90,
        ),
    ]


@pytest.fixture
def sample_proposed_class() -> ProposedClass:
    """Sample proposed class for testing."""
    return ProposedClass(
        id="prop_001",
        label="Facility",
        definition="A nuclear facility subject to decommissioning.",
        parent_uri="http://purl.org/2024/planning-ontology#DomainConstant",
        parent_label="DomainConstant",
        examples=["KKW Greifswald", "KKW Lubmin"],
        frequency=12,
        confidence=0.85,
        suggested_properties=[
            PropertyDef(
                name="label",
                datatype="xsd:string",
                description="Human-readable name",
                required=True,
                max_count=1,
            ),
        ],
    )


@pytest.fixture
def sample_checkpoint(tmp_path: Path) -> Path:
    """Create a sample extraction checkpoint JSON file."""
    checkpoint = {
        "pipeline_run_id": "test_run_001",
        "timestamp": "2026-02-09T10:00:00",
        "ontology_version": "plan-ontology-v1.0",
        "entities": [
            {
                "id": "ent_001",
                "label": "Kernkraftwerk Greifswald",
                "entity_type": "Facility",
                "confidence": 0.87,
                "evidence": [
                    {
                        "chunk_id": "chunk_01",
                        "document": "doc_01.pdf",
                        "text_snippet": "Das Kernkraftwerk Greifswald...",
                    }
                ],
            },
            {
                "id": "ent_002",
                "label": "Sicherheitsgenehmigung",
                "entity_type": "Permit",
                "confidence": 0.92,
                "evidence": [
                    {
                        "chunk_id": "chunk_02",
                        "document": "doc_02.pdf",
                        "text_snippet": "Die Sicherheitsgenehmigung...",
                    }
                ],
            },
            {
                "id": "ent_003",
                "label": "Demontage",
                "entity_type": "Action",
                "confidence": 0.78,
                "evidence": [
                    {
                        "chunk_id": "chunk_03",
                        "document": "doc_03.pdf",
                        "text_snippet": "Die Demontage der Anlage...",
                    },
                    {
                        "chunk_id": "chunk_04",
                        "document": "doc_04.pdf",
                        "text_snippet": "Demontage und Rückbau...",
                    },
                ],
            },
        ],
        "metrics": {
            "total_entities": 3,
            "unique_entity_types": 3,
            "avg_confidence": 0.86,
        },
    }

    path = tmp_path / "extraction_checkpoint.json"
    with open(path, "w") as f:
        json.dump(checkpoint, f, indent=2)
    return path

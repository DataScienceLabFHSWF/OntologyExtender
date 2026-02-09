"""Tests for B — Entity Linker (discovery.entity_linker)."""

from __future__ import annotations

import pytest

from ontology_hitl.discovery.entity_linker import (
    EntityLink,
    EntityLinkReport,
    EntityLinker,
    EXTERNAL_ONTOLOGIES,
)


# ── Data model tests ────────────────────────────────────────────────

def test_entity_link_creation():
    link = EntityLink(
        proposed_label="Facility",
        external_uri="http://www.wikidata.org/entity/Q13226383",
        external_label="facility",
        ontology_source="wikidata",
        similarity_score=0.89,
    )
    assert link.link_type == "seeAlso"
    assert not link.verified


def test_entity_link_report():
    report = EntityLinkReport(
        links=[
            EntityLink(
                proposed_label="Facility",
                external_uri="http://ex.org/F",
                external_label="Facility",
                ontology_source="bfo",
                similarity_score=0.9,
            ),
        ],
        unlinked_classes=["UnknownThing"],
        coverage_pct=0.5,
    )
    assert len(report.links) == 1
    assert report.coverage_pct == 0.5


# ── External ontologies registry ───────────────────────────────────

def test_external_ontologies_registry():
    assert "wikidata" in EXTERNAL_ONTOLOGIES
    assert "bfo" in EXTERNAL_ONTOLOGIES
    assert "emmo" in EXTERNAL_ONTOLOGIES
    assert "schema" in EXTERNAL_ONTOLOGIES
    assert "saref" in EXTERNAL_ONTOLOGIES


# ── Cosine similarity ──────────────────────────────────────────────

def test_cosine_similarity_identical():
    linker = EntityLinker()
    assert linker.cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    linker = EntityLinker()
    assert linker.cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)


def test_cosine_similarity_opposite():
    linker = EntityLinker()
    assert linker.cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)


def test_cosine_similarity_zero_vector():
    linker = EntityLinker()
    assert linker.cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


# ── EntityLinker initialisation ─────────────────────────────────────

def test_linker_init():
    linker = EntityLinker(similarity_threshold=0.8)
    assert linker.similarity_threshold == 0.8


def test_link_classes_empty():
    linker = EntityLinker()
    report = linker.link_classes([])
    assert len(report.links) == 0
    assert report.coverage_pct == 0.0


def test_link_classes_no_embeddings_graceful():
    """Without Ollama running, linker returns empty but doesn't crash."""
    linker = EntityLinker()
    # This will try to call Ollama and fail gracefully
    report = linker.link_classes(["Facility"])
    assert isinstance(report, EntityLinkReport)


# ── Reference-based linking (unit test with mock embeddings) ────────

def test_link_with_reference_terms():
    """Test linking against pre-provided reference terms (no network)."""
    linker = EntityLinker(similarity_threshold=0.5)

    # Manually inject embeddings to bypass Ollama
    linker._embedding_cache["Facility"] = [1.0, 0.0, 0.0]
    linker._embedding_cache["Building"] = [0.95, 0.1, 0.0]
    linker._embedding_cache["Person"] = [0.0, 1.0, 0.0]

    reference = {
        "bfo": [
            {"label": "Building", "uri": "http://bfo.org/Building"},
            {"label": "Person", "uri": "http://bfo.org/Person"},
        ],
    }

    report = linker.link_classes(["Facility"], reference_terms=reference)
    # "Facility" should match "Building" with high similarity
    facility_links = [l for l in report.links if l.proposed_label == "Facility"]
    assert len(facility_links) >= 1
    assert any(l.external_label == "Building" for l in facility_links)

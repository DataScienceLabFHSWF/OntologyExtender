"""Tests for A — Seed Protection Pattern (schema.seed_manager)."""

from __future__ import annotations

import pytest
from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef

from ontology_hitl.schema.seed_manager import (
    MERGED_GRAPH,
    SEED_GRAPH,
    SeedProtectedOntology,
    ext_graph_iri,
    snapshot_graph_iri,
)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def sample_seed(tmp_path):
    """Create a minimal OWL seed ontology file."""
    g = Graph()
    ns = "http://example.org/seed#"
    g.add((URIRef(ns + "Thing"), RDF.type, OWL.Class))
    g.add((URIRef(ns + "Thing"), RDFS.label, Literal("Thing")))
    g.add((URIRef(ns + "Action"), RDF.type, OWL.Class))
    g.add((URIRef(ns + "Action"), RDFS.label, Literal("Action")))
    g.add((URIRef(ns + "Action"), RDFS.subClassOf, URIRef(ns + "Thing")))
    path = tmp_path / "seed.owl"
    g.serialize(str(path), format="xml")
    return path


@pytest.fixture
def spo(sample_seed):
    """A SeedProtectedOntology loaded with the sample seed."""
    spo = SeedProtectedOntology()
    spo.load_seed(sample_seed)
    return spo


# ── Graph IRI helpers ───────────────────────────────────────────────

def test_ext_graph_iri():
    assert ext_graph_iri(1) == "urn:graph:ext-v1"
    assert ext_graph_iri(42) == "urn:graph:ext-v42"


def test_snapshot_graph_iri_custom():
    iri = snapshot_graph_iri("v1-final")
    assert iri == "urn:graph:snapshot-v1-final"


def test_snapshot_graph_iri_auto():
    iri = snapshot_graph_iri()
    assert iri.startswith("urn:graph:snapshot-")


# ── Seed loading ────────────────────────────────────────────────────

def test_load_seed(spo):
    assert len(spo.seed) > 0


def test_seed_classes(spo):
    classes = spo.seed_classes()
    assert len(classes) == 2


def test_seed_class_labels(spo):
    labels = spo.seed_class_labels()
    assert "Thing" in labels.values()
    assert "Action" in labels.values()


# ── Extensions ──────────────────────────────────────────────────────

def test_create_extension(spo):
    g = spo.create_extension(1)
    assert spo.extension_count() == 1
    assert len(g) == 0


def test_add_extension_class(spo):
    spo.create_extension(1)
    spo.add_extension_class(
        version=1,
        class_uri="http://example.org/ext#Facility",
        label="Facility",
        definition="A physical installation.",
        parent_uri="http://example.org/seed#Thing",
    )
    g = spo._extensions[1]
    assert (URIRef("http://example.org/ext#Facility"), RDF.type, OWL.Class) in g
    assert (
        URIRef("http://example.org/ext#Facility"),
        RDFS.subClassOf,
        URIRef("http://example.org/seed#Thing"),
    ) in g


def test_add_extension_class_auto_creates_layer(spo):
    """Adding to a non-existent version auto-creates the layer."""
    spo.add_extension_class(
        version=5,
        class_uri="http://example.org/ext#NewClass",
        label="NewClass",
    )
    assert 5 in spo._extensions


def test_add_disjoint(spo):
    spo.create_extension(1)
    spo.add_extension_class(
        version=1,
        class_uri="http://example.org/ext#X",
        label="X",
        disjoint_with=["http://example.org/ext#Y"],
    )
    g = spo._extensions[1]
    assert (
        URIRef("http://example.org/ext#X"),
        OWL.disjointWith,
        URIRef("http://example.org/ext#Y"),
    ) in g


# ── Merge ───────────────────────────────────────────────────────────

def test_build_merged(spo):
    spo.add_extension_class(
        version=1,
        class_uri="http://example.org/ext#Facility",
        label="Facility",
        parent_uri="http://example.org/seed#Thing",
    )
    merged = spo.build_merged()
    # Should have seed triples + extension triples
    assert len(merged) > len(spo.seed)
    assert (URIRef("http://example.org/ext#Facility"), RDF.type, OWL.Class) in merged


def test_build_merged_up_to_version(spo):
    spo.add_extension_class(version=1, class_uri="http://ex.org/A", label="A")
    spo.add_extension_class(version=2, class_uri="http://ex.org/B", label="B")

    m1 = spo.build_merged(up_to_version=1)
    assert (URIRef("http://ex.org/A"), RDF.type, OWL.Class) in m1
    assert (URIRef("http://ex.org/B"), RDF.type, OWL.Class) not in m1


def test_merged_property(spo):
    """The .merged property auto-builds if needed."""
    merged = spo.merged
    assert len(merged) > 0


# ── Export ──────────────────────────────────────────────────────────

def test_export_merged(spo, tmp_path):
    spo.add_extension_class(version=1, class_uri="http://ex.org/C", label="C")
    out = spo.export_merged(tmp_path / "merged.owl")
    assert out.exists()
    assert out.stat().st_size > 0


def test_export_extension(spo, tmp_path):
    spo.add_extension_class(version=1, class_uri="http://ex.org/D", label="D")
    out = spo.export_extension(1, tmp_path / "ext1.ttl")
    assert out.exists()


def test_export_missing_extension(spo, tmp_path):
    with pytest.raises(KeyError):
        spo.export_extension(99, tmp_path / "nope.ttl")


# ── Validation ──────────────────────────────────────────────────────

def test_validate_parent_in_seed(spo):
    assert spo.validate_parent_exists("http://example.org/seed#Thing")


def test_validate_parent_not_found(spo):
    assert not spo.validate_parent_exists("http://example.org/nonexistent")


def test_validate_parent_in_extension(spo):
    spo.add_extension_class(version=1, class_uri="http://ex.org/E", label="E")
    assert spo.validate_parent_exists("http://ex.org/E")


# ── Summary ─────────────────────────────────────────────────────────

def test_summary(spo):
    spo.add_extension_class(version=1, class_uri="http://ex.org/F", label="F")
    s = spo.summary()
    assert s["seed_classes"] == 2
    assert s["extension_layers"] == 1
    assert s["extension_classes"] == 1

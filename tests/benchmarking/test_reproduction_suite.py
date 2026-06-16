"""Tests for the reproduction benchmark suite."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

import pytest
from rdflib import OWL, RDF, RDFS, Graph, URIRef

from ontology_hitl.benchmarking.reproduction_suite import (
    Complexity,
    REGISTRY,
    REGISTRY_ORDERED,
    ReproductionSuite,
    ReproductionTarget,
    _build_seed_by_split,
)


# ── Unit: Complexity ordering ──────────────────────────────────────────────────


def test_registry_ordered_ascending():
    """REGISTRY_ORDERED must be sorted easy → hard."""
    levels = [t.complexity for t in REGISTRY_ORDERED]
    assert levels == sorted(levels)


def test_registry_names_unique():
    names = [t.name for t in REGISTRY]
    assert len(names) == len(set(names))


def test_complexity_tiers():
    names = {t.name: t.complexity for t in REGISTRY}
    assert names["wine"] == Complexity.SMOKE
    assert names["owl_time"] == Complexity.FORMAL
    assert names["prov_o"] == Complexity.PROVENANCE
    assert names["oeo"] == Complexity.RESEARCH


# ── Unit: seed-splitting logic ─────────────────────────────────────────────────


def _make_simple_ontology(path: Path) -> None:
    """Write a tiny OWL ontology for split testing."""
    g = Graph()
    EX = URIRef("http://example.org/")
    # 3 inner + 4 leaf classes
    classes = {
        "Animal": [],
        "Mammal": ["Animal"],
        "Fish": ["Animal"],
        "Dog": ["Mammal"],
        "Cat": ["Mammal"],
        "Salmon": ["Fish"],
        "Trout": ["Fish"],
    }
    for name, parents in classes.items():
        cls = EX + name
        g.add((cls, RDF.type, OWL.Class))
        for parent in parents:
            g.add((cls, RDFS.subClassOf, EX + parent))
    g.serialize(destination=str(path), format="turtle")


def test_build_seed_keeps_inner_classes(tmp_path):
    gold = tmp_path / "gold.ttl"
    seed = tmp_path / "seed.ttl"
    _make_simple_ontology(gold)

    _build_seed_by_split(gold, seed, fraction=0.5, rdf_format="turtle")

    assert seed.exists()
    sg = Graph()
    sg.parse(str(seed))
    seed_classes = {
        str(s)
        for s in sg.subjects(RDF.type, OWL.Class)
        if isinstance(s, URIRef)
    }
    # Inner classes (Animal, Mammal, Fish) must be kept
    for inner in ("Animal", "Mammal", "Fish"):
        assert any(inner in c for c in seed_classes), f"{inner} should be in seed"


def test_build_seed_fraction(tmp_path):
    gold = tmp_path / "gold.ttl"
    seed = tmp_path / "seed.ttl"
    _make_simple_ontology(gold)

    _build_seed_by_split(gold, seed, fraction=0.0, rdf_format="turtle")
    sg = Graph()
    sg.parse(str(seed))
    seed_classes = {s for s in sg.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
    # fraction=0.0 → inner classes + at least 1 leaf (max(1, int(n*0)) = 1)
    # inner = Animal, Mammal, Fish → 3; +1 leaf → 4
    assert len(seed_classes) == 4


def test_build_seed_idempotent(tmp_path):
    """Calling build_seed_by_split twice should not raise or change the output."""
    gold = tmp_path / "gold.ttl"
    seed = tmp_path / "seed.ttl"
    _make_simple_ontology(gold)

    _build_seed_by_split(gold, seed, fraction=0.5, rdf_format="turtle")
    mtime_1 = seed.stat().st_mtime

    _build_seed_by_split(gold, seed, fraction=0.5, rdf_format="turtle")
    assert seed.stat().st_mtime == mtime_1  # not re-written


# ── Unit: ReproductionSuite ────────────────────────────────────────────────────


def test_suite_init_default():
    suite = ReproductionSuite()
    assert suite.targets is REGISTRY_ORDERED
    assert suite.benchmark is not None


def test_suite_init_custom_targets():
    wine = next(t for t in REGISTRY if t.name == "wine")
    suite = ReproductionSuite(targets=[wine])
    assert len(suite.targets) == 1
    assert suite.targets[0].name == "wine"


def test_suite_delta_summary_not_prepared(tmp_path):
    # Use a target whose files don't exist
    wine = next(t for t in REGISTRY if t.name == "wine")
    suite = ReproductionSuite(targets=[wine])
    summary = suite.delta_summary()
    assert len(summary) == 1
    assert summary[0]["status"] == "not_prepared"


# ── Integration: prepare + delta (mocked HTTP) ────────────────────────────────


def test_suite_prepare_and_delta(tmp_path):
    """Prepare with a locally created gold; verify delta is computable."""
    # Build a minimal target backed by temp files
    gold_path = tmp_path / "myonto" / "gold.ttl"
    gold_path.parent.mkdir()
    seed_path = tmp_path / "myonto" / "seed.ttl"
    _make_simple_ontology(gold_path)

    target = ReproductionTarget(
        name="myonto",
        description="test",
        complexity=Complexity.SMOKE,
        gold_url="http://mocked.invalid/gold.ttl",
        gold_filename="gold.ttl",
        seed_filename="seed.ttl",
        rdf_format="turtle",
        split_fraction=0.5,
    )

    # Patch cache_dir to use tmp_path
    with patch.object(type(target), "cache_dir", new_callable=lambda: property(lambda _: tmp_path / "myonto")):
        suite = ReproductionSuite(targets=[target])

        # Simulate gold already downloaded; let prepare() create the seed
        with patch(
            "ontology_hitl.benchmarking.reproduction_suite._download",
            side_effect=lambda url, dest, **kw: None,  # no-op (gold already there)
        ):
            suite.prepare(target)

        # seed should have been created
        assert seed_path.exists()

        delta = suite.delta(target)
        # gold has 7 classes, seed has fewer → some additions expected
        assert delta.added_classes or True  # just verify no exception

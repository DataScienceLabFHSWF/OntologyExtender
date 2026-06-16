"""Tests for the OEO reproduction benchmark and .omn CQ loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace

from ontology_hitl.benchmarking import (
    OEOBenchmark,
    OntologyDelta,
    ReproductionScore,
    load_cq_directory,
    parse_omn,
)

NS = Namespace("http://ex#")


def _mk(classes, subs=(), props=()):
    g = Graph()
    for c in classes:
        g.add((NS[c], RDF.type, OWL.Class))
    for a, b in subs:
        g.add((NS[a], RDFS.subClassOf, NS[b]))
    for p in props:
        g.add((NS[p], RDF.type, OWL.ObjectProperty))
    return g


@pytest.fixture
def snapshots(tmp_path: Path):
    old = _mk(["Animal", "Dog"], [("Dog", "Animal")])
    new = _mk(
        ["Animal", "Dog", "Cat", "Mammal"],
        [("Dog", "Mammal"), ("Cat", "Mammal"), ("Mammal", "Animal")],
        props=["eats"],
    )
    gen = _mk(["Animal", "Dog", "Cat"], [("Dog", "Animal"), ("Cat", "Animal")])
    paths = {}
    for name, g in (("old", old), ("new", new), ("gen", gen)):
        p = tmp_path / f"{name}.owl"
        g.serialize(str(p), format="xml")
        paths[name] = str(p)
    return paths


_OMN_SAMPLE = """Prefix: : <https://openenergyplatform.org/ontology/oeo/>
Prefix: owl: <http://www.w3.org/2002/07/owl#>
Ontology: <https://openenergyplatform.org/ontology/cc/>

# Do all hot things carry energy?

Class: owl:Nothing
ObjectProperty: obo:RO_0000053
Class: OEO_00000207
EquivalentClasses: ((obo:RO_0000053 some OEO_00000207) and not (obo:RO_0000091 some OEO_00000151)), owl:Nothing
# All bearers of thermal energy are energy carriers
"""


class TestOmnLoader:
    def test_parse_single_file(self, tmp_path: Path):
        f = tmp_path / "competency_questions" / "implementing" / "043_test.omn"
        f.parent.mkdir(parents=True)
        f.write_text(_OMN_SAMPLE)
        cq = parse_omn(f)
        assert cq.id == "043_test"
        assert cq.question == "Do all hot things carry energy?"
        assert cq.category == "implementing"
        assert cq.expected_unsatisfiable is True
        assert "OEO_00000207" in cq.referenced_terms
        assert "RO_0000053" in cq.referenced_terms

    def test_load_directory(self, tmp_path: Path):
        base = tmp_path / "competency_questions"
        for cat, num in (("implementing", "043"), ("physical", "010")):
            f = base / cat / f"{num}_q.omn"
            f.parent.mkdir(parents=True)
            f.write_text(_OMN_SAMPLE)
        cqs = load_cq_directory(base)
        assert len(cqs) == 2
        cats = {c.category for c in cqs}
        assert cats == {"implementing", "physical"}

    def test_category_filter(self, tmp_path: Path):
        base = tmp_path / "competency_questions"
        for cat in ("implementing", "physical"):
            f = base / cat / "q.omn"
            f.parent.mkdir(parents=True)
            f.write_text(_OMN_SAMPLE)
        cqs = load_cq_directory(base, categories=["physical"])
        assert len(cqs) == 1
        assert cqs[0].category == "physical"

    def test_missing_directory_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_cq_directory(tmp_path / "nope")

    def test_to_dict(self, tmp_path: Path):
        f = tmp_path / "competency_questions" / "implementing" / "q.omn"
        f.parent.mkdir(parents=True)
        f.write_text(_OMN_SAMPLE)
        d = parse_omn(f).to_dict()
        assert d["question"]
        assert d["expected_unsatisfiable"] is True


class TestVersionDelta:
    def test_delta_detects_additions(self, snapshots):
        bench = OEOBenchmark()
        delta = bench.version_delta(snapshots["old"], snapshots["new"])
        assert isinstance(delta, OntologyDelta)
        added = {c.split("#")[-1] for c in delta.added_classes}
        assert added == {"Cat", "Mammal"}
        assert any("eats" in p for p in delta.added_properties)
        assert len(delta.added_subclass_axioms) == 3

    def test_delta_to_dict(self, snapshots):
        bench = OEOBenchmark()
        delta = bench.version_delta(snapshots["old"], snapshots["new"])
        d = delta.to_dict()
        assert d["summary"]["added_classes"] == 2


class TestReproductionScore:
    def test_score_against_gold_with_seed(self, snapshots):
        bench = OEOBenchmark()
        score = bench.score_reproduction(
            snapshots["gen"], snapshots["new"], seed_path=snapshots["old"]
        )
        assert isinstance(score, ReproductionScore)
        # gen added Cat (in gold delta) but missed Mammal → precision 1.0, recall 0.5
        assert score.class_precision == pytest.approx(1.0)
        assert score.class_recall == pytest.approx(0.5)
        assert score.consistent is True

    def test_score_to_dict(self, snapshots):
        bench = OEOBenchmark()
        score = bench.score_reproduction(snapshots["gen"], snapshots["new"])
        d = score.to_dict()
        assert "classes" in d and "f1" in d["classes"]

    def test_inconsistent_generated_flagged(self, tmp_path: Path):
        g = _mk(["Animal", "Plant", "Hybrid"])
        g.add((NS.Animal, OWL.disjointWith, NS.Plant))
        g.add((NS.Hybrid, RDFS.subClassOf, NS.Animal))
        g.add((NS.Hybrid, RDFS.subClassOf, NS.Plant))
        gen = tmp_path / "gen.owl"
        g.serialize(str(gen), format="xml")
        gold = tmp_path / "gold.owl"
        _mk(["Animal", "Plant"]).serialize(str(gold), format="xml")
        bench = OEOBenchmark()
        score = bench.score_reproduction(str(gen), str(gold))
        assert score.consistent is False
        assert score.num_logical_issues >= 1


class TestCQEvaluation:
    def test_evaluation_skips_without_reasoner(self, tmp_path: Path, snapshots, monkeypatch):
        # Force the owlready path to be unavailable.
        import ontology_hitl.benchmarking.oeo_benchmark as mod

        monkeypatch.setattr(mod, "_try_owlready_reasoner", lambda p: None)
        f = tmp_path / "competency_questions" / "implementing" / "q.omn"
        f.parent.mkdir(parents=True)
        f.write_text(_OMN_SAMPLE)
        bench = OEOBenchmark()
        cqs = bench.load_competency_questions(tmp_path / "competency_questions")
        result = bench.evaluate_competency_questions(snapshots["new"], cqs)
        assert result.total == 1
        assert result.skipped == 1
        assert result.reasoner == "none"
        assert result.skip_reason

import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef, RDF, RDFS, OWL

from ontology_hitl.benchmarking.metrics import BenchmarkEvaluator
from ontology_hitl.benchmarking.models import (
    CompetencyQuestion,
    TestCase,
    SemanticMatchLevel,
    SemanticMatchResult,
    OWLUnitTestResult,
    OWLUnitTestType,
)
from ontology_hitl.benchmarking.models import ReductionLevel


def _make_graph_with_class_and_individual(class_uri: str, ind_uri: str = None):
    g = Graph()
    cls = URIRef(class_uri)
    g.add((cls, RDF.type, OWL.Class))
    g.add((cls, RDFS.label, Literal(class_uri.split('#')[-1])))
    if ind_uri:
        ind = URIRef(ind_uri)
        g.add((ind, RDF.type, cls))
    return g


def test_extract_concepts_and_spo_triples_basic():
    ev = BenchmarkEvaluator()
    g = Graph()
    cls = URIRef("http://example.org/Heart")
    g.add((cls, RDF.type, OWL.Class))
    g.add((cls, RDFS.label, Literal("Heart")))
    g.add((cls, RDFS.comment, Literal("organ")))

    sub = URIRef("http://example.org/CardiacMuscle")
    g.add((sub, RDF.type, OWL.Class))
    g.add((sub, RDFS.label, Literal("CardiacMuscle")))
    g.add((sub, RDFS.subClassOf, cls))

    concepts = ev._extract_concepts_with_definitions(g)
    assert "Heart" in concepts and concepts["Heart"] == "organ"
    triples = ev._extract_spo_triples(g)
    # subclass should be present as a triple sentence component
    assert ("CardiacMuscle", "subClassOf", "Heart") in triples


def test_score_semantic_match_concepts_token_overlap():
    ev = BenchmarkEvaluator()
    gen = Graph()
    gcls = URIRef("http://example.org/Apple")
    gen.add((gcls, RDF.type, OWL.Class))
    gen.add((gcls, RDFS.label, Literal("Apple")))

    ref = Graph()
    rcls = URIRef("http://example.org/fruit/Apple")
    ref.add((rcls, RDF.type, OWL.Class))
    ref.add((rcls, RDFS.label, Literal("apple")))

    res = ev.score_semantic_match_concepts(gen, {"ref": ref})
    assert isinstance(res, SemanticMatchResult)
    assert res.total_generated == 1
    assert res.total_matched == 1
    assert res.match_percentage == 100.0


def test_score_semantic_match_triples_token_overlap():
    ev = BenchmarkEvaluator()
    gen = Graph()
    s = URIRef("http://example.org/Apple")
    p = URIRef("http://example.org/hasPart")
    o = URIRef("http://example.org/Seed")
    gen.add((s, p, o))

    ref = Graph()
    rs = URIRef("http://example.org/fapple")
    rp = URIRef("http://example.org/hasPart")
    ro = URIRef("http://example.org/seed")
    ref.add((rs, rp, ro))

    res = ev.score_semantic_match_triples(gen, {"ref": ref})
    assert isinstance(res, SemanticMatchResult)
    assert res.total_generated >= 1
    assert res.total_matched >= 1
    assert res.match_percentage > 0.0


def test_generate_cq_verification_tests_and_owlunit_suite(tmp_path: Path):
    ev = BenchmarkEvaluator()
    class_uri = "http://example.org/Fruit"
    ind_uri = "http://example.org/apple1"

    g = Graph()
    cls = URIRef(class_uri)
    g.add((cls, RDF.type, OWL.Class))
    g.add((cls, RDFS.label, Literal("Fruit")))
    ind = URIRef(ind_uri)
    g.add((ind, RDF.type, cls))

    cq = CompetencyQuestion(
        id="cq1",
        question="Is there an apple?",
        target_classes=[class_uri],
        target_properties=[],
        sparql_template=f"SELECT ?s WHERE {{ ?s a <{class_uri}> }}",
    )

    tc = TestCase(
        id="tc1",
        reduction_level=ReductionLevel.PCT_75,
        seed_ontology_path=tmp_path / "seed.owl",
        gold_standard_path=tmp_path / "gold.owl",
        competency_questions=[cq],
    )

    results = ev._generate_cq_verification_tests(tc, g)
    assert len(results) == 1
    assert results[0].passed is True

    # write graph to disk and run score_owlunit_suite (uses rdflib approximation)
    gen_path = tmp_path / "gen.ttl"
    g.serialize(destination=str(gen_path), format="turtle")
    suite = ev.score_owlunit_suite(gen_path, tc)
    assert suite.ontology_path == str(gen_path)
    # at least one CQ test result exists
    assert any(r.test_type == OWLUnitTestType.COMPETENCY_Q for r in suite.results)


def test_competency_question_type_field_is_preserved():
    cq = CompetencyQuestion(
        id="cq2",
        question="Is this a scope question?",
        target_classes=[],
        target_properties=[],
        sparql_template=None,
        cq_type="SCQ",
    )
    assert cq.cq_type == "SCQ"


def test_get_embedding_respects_model_arg(monkeypatch):
    called = {}

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def fake_post(url, json=None, timeout=None):
        # record what model was requested
        called['model'] = json.get('model') if json else None
        return FakeResp({'embeddings': [[0.1, 0.2, 0.3]]})

    monkeypatch.setattr('httpx.post', fake_post)
    ev = BenchmarkEvaluator(embedding_url='http://localhost:18135', embedding_model='gemma4:e2b')
    vec = ev._get_embedding('test text', model='qwen3-embedding')
    assert vec == [0.1, 0.2, 0.3]
    assert called.get('model') == 'qwen3-embedding'
"""Tests for the OWL consistency checker (ontology_hitl.reasoning)."""

from __future__ import annotations

import pytest
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace

from ontology_hitl.reasoning import (
    ConsistencyChecker,
    ConsistencyReport,
    LogicalIssue,
    LogicalIssueKind,
)

NS = Namespace("http://example.org/onto#")


def _class(g: Graph, name: str) -> None:
    g.add((NS[name], RDF.type, OWL.Class))
    g.add((NS[name], RDFS.label, Literal(name)))


@pytest.fixture
def checker() -> ConsistencyChecker:
    return ConsistencyChecker()


class TestConsistentGraphs:
    def test_empty_graph_is_consistent(self, checker):
        report = checker.check_graph(Graph())
        assert report.consistent is True
        assert report.issues == []

    def test_simple_hierarchy_is_consistent(self, checker):
        g = Graph()
        for n in ("Animal", "Mammal", "Dog"):
            _class(g, n)
        g.add((NS.Mammal, RDFS.subClassOf, NS.Animal))
        g.add((NS.Dog, RDFS.subClassOf, NS.Mammal))
        report = checker.check_graph(g)
        assert report.consistent is True
        assert report.num_classes == 3

    def test_disjoint_siblings_are_consistent(self, checker):
        g = Graph()
        for n in ("Animal", "Plant", "Dog"):
            _class(g, n)
        g.add((NS.Animal, OWL.disjointWith, NS.Plant))
        g.add((NS.Dog, RDFS.subClassOf, NS.Animal))
        report = checker.check_graph(g)
        assert report.consistent is True


class TestUnsatisfiableClasses:
    def test_subclass_of_two_disjoint_classes(self, checker):
        g = Graph()
        for n in ("Animal", "Plant", "Hybrid"):
            _class(g, n)
        g.add((NS.Animal, OWL.disjointWith, NS.Plant))
        g.add((NS.Hybrid, RDFS.subClassOf, NS.Animal))
        g.add((NS.Hybrid, RDFS.subClassOf, NS.Plant))
        report = checker.check_graph(g)
        assert report.consistent is False
        kinds = {i.kind for i in report.errors}
        assert LogicalIssueKind.UNSATISFIABLE_CLASS in kinds

    def test_transitive_unsatisfiability(self, checker):
        g = Graph()
        for n in ("A", "B", "Mid", "Leaf"):
            _class(g, n)
        g.add((NS.A, OWL.disjointWith, NS.B))
        g.add((NS.Mid, RDFS.subClassOf, NS.A))
        g.add((NS.Leaf, RDFS.subClassOf, NS.Mid))
        g.add((NS.Leaf, RDFS.subClassOf, NS.B))
        report = checker.check_graph(g)
        assert report.consistent is False


class TestDisjointnessViolation:
    def test_disjoint_with_superclass(self, checker):
        g = Graph()
        for n in ("Animal", "Weird"):
            _class(g, n)
        g.add((NS.Weird, RDFS.subClassOf, NS.Animal))
        g.add((NS.Weird, OWL.disjointWith, NS.Animal))
        report = checker.check_graph(g)
        assert report.consistent is False
        assert any(
            i.kind == LogicalIssueKind.DISJOINTNESS_VIOLATION for i in report.errors
        )


class TestSubclassCycles:
    def test_two_class_cycle(self, checker):
        g = Graph()
        for n in ("A", "B"):
            _class(g, n)
        g.add((NS.A, RDFS.subClassOf, NS.B))
        g.add((NS.B, RDFS.subClassOf, NS.A))
        report = checker.check_graph(g)
        assert any(
            i.kind == LogicalIssueKind.SUBCLASS_CYCLE for i in report.issues
        )

    def test_declared_equivalence_is_not_a_cycle(self, checker):
        g = Graph()
        for n in ("A", "B"):
            _class(g, n)
        g.add((NS.A, RDFS.subClassOf, NS.B))
        g.add((NS.B, RDFS.subClassOf, NS.A))
        g.add((NS.A, OWL.equivalentClass, NS.B))
        report = checker.check_graph(g)
        assert not any(
            i.kind == LogicalIssueKind.SUBCLASS_CYCLE for i in report.issues
        )


class TestDomainRangeConflict:
    def test_disjoint_domains(self, checker):
        g = Graph()
        for n in ("Animal", "Plant"):
            _class(g, n)
        g.add((NS.Animal, OWL.disjointWith, NS.Plant))
        g.add((NS.eats, RDF.type, OWL.ObjectProperty))
        g.add((NS.eats, RDFS.domain, NS.Animal))
        g.add((NS.eats, RDFS.domain, NS.Plant))
        report = checker.check_graph(g)
        assert any(
            i.kind == LogicalIssueKind.DOMAIN_RANGE_CONFLICT for i in report.errors
        )


class TestProposalMaterialisation:
    def test_consistent_proposal(self, checker):
        proposal = {
            "classes": [
                {"label": "Animal"},
                {"label": "Dog", "parent_label": "Animal"},
            ]
        }
        report = checker.check_proposal(proposal)
        assert report.consistent is True

    def test_inconsistent_proposal(self, checker):
        proposal = {
            "classes": [
                {"label": "Animal", "disjoint_with": ["Plant"]},
                {"label": "Plant"},
                {"label": "Weird", "parent_label": "Animal", "disjoint_with": ["Animal"]},
            ]
        }
        report = checker.check_proposal(proposal)
        assert report.consistent is False
        assert len(report.errors) >= 1

    def test_proposal_with_seed_graph(self, checker):
        seed = Graph()
        _class(seed, "Animal")
        _class(seed, "Plant")
        seed.add((NS.Animal, OWL.disjointWith, NS.Plant))
        # New class subclasses a seed class but is disjoint with it.
        proposal = {
            "classes": [
                {
                    "label": "Animal",
                    "uri": str(NS.Animal),
                    "disjoint_with": [str(NS.Plant)],
                },
            ],
            "nodes": [
                {
                    "label": "Contradiction",
                    "uri": str(NS.Contradiction),
                    "parent_uri": str(NS.Animal),
                    "disjoint_with": [str(NS.Animal)],
                },
            ],
        }
        report = checker.check_proposal(proposal, seed_graph=seed)
        assert report.consistent is False

    def test_alternate_key_names(self, checker):
        proposal = {
            "nodes": [{"name": "Thing1"}],
            "terms": [{"term": "Thing2", "parent": "Thing1"}],
        }
        report = checker.check_proposal(proposal)
        assert report.consistent is True
        assert report.num_classes >= 2


class TestReportSerialisation:
    def test_to_dict_round_trip(self, checker):
        g = Graph()
        for n in ("Animal", "Plant", "Hybrid"):
            _class(g, n)
        g.add((NS.Animal, OWL.disjointWith, NS.Plant))
        g.add((NS.Hybrid, RDFS.subClassOf, NS.Animal))
        g.add((NS.Hybrid, RDFS.subClassOf, NS.Plant))
        report = checker.check_graph(g)
        d = report.to_dict()
        assert d["consistent"] is False
        assert isinstance(d["issues"], list)
        assert d["issues"][0]["kind"]

    def test_logical_issue_to_dict(self):
        issue = LogicalIssue(
            kind=LogicalIssueKind.UNSATISFIABLE_CLASS,
            severity="error",
            message="x",
            affected=["a", "b"],
        )
        d = issue.to_dict()
        assert d["kind"] == "unsatisfiable_class"
        assert d["affected"] == ["a", "b"]


class TestManualClosureFallback:
    def test_manual_closure_detects_unsat(self):
        checker = ConsistencyChecker(use_owlrl=False)
        g = Graph()
        for n in ("A", "B", "Mid", "Leaf"):
            _class(g, n)
        g.add((NS.A, OWL.disjointWith, NS.B))
        g.add((NS.Mid, RDFS.subClassOf, NS.A))
        g.add((NS.Leaf, RDFS.subClassOf, NS.Mid))
        g.add((NS.Leaf, RDFS.subClassOf, NS.B))
        report = checker.check_graph(g)
        assert report.reasoner == "manual"
        assert report.consistent is False

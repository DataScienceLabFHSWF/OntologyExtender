"""Tests for Ontology 101 methodology prompts and data models."""

from __future__ import annotations

import pytest

from ontology_hitl.methodology.ontology101 import (
    AgentQuestion,
    ClassHierarchy,
    DomainTerm,
    FacetSpec,
    HierarchyNode,
    Ont101Iteration,
    OntologyScope,
    Phase,
    PropertyProposal,
    ReuseCandidate,
    ReuseReport,
    TermEnumeration,
    SampleInstance,
    ValidationReport,
)
from ontology_hitl.methodology.prompts import PhasePrompt, get_prompt


# ── Phase enum ──────────────────────────────────────────────────────

class TestPhaseEnum:
    def test_all_seven_phases(self):
        assert len(Phase) == 7

    def test_phase_ordering(self):
        phases = list(Phase)
        assert phases[0] == Phase.SCOPE
        assert phases[-1] == Phase.INSTANCES


# ── Data models ─────────────────────────────────────────────────────

class TestAgentQuestion:
    def test_defaults(self):
        q = AgentQuestion(
            phase=Phase.SCOPE,
            question="Is nuclear decommissioning in scope?",
            context="Found 50 documents about decommissioning.",
        )
        assert q.answer is None
        assert q.auto_resolved is False
        assert q.options == []

    def test_with_options(self):
        q = AgentQuestion(
            phase=Phase.HIERARCHY,
            question="Should Pump be a subclass of Equipment?",
            context="Documents mention pumps as equipment types.",
            options=["Yes", "No", "Needs discussion"],
            default="Yes",
        )
        assert len(q.options) == 3
        assert q.default == "Yes"


class TestOntologyScope:
    def test_defaults(self):
        s = OntologyScope()
        assert s.domain == ""
        assert s.competency_questions == []
        assert s.language == "en"

    def test_filled(self):
        s = OntologyScope(
            domain="Nuclear decommissioning",
            purpose="Guide KG construction for planning",
            competency_questions=[{"id": "CQ_001", "question": "test?"}],
            out_of_scope=["Financial modeling"],
        )
        assert len(s.competency_questions) == 1


class TestDomainTerm:
    def test_default_category(self):
        t = DomainTerm(term="Pump")
        assert t.category == "unknown"
        assert t.frequency == 1

    def test_with_synonyms(self):
        t = DomainTerm(
            term="Radioactive waste",
            category="class",
            synonyms=["RadWaste", "nuclear waste"],
        )
        assert len(t.synonyms) == 2


class TestHierarchyNode:
    def test_default_strategy(self):
        n = HierarchyNode(uri="plan:Pump", label="Pump")
        assert n.strategy == "middle-out"
        assert n.is_from_seed is False
        assert n.disjoint_with == []


class TestPropertyProposal:
    def test_datatype_property(self):
        p = PropertyProposal(
            name="weight",
            attached_to_class="Equipment",
            property_type="datatype",
            datatype="xsd:float",
        )
        assert p.range_class is None

    def test_object_property(self):
        p = PropertyProposal(
            name="hasComponent",
            attached_to_class="Equipment",
            property_type="object",
            range_class="Component",
            inverse_name="isComponentOf",
        )
        assert p.inverse_name == "isComponentOf"


class TestOnt101Iteration:
    def test_empty_iteration(self):
        it = Ont101Iteration(iteration=1)
        assert it.scope is None
        assert it.questions == []
        assert it.properties == []


# ── Prompts ─────────────────────────────────────────────────────────

class TestPrompts:
    def test_get_prompt_all_phases(self):
        """Every phase should return a valid prompt."""
        for phase in Phase:
            prompt = get_prompt(phase)
            assert isinstance(prompt, PhasePrompt)
            assert prompt.phase == phase
            assert len(prompt.system) > 50
            assert len(prompt.user) > 50

    def test_context_substitution(self):
        prompt = get_prompt(
            Phase.SCOPE,
            document_excerpts="This is a test document about pumps.",
            seed_classes="Equipment, Pump, Valve",
        )
        assert "test document about pumps" in prompt.user
        assert "Equipment, Pump, Valve" in prompt.user

    def test_missing_context_uses_placeholder(self):
        prompt = get_prompt(Phase.SCOPE)
        assert "(not provided)" in prompt.user

    def test_system_prompt_includes_identity(self):
        prompt = get_prompt(Phase.HIERARCHY)
        assert "Noy & McGuinness" in prompt.system
        assert "ontology engineer" in prompt.system.lower()

    def test_hierarchy_prompt_encodes_rules(self):
        prompt = get_prompt(Phase.HIERARCHY)
        assert "IS-A" in prompt.system or "is-a" in prompt.system
        assert "single subclass" in prompt.system.lower() or "SINGLE SUBCLASS" in prompt.system
        assert "disjoint" in prompt.system.lower()

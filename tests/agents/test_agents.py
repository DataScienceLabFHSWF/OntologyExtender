"""Tests for the multi-agent ontology development system."""

from __future__ import annotations

import pytest

from ontology_hitl.agents.base import (
    AgentMessage,
    AgentRole,
    BaseAgent,
    Debate,
    DebateOutcome,
    DebateVerdict,
)
from ontology_hitl.agents.ontology_engineer import OntologyEngineerAgent
from ontology_hitl.agents.domain_expert import DomainExpertAgent
from ontology_hitl.agents.critic import CriticAgent
from ontology_hitl.agents.team import AgentTeam
from ontology_hitl.methodology.ontology101 import AgentQuestion, Phase


# ── AgentRole enum ──────────────────────────────────────────────────

class TestAgentRole:
    def test_three_roles(self):
        assert len(AgentRole) == 4

    def test_role_values(self):
        assert AgentRole.ONTOLOGY_ENGINEER.value == "ontology_engineer"
        assert AgentRole.DOMAIN_EXPERT.value == "domain_expert"
        assert AgentRole.CRITIC.value == "critic"
        assert AgentRole.REASONER.value == "reasoner"


# ── DebateVerdict ───────────────────────────────────────────────────

class TestDebateVerdict:
    def test_four_verdicts(self):
        assert len(DebateVerdict) == 4

    def test_verdict_values(self):
        assert DebateVerdict.CONSENSUS.value == "consensus"
        assert DebateVerdict.REVISED.value == "revised"
        assert DebateVerdict.ESCALATED.value == "escalated"
        assert DebateVerdict.PARTIAL.value == "partial"


# ── AgentMessage ────────────────────────────────────────────────────

class TestAgentMessage:
    def test_proposal_message(self):
        msg = AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.SCOPE,
            message_type="proposal",
            content={"domain": "nuclear decommissioning"},
        )
        assert msg.role == AgentRole.ONTOLOGY_ENGINEER
        assert msg.phase == Phase.SCOPE
        assert msg.message_type == "proposal"
        assert msg.approves is None
        assert msg.issues_raised == []

    def test_review_message(self):
        msg = AgentMessage(
            role=AgentRole.DOMAIN_EXPERT,
            phase=Phase.HIERARCHY,
            message_type="review",
            content={"approves": False},
            reasoning="Missing pump classification",
            issues_raised=["Pump should be under RotatingEquipment"],
            approves=False,
        )
        assert not msg.approves
        assert len(msg.issues_raised) == 1

    def test_revision_message(self):
        msg = AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.HIERARCHY,
            message_type="revision",
            content={"nodes": [{"label": "Pump", "parent": "RotatingEquipment"}]},
            reasoning="Moved Pump under RotatingEquipment per expert feedback",
        )
        assert msg.message_type == "revision"


# ── Debate ──────────────────────────────────────────────────────────

class TestDebate:
    def test_empty_debate(self):
        d = Debate(phase=Phase.SCOPE)
        assert d.latest_proposal is None
        assert d.reviews == []
        assert not d.has_consensus
        assert d.unresolved_issues == []

    def test_latest_proposal(self):
        d = Debate(phase=Phase.SCOPE)
        d.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.SCOPE,
            message_type="proposal",
            content={"domain": "v1"},
        ))
        assert d.latest_proposal == {"domain": "v1"}

        d.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.SCOPE,
            message_type="revision",
            content={"domain": "v2"},
        ))
        assert d.latest_proposal == {"domain": "v2"}

    def test_consensus_detection(self):
        d = Debate(phase=Phase.SCOPE)
        # Proposal
        d.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.SCOPE,
            message_type="proposal",
            content={"domain": "test"},
        ))
        # Both reviewers approve
        d.add_message(AgentMessage(
            role=AgentRole.DOMAIN_EXPERT,
            phase=Phase.SCOPE,
            message_type="review",
            content={},
            approves=True,
        ))
        d.add_message(AgentMessage(
            role=AgentRole.CRITIC,
            phase=Phase.SCOPE,
            message_type="review",
            content={},
            approves=True,
        ))
        assert d.has_consensus

    def test_no_consensus_when_rejected(self):
        d = Debate(phase=Phase.SCOPE)
        d.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.SCOPE,
            message_type="proposal",
            content={"domain": "test"},
        ))
        d.add_message(AgentMessage(
            role=AgentRole.DOMAIN_EXPERT,
            phase=Phase.SCOPE,
            message_type="review",
            content={},
            approves=True,
        ))
        d.add_message(AgentMessage(
            role=AgentRole.CRITIC,
            phase=Phase.SCOPE,
            message_type="review",
            content={},
            approves=False,
            issues_raised=["Naming inconsistency"],
        ))
        assert not d.has_consensus

    def test_unresolved_issues(self):
        d = Debate(phase=Phase.HIERARCHY)
        d.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.HIERARCHY,
            message_type="proposal",
            content={},
        ))
        d.add_message(AgentMessage(
            role=AgentRole.DOMAIN_EXPERT,
            phase=Phase.HIERARCHY,
            message_type="review",
            content={},
            approves=False,
            issues_raised=["Missing Pump class", "Wrong hierarchy"],
        ))
        d.add_message(AgentMessage(
            role=AgentRole.CRITIC,
            phase=Phase.HIERARCHY,
            message_type="review",
            content={},
            approves=False,
            issues_raised=["Naming issue"],
        ))
        assert len(d.unresolved_issues) == 3

    def test_issues_resolved_by_revision(self):
        d = Debate(phase=Phase.HIERARCHY)
        d.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.HIERARCHY,
            message_type="proposal",
            content={},
        ))
        d.add_message(AgentMessage(
            role=AgentRole.DOMAIN_EXPERT,
            phase=Phase.HIERARCHY,
            message_type="review",
            content={},
            issues_raised=["Missing Pump class"],
            approves=False,
        ))
        # Engineer revises, mentioning the issue in reasoning
        d.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.HIERARCHY,
            message_type="revision",
            content={"nodes": [{"label": "Pump"}]},
            reasoning="Added missing pump class as requested",
        ))
        assert len(d.unresolved_issues) == 0


# ── DebateOutcome ───────────────────────────────────────────────────

class TestDebateOutcome:
    def test_consensus_outcome(self):
        o = DebateOutcome(
            phase=Phase.SCOPE,
            verdict=DebateVerdict.CONSENSUS,
            final_proposal={"domain": "nuclear decommissioning"},
            rounds=1,
        )
        assert o.verdict == DebateVerdict.CONSENSUS
        assert o.escalated_questions == []
        assert o.resolved_issues == []

    def test_escalated_outcome(self):
        q = AgentQuestion(
            phase=Phase.HIERARCHY,
            question="Competing valid hierarchies",
            context="Engineer and expert disagree",
        )
        o = DebateOutcome(
            phase=Phase.HIERARCHY,
            verdict=DebateVerdict.ESCALATED,
            final_proposal={},
            escalated_questions=[q],
            rounds=2,
        )
        assert len(o.escalated_questions) == 1
        assert o.rounds == 2


# ── Agent construction ──────────────────────────────────────────────

class TestAgentConstruction:
    def test_engineer_role(self):
        agent = OntologyEngineerAgent()
        assert agent.role == AgentRole.ONTOLOGY_ENGINEER
        assert "ONTOLOGY ENGINEER" in agent.system_prompt
        assert "Noy & McGuinness" in agent.system_prompt

    def test_domain_expert_role(self):
        agent = DomainExpertAgent(document_context="Test documents about pumps")
        assert agent.role == AgentRole.DOMAIN_EXPERT
        assert "DOMAIN EXPERT" in agent.system_prompt
        assert agent.document_context == "Test documents about pumps"

    def test_domain_expert_set_documents(self):
        agent = DomainExpertAgent()
        assert agent.document_context == ""
        agent.set_documents("Updated documents")
        assert agent.document_context == "Updated documents"

    def test_critic_role(self):
        agent = CriticAgent()
        assert agent.role == AgentRole.CRITIC
        assert "CRITIC" in agent.system_prompt
        assert agent.competency_questions == []

    def test_critic_set_cqs(self):
        agent = CriticAgent()
        cqs = [{"id": "CQ1", "question": "What pumps are in the plant?"}]
        agent.set_competency_questions(cqs)
        assert len(agent.competency_questions) == 1


# ── AgentTeam ───────────────────────────────────────────────────────

class TestAgentTeam:
    def test_team_creation(self):
        team = AgentTeam(document_context="Test docs")
        assert isinstance(team.engineer, OntologyEngineerAgent)
        assert isinstance(team.domain_expert, DomainExpertAgent)
        assert isinstance(team.critic, CriticAgent)
        assert team.domain_expert.document_context == "Test docs"

    def test_set_document_context(self):
        team = AgentTeam()
        team.set_document_context("New docs")
        assert team.domain_expert.document_context == "New docs"

    def test_set_competency_questions(self):
        team = AgentTeam()
        cqs = [{"id": "CQ1", "question": "What is X?"}]
        team.set_competency_questions(cqs)
        assert team.critic.competency_questions == cqs

    def test_build_scope_context(self):
        team = AgentTeam()
        ctx = team.build_scope_context("docs text", "Equipment, Pump")
        assert "docs text" in ctx
        assert "Equipment, Pump" in ctx
        assert "competency questions" in ctx.lower()

    def test_build_reuse_context(self):
        team = AgentTeam()
        ctx = team.build_reuse_context("Cls", "Props", "terms", "cqs")
        assert "Cls" in ctx
        assert "Props" in ctx
        assert "terms" in ctx

    def test_build_terms_context(self):
        team = AgentTeam()
        ctx = team.build_terms_context("docs about reactors", "Reactor")
        assert "reactors" in ctx
        assert "Reactor" in ctx

    def test_build_hierarchy_context(self):
        team = AgentTeam()
        ctx = team.build_hierarchy_context("seed hier", ["Pump", "Valve"], "CQs")
        assert "Pump" in ctx
        assert "Valve" in ctx
        assert "seed hier" in ctx

    def test_build_properties_context(self):
        team = AgentTeam()
        ctx = team.build_properties_context("hier", ["weight"], ["hasPart"], "docs")
        assert "weight" in ctx
        assert "hasPart" in ctx

    def test_build_facets_context(self):
        team = AgentTeam()
        ctx = team.build_facets_context("props", "hier")
        assert "props" in ctx
        assert "hier" in ctx

    def test_build_instances_context(self):
        team = AgentTeam()
        ctx = team.build_instances_context("cls", "props", "facets", "cqs", "docs")
        assert "cls" in ctx
        assert "props" in ctx

    def test_finalize_debate_no_issues(self):
        """When all issues are resolved, verdict should be REVISED."""
        team = AgentTeam()
        debate = Debate(phase=Phase.SCOPE, max_rounds=2)
        debate.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.SCOPE,
            message_type="proposal",
            content={"domain": "test"},
        ))
        debate.add_message(AgentMessage(
            role=AgentRole.DOMAIN_EXPERT,
            phase=Phase.SCOPE,
            message_type="review",
            content={},
            approves=True,
        ))
        outcome = team._finalize_debate(debate)
        assert outcome.verdict == DebateVerdict.REVISED
        assert outcome.escalated_questions == []

    def test_finalize_debate_with_escalation(self):
        """When unresolved issues remain, they should be escalated."""
        team = AgentTeam()
        debate = Debate(phase=Phase.HIERARCHY, max_rounds=2)
        debate.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.HIERARCHY,
            message_type="proposal",
            content={},
        ))
        debate.add_message(AgentMessage(
            role=AgentRole.DOMAIN_EXPERT,
            phase=Phase.HIERARCHY,
            message_type="review",
            content={},
            approves=False,
            issues_raised=["Missing class A", "Missing class B", "Missing class C"],
        ))
        outcome = team._finalize_debate(debate)
        assert outcome.verdict == DebateVerdict.ESCALATED
        assert len(outcome.escalated_questions) == 3

    def test_finalize_debate_partial(self):
        """Few unresolved issues → PARTIAL verdict."""
        team = AgentTeam()
        debate = Debate(phase=Phase.TERMS, max_rounds=2)
        debate.add_message(AgentMessage(
            role=AgentRole.ONTOLOGY_ENGINEER,
            phase=Phase.TERMS,
            message_type="proposal",
            content={},
        ))
        debate.add_message(AgentMessage(
            role=AgentRole.CRITIC,
            phase=Phase.TERMS,
            message_type="review",
            content={},
            approves=False,
            issues_raised=["Minor naming issue"],
        ))
        outcome = team._finalize_debate(debate)
        assert outcome.verdict == DebateVerdict.PARTIAL
        assert len(outcome.escalated_questions) == 1


# ── BaseAgent LLM helpers ──────────────────────────────────────────

class TestBaseAgentParsing:
    """Test the LLM response parsing logic (mocked)."""

    def test_agent_has_settings(self):
        agent = OntologyEngineerAgent()
        assert agent.settings is not None
        assert hasattr(agent.settings, "ollama_url")

    def test_agent_system_prompts_differ(self):
        eng = OntologyEngineerAgent()
        exp = DomainExpertAgent()
        critic = CriticAgent()
        # Each agent has a unique identity
        assert eng.system_prompt != exp.system_prompt
        assert exp.system_prompt != critic.system_prompt
        assert eng.system_prompt != critic.system_prompt

    def test_engineer_phase_prompts(self):
        """Engineer should have prompts for all 7 phases."""
        from ontology_hitl.agents.ontology_engineer import _PHASE_PROMPTS
        assert len(_PHASE_PROMPTS) == 7
        for phase in Phase:
            assert phase in _PHASE_PROMPTS
            assert "ONTOLOGY ENGINEER" in _PHASE_PROMPTS[phase]

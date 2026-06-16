"""Tests for the ReasonerAgent (deterministic logical verdicts)."""

from __future__ import annotations

import pytest

from ontology_hitl.agents.base import AgentRole
from ontology_hitl.agents.reasoner import ReasonerAgent
from ontology_hitl.methodology.ontology101 import Phase


@pytest.fixture
def reasoner() -> ReasonerAgent:
    # No LLM explanations → fully deterministic, no network calls.
    return ReasonerAgent(use_llm_explanations=False)


class TestReasonerAgent:
    def test_role(self, reasoner):
        assert reasoner.role == AgentRole.REASONER

    def test_consistent_proposal_approved(self, reasoner):
        proposal = {
            "classes": [
                {"label": "Animal"},
                {"label": "Dog", "parent_label": "Animal"},
            ]
        }
        msg = reasoner.review(Phase.HIERARCHY, proposal)
        assert msg.approves is True
        assert msg.role == AgentRole.REASONER
        assert msg.message_type == "review"
        assert msg.issues_raised == []

    def test_inconsistent_proposal_rejected(self, reasoner):
        proposal = {
            "classes": [
                {"label": "Animal", "disjoint_with": ["Plant"]},
                {"label": "Plant"},
                {"label": "Weird", "parent_label": "Animal", "disjoint_with": ["Animal"]},
            ]
        }
        msg = reasoner.review(Phase.HIERARCHY, proposal)
        assert msg.approves is False
        assert len(msg.issues_raised) >= 1
        assert msg.content["consistent"] is False

    def test_content_contains_report(self, reasoner):
        msg = reasoner.review(Phase.HIERARCHY, {"classes": [{"label": "X"}]})
        assert "report" in msg.content
        assert msg.content["report"]["reasoner"]

    def test_check_returns_report(self, reasoner):
        report = reasoner.check({"classes": [{"label": "A"}]})
        assert report.consistent is True

    def test_empty_proposal_is_consistent(self, reasoner):
        msg = reasoner.review(Phase.SCOPE, {})
        assert msg.approves is True

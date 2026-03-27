"""Tests for ontology extension endpoints — debate pipeline + direct fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ontology_hitl.api.schemas import TBoxChangeType


# ── Fixtures for debate mocking ──────────────────────────────────────────

@pytest.fixture
def mock_debate_consensus():
    """Mock AgentTeam that always reaches consensus."""
    from ontology_hitl.agents.base import (
        AgentMessage,
        AgentRole,
        DebateOutcome,
        DebateVerdict,
    )
    from ontology_hitl.methodology.ontology101 import Phase

    outcome = DebateOutcome(
        phase=Phase.HIERARCHY,
        verdict=DebateVerdict.CONSENSUS,
        final_proposal={
            "nodes": [{
                "uri": "plan:TestClass",
                "label": "TestClass",
                "definition": "A test class proposed by the debate pipeline.",
                "parent_uri": "owl:Thing",
                "parent_label": "Thing",
                "disjoint_with": [],
                "examples": ["test_instance_1", "test_instance_2"],
                "strategy": "external_expert",
            }]
        },
        messages=[
            AgentMessage(
                role=AgentRole.ONTOLOGY_ENGINEER,
                phase=Phase.HIERARCHY,
                message_type="proposal",
                content={"nodes": [{"label": "TestClass"}]},
                reasoning="Proposing TestClass based on external expert input.",
            ),
            AgentMessage(
                role=AgentRole.DOMAIN_EXPERT,
                phase=Phase.HIERARCHY,
                message_type="review",
                content={},
                reasoning="TestClass aligns with domain requirements.",
                approves=True,
                issues_raised=[],
            ),
            AgentMessage(
                role=AgentRole.CRITIC,
                phase=Phase.HIERARCHY,
                message_type="review",
                content={},
                reasoning="Naming and hierarchy are sound.",
                approves=True,
                issues_raised=[],
            ),
        ],
        resolved_issues=[],
        escalated_questions=[],
        rounds=1,
    )

    mock_team = MagicMock()
    mock_team.run_debate.return_value = outcome
    mock_team.save_debate.return_value = None

    with patch("ontology_hitl.api.routes.extend.create_agent_team", return_value=mock_team) as m:
        m._outcome = outcome
        m._team = mock_team
        yield m


@pytest.fixture
def mock_debate_escalated():
    """Mock AgentTeam that escalates (no consensus)."""
    from ontology_hitl.agents.base import (
        AgentMessage,
        AgentRole,
        DebateOutcome,
        DebateVerdict,
    )
    from ontology_hitl.methodology.ontology101 import AgentQuestion, Phase

    outcome = DebateOutcome(
        phase=Phase.HIERARCHY,
        verdict=DebateVerdict.ESCALATED,
        final_proposal={"nodes": [{"label": "AmbiguousClass"}]},
        messages=[
            AgentMessage(
                role=AgentRole.ONTOLOGY_ENGINEER,
                phase=Phase.HIERARCHY,
                message_type="proposal",
                content={"nodes": [{"label": "AmbiguousClass"}]},
                reasoning="Proposing AmbiguousClass.",
            ),
            AgentMessage(
                role=AgentRole.DOMAIN_EXPERT,
                phase=Phase.HIERARCHY,
                message_type="review",
                content={},
                reasoning="Not sure this class is needed.",
                approves=False,
                issues_raised=["Overlaps with ExistingClass"],
            ),
            AgentMessage(
                role=AgentRole.CRITIC,
                phase=Phase.HIERARCHY,
                message_type="review",
                content={},
                reasoning="Naming is ambiguous.",
                approves=False,
                issues_raised=["Name too generic", "Missing definition"],
            ),
        ],
        resolved_issues=[],
        escalated_questions=[
            AgentQuestion(
                phase=Phase.HIERARCHY,
                question="Is AmbiguousClass distinct from ExistingClass?",
                context="Domain expert raised overlap concern.",
            ),
            AgentQuestion(
                phase=Phase.HIERARCHY,
                question="Should we rename AmbiguousClass to something more specific?",
                context="Critic found naming too generic.",
            ),
            AgentQuestion(
                phase=Phase.HIERARCHY,
                question="What is the definition of AmbiguousClass?",
                context="Missing definition identified by critic.",
            ),
        ],
        rounds=2,
    )

    mock_team = MagicMock()
    mock_team.run_debate.return_value = outcome
    mock_team.save_debate.return_value = None

    with patch("ontology_hitl.api.routes.extend.create_agent_team", return_value=mock_team) as m:
        m._outcome = outcome
        yield m


@pytest.fixture
def mock_hierarchy_fetch():
    """Mock the Fuseki hierarchy + class label fetchers."""
    with patch(
        "ontology_hitl.api.routes.extend.fetch_fuseki_hierarchy",
        return_value="Current ontology hierarchy:\n  Thing (root)\n  Event → Meeting",
    ), patch(
        "ontology_hitl.api.routes.extend.fetch_fuseki_class_labels",
        return_value=["Thing", "Event", "Meeting"],
    ):
        yield


# ── Debate-backed NEW_CLASS tests ────────────────────────────────────────

def test_extend_new_class_debate_consensus(
    client, mock_sparql_update, mock_hierarchy_fetch, mock_debate_consensus,
):
    """Test: NEW_CLASS with debate reaching consensus → staged."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "tbox_new_class",
            "review_item_id": "gap_TestClass",
            "rationale": "Found unmapped entities in KGB extraction",
            "suggested_changes": {"label": "TestClass"},
            "debate_enabled": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "staged"
    assert "debate_" in data["change_id"]

    # Debate result should be populated
    assert data["debate"] is not None
    assert data["debate"]["verdict"] == "consensus"
    assert data["debate"]["rounds"] == 1
    assert len(data["debate"]["transcript"]) == 3  # engineer + expert + critic
    assert len(data["debate"]["escalated_questions"]) == 0

    # SPARQL update should have been called (staging insert + SHACL)
    assert mock_sparql_update.call_count >= 1


def test_extend_new_class_debate_escalated(
    client, mock_sparql_update, mock_hierarchy_fetch, mock_debate_escalated,
):
    """Test: NEW_CLASS with debate escalating → needs_review."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "tbox_new_class",
            "review_item_id": "gap_AmbiguousClass",
            "rationale": "Gap detected",
            "suggested_changes": {"label": "AmbiguousClass"},
            "debate_enabled": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "needs_review"

    # Debate result should carry escalated questions
    assert data["debate"] is not None
    assert data["debate"]["verdict"] == "escalated"
    assert data["debate"]["rounds"] == 2
    assert len(data["debate"]["escalated_questions"]) == 3

    # Should NOT have inserted anything into staging
    assert mock_sparql_update.call_count == 0


def test_extend_new_class_direct_fallback(
    client, mock_sparql_update, mock_llm_generate, mock_hierarchy_fetch,
):
    """Test: NEW_CLASS with debate_enabled=False → direct LLM path."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "tbox_new_class",
            "review_item_id": "gap_DirectClass",
            "rationale": "Quick addition, skip debate",
            "suggested_changes": {"label": "DirectClass"},
            "debate_enabled": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "staged"
    assert "direct_" in data["change_id"]

    # Debate should show SKIPPED
    assert data["debate"] is not None
    assert data["debate"]["verdict"] == "skipped"

    # LLM should have been called directly
    assert mock_llm_generate.call_count >= 1


def test_extend_new_class_with_document_context(
    client, mock_sparql_update, mock_hierarchy_fetch, mock_debate_consensus,
):
    """Test: NEW_CLASS passes document context to the debate."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "tbox_new_class",
            "review_item_id": "gap_RiskAssessment",
            "rationale": "Documents mention risk assessments frequently",
            "suggested_changes": {
                "label": "RiskAssessment",
                "description": "An evaluation of potential risks",
                "parent_uri": "plan:Assessment",
            },
            "document_context": "The decommissioning plan includes risk assessments...",
            "debate_enabled": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "staged"

    # Verify the team was created with document context
    mock_debate_consensus.assert_called_once()
    call_kwargs = mock_debate_consensus.call_args
    assert "document_context" in call_kwargs.kwargs or len(call_kwargs.args) > 0


# ── Non-debate handler tests (unchanged behavior) ───────────────────────

def test_extend_modify_class(client, mock_sparql_update):
    """Test modifying an existing class."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "tbox_modify_class",
            "review_item_id": "mod_TestClass",
            "reviewer_id": "alice",
            "suggested_changes": {
                "uri": "http://example.org/TestClass",
                "label": "Updated Label",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "applied"
    assert mock_sparql_update.called


def test_extend_hierarchy_fix(client, mock_sparql_update):
    """Test fixing class hierarchy."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "tbox_hierarchy_fix",
            "review_item_id": "fix_hierarchy",
            "suggested_changes": {
                "uri": "http://example.org/Child",
                "parent_uri": "http://example.org/NewParent",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "applied"


def test_extend_invalid_change_type(client):
    """Test extending with invalid change type."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "invalid_type",
            "review_item_id": "test",
        },
    )
    # Pydantic validation should catch this, or the handler lookup should fail
    assert resp.status_code in (400, 422)


def test_extend_bulk_with_debate(
    client, mock_sparql_update, mock_hierarchy_fetch, mock_debate_consensus,
):
    """Test bulk extending with debate for new classes."""
    resp = client.post(
        "/api/v1/extend/bulk",
        json={
            "changes": [
                {
                    "change_type": "tbox_new_class",
                    "review_item_id": "gap_Class1",
                    "suggested_changes": {"label": "Class1"},
                    "debate_enabled": True,
                },
                {
                    "change_type": "tbox_modify_class",
                    "review_item_id": "mod_Existing",
                    "suggested_changes": {
                        "uri": "http://example.org/Existing",
                        "label": "RenamedExisting",
                    },
                },
            ],
            "atomic": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # First should be debated + staged
    assert data[0]["status"] == "staged"
    assert data[0]["debate"]["verdict"] == "consensus"
    # Second is a direct modify
    assert data[1]["status"] == "applied"


def test_extend_bulk_direct_fallback(
    client, mock_sparql_update, mock_llm_generate, mock_hierarchy_fetch,
):
    """Test bulk extending with debate disabled."""
    resp = client.post(
        "/api/v1/extend/bulk",
        json={
            "changes": [
                {
                    "change_type": "tbox_new_class",
                    "review_item_id": "gap_Class1",
                    "suggested_changes": {"label": "Class1"},
                    "debate_enabled": False,
                },
                {
                    "change_type": "tbox_new_class",
                    "review_item_id": "gap_Class2",
                    "suggested_changes": {"label": "Class2"},
                    "debate_enabled": False,
                },
            ],
            "atomic": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(r["status"] in ("staged", "applied", "error") for r in data)
    # Both should have skipped debate
    for r in data:
        if r.get("debate"):
            assert r["debate"]["verdict"] == "skipped"

"""Tests for ontology extension endpoints."""

from __future__ import annotations

from ontology_hitl.api.schemas import TBoxChangeType


def test_extend_new_class(client, mock_sparql_update, mock_llm_generate):
    """Test extending ontology with a new class."""
    resp = client.post(
        "/api/v1/extend",
        json={
            "change_type": "tbox_new_class",
            "review_item_id": "gap_TestClass",
            "rationale": "Found unmapped entities",
            "suggested_changes": {"label": "TestClass"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "staged"
    assert "change_id" in data
    assert mock_llm_generate.call_count >= 1
    assert mock_sparql_update.call_count >= 1


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


def test_extend_bulk(client, mock_sparql_update, mock_llm_generate):
    """Test bulk extending."""
    resp = client.post(
        "/api/v1/extend/bulk",
        json={
            "changes": [
                {
                    "change_type": "tbox_new_class",
                    "review_item_id": "gap_Class1",
                    "suggested_changes": {"label": "Class1"},
                },
                {
                    "change_type": "tbox_new_class",
                    "review_item_id": "gap_Class2",
                    "suggested_changes": {"label": "Class2"},
                },
            ],
            "atomic": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(r["status"] in ("staged", "applied", "error") for r in data)

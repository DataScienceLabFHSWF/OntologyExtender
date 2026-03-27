"""Tests for API schemas."""

from __future__ import annotations

from ontology_hitl.api.schemas import (
    TBoxChangeType,
    TBoxChangeRequest,
    TBoxChangeResponse,
    OntologyClass,
    OntologyRelation,
    HierarchyEdge,
    OntologySummary,
    ServiceHealth,
)


def test_tbox_change_type_enum():
    """Test TBoxChangeType enum values."""
    assert TBoxChangeType.NEW_CLASS.value == "tbox_new_class"
    assert TBoxChangeType.MODIFY_CLASS.value == "tbox_modify_class"
    assert TBoxChangeType.HIERARCHY_FIX.value == "tbox_hierarchy_fix"
    assert TBoxChangeType.PROPERTY_FIX.value == "tbox_property_fix"


def test_tbox_change_request_defaults():
    """Test TBoxChangeRequest with defaults."""
    req = TBoxChangeRequest(
        change_type=TBoxChangeType.NEW_CLASS,
        review_item_id="gap_test",
    )
    assert req.reviewer_id == "system"
    assert req.rationale == ""
    assert req.confidence == 1.0
    assert req.suggested_changes == {}


def test_tbox_change_request_full():
    """Test TBoxChangeRequest with all fields."""
    req = TBoxChangeRequest(
        change_type=TBoxChangeType.NEW_CLASS,
        review_item_id="gap_test",
        reviewer_id="alice",
        rationale="Found unmapped entities",
        suggested_changes={"label": "TestClass"},
        confidence=0.95,
    )
    assert req.reviewer_id == "alice"
    assert req.rationale == "Found unmapped entities"
    assert req.suggested_changes["label"] == "TestClass"
    assert req.confidence == 0.95


def test_tbox_change_response():
    """Test TBoxChangeResponse."""
    resp = TBoxChangeResponse(
        status="staged",
        change_id="change_abc123",
        changes_applied=["Inserted class 'TestClass'"],
    )
    assert resp.status == "staged"
    assert resp.change_id == "change_abc123"
    assert len(resp.changes_applied) == 1


def test_ontology_class():
    """Test OntologyClass schema."""
    cls = OntologyClass(
        uri="http://example.org/TestClass",
        label="Test Class",
        description="A test class",
        parent_uri="http://example.org/ParentClass",
    )
    assert cls.uri == "http://example.org/TestClass"
    assert cls.label == "Test Class"
    assert cls.description == "A test class"
    assert cls.parent_uri == "http://example.org/ParentClass"
    assert cls.properties == []
    assert cls.examples == []


def test_ontology_relation():
    """Test OntologyRelation schema."""
    rel = OntologyRelation(
        uri="http://example.org/hasChild",
        label="has child",
        domain=["http://example.org/Person"],
        range=["http://example.org/Person"],
    )
    assert rel.uri == "http://example.org/hasChild"
    assert rel.label == "has child"
    assert len(rel.domain) == 1
    assert len(rel.range) == 1


def test_ontology_summary():
    """Test OntologySummary schema."""
    summary = OntologySummary(
        classes=[],
        relations=[],
        hierarchy=[],
        class_count=0,
        relation_count=0,
    )
    assert summary.class_count == 0
    assert summary.relation_count == 0


def test_service_health():
    """Test ServiceHealth schema."""
    health = ServiceHealth(
        status="ok",
        fuseki="ok",
        ollama="ok",
    )
    assert health.service == "ontology-extender"
    assert health.version == "0.1.0"

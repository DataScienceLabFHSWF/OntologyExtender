"""Tests for ontology browsing endpoints."""

from __future__ import annotations


def test_list_classes_empty(client, mock_sparql_query):
    """Test listing classes when ontology is empty."""
    mock_sparql_query.return_value = []
    resp = client.get("/api/v1/ontology/classes")
    assert resp.status_code == 200
    data = resp.json()
    assert data == []


def test_list_classes_with_data(client, mock_sparql_query):
    """Test listing classes with sample data."""
    mock_sparql_query.return_value = [
        {
            "uri": "http://example.org/Person",
            "label": "Person",
            "description": "A person",
            "parent": None,
        },
        {
            "uri": "http://example.org/Employee",
            "label": "Employee",
            "description": "An employee",
            "parent": "http://example.org/Person",
        },
    ]
    resp = client.get("/api/v1/ontology/classes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["uri"] == "http://example.org/Person"
    assert data[1]["parent_uri"] == "http://example.org/Person"


def test_list_relations_empty(client, mock_sparql_query):
    """Test listing relations when ontology is empty."""
    mock_sparql_query.return_value = []
    resp = client.get("/api/v1/ontology/relations")
    assert resp.status_code == 200
    data = resp.json()
    assert data == []


def test_get_hierarchy(client, mock_sparql_query):
    """Test getting class hierarchy."""
    mock_sparql_query.return_value = [
        {
            "child": "http://example.org/Employee",
            "parent": "http://example.org/Person",
        },
    ]
    resp = client.get("/api/v1/ontology/hierarchy")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["child_uri"] == "http://example.org/Employee"


def test_get_summary(client, mock_sparql_query):
    """Test getting full ontology summary."""
    mock_sparql_query.return_value = []
    resp = client.get("/api/v1/ontology/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "classes" in data
    assert "relations" in data
    assert "hierarchy" in data
    assert "class_count" in data
    assert "relation_count" in data

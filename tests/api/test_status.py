"""Tests for status endpoints."""

from __future__ import annotations


def test_root_endpoint(client):
    """Test root endpoint."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "ontology-extender"
    assert "docs" in data


def test_health_endpoint(client, mock_get_fuseki_client, mock_get_ollama_client):
    """Test health check endpoint."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["service"] == "ontology-extender"
    assert "fuseki" in data
    assert "ollama" in data
    assert "version" in data

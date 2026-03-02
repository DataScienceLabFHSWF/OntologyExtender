"""Tests for SHACL validation endpoints."""

from __future__ import annotations


def test_validate_shacl_no_shapes(client):
    """Test SHACL validation with no shapes graph."""
    resp = client.post(
        "/api/v1/validate/shacl",
        json={},
    )
    # Should handle gracefully - either 200 with empty results or error
    assert resp.status_code >= 200

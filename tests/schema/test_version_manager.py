"""Tests for OntologyVersionManager."""

from __future__ import annotations

from ontology_hitl.schema.version_manager import OntologyVersionManager


class TestOntologyVersionManager:
    """Test version management functionality."""

    def test_create_version(self) -> None:
        """Test creating a new version record."""
        mgr = OntologyVersionManager()
        version = mgr.create_version("v1.0", notes="Initial version")
        assert version.version_id == "v1.0"
        assert version.notes == "Initial version"

    def test_compute_diff_returns_diff(self) -> None:
        """Test computing diff between versions."""
        mgr = OntologyVersionManager()
        diff = mgr.compute_diff("v1.0", "v2.0")
        assert diff.from_version == "v1.0"
        assert diff.to_version == "v2.0"

"""Exception hierarchy for ontology-hitl."""

from __future__ import annotations


class OntologyHITLError(Exception):
    """Base exception."""


class GapAnalysisError(OntologyHITLError):
    """Error during gap analysis."""


class SchemaUpdateError(OntologyHITLError):
    """Error updating ontology schema."""


class SHACLValidationError(OntologyHITLError):
    """SHACL constraint violation."""

    def __init__(self, violations: list[str]) -> None:
        super().__init__(f"SHACL validation failed: {len(violations)} violations")
        self.violations = violations


class ReviewError(OntologyHITLError):
    """Error in review workflow."""


class CheckpointLoadError(OntologyHITLError):
    """Error loading KGB checkpoint."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Failed to load checkpoint {path}: {reason}")
        self.path = path
        self.reason = reason

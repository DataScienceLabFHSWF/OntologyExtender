"""Protocol definitions for ontology extension components."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ontology_hitl.core.models import (
    ExtractedEntitySummary,
    GapCandidate,
    GapReport,
    ProposedClass,
    ReviewDecision,
)


@runtime_checkable
class OntologyProvider(Protocol):
    """Interface to ontology store (Fuseki)."""

    def get_all_classes(self) -> list[str]: ...
    def get_class_hierarchy(self) -> dict[str, list[str]]: ...
    def add_class(self, owl_turtle: str) -> None: ...
    def remove_class(self, class_uri: str) -> None: ...
    def sparql_query(self, query: str) -> list[dict]: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Interface to LLM for definition generation."""

    def generate(self, prompt: str, **kwargs: object) -> str: ...


@runtime_checkable
class CheckpointReader(Protocol):
    """Reads KGB extraction checkpoints."""

    def load_entities(self, path: Path) -> list[ExtractedEntitySummary]: ...


@runtime_checkable
class ReviewBackend(Protocol):
    """Stores and retrieves review decisions."""

    def save_decision(self, decision: ReviewDecision) -> None: ...
    def get_decisions(self, proposal_id: str) -> list[ReviewDecision]: ...
    def get_all_decisions(self) -> list[ReviewDecision]: ...

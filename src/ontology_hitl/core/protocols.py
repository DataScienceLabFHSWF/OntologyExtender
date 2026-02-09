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
    """Interface to ontology store (Fuseki).

    Implementation maps to FusekiOntologyService exposed via
    INTERFACE_CONTRACT.md §3 SPARQL endpoints.
    """

    def get_all_classes(self) -> list[str]: ...
    def get_class_hierarchy(self) -> dict[str, list[str]]: ...
    def add_class(self, owl_turtle: str) -> None: ...
    def remove_class(self, class_uri: str) -> None: ...
    def sparql_query(self, query: str) -> list[dict]: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Interface to LLM for definition generation.

    Used by discovery modules (ClassDefinitionGenerator, RelationProposalGenerator)
    to generate class definitions and relations. Typically implemented by
    an Ollama endpoint (INTERFACE_CONTRACT.md specifies model selection).
    """

    def generate(self, prompt: str, **kwargs: object) -> str: ...


@runtime_checkable
class CheckpointReader(Protocol):
    """Reads KGB extraction checkpoints.

    Checkpoint format defined in INTERFACE_CONTRACT.md §4.
    Transforms raw checkpoint entities into ExtractedEntitySummary,
    preserving id, description, aliases, and evidence links.
    """

    def load_entities(self, path: Path) -> list[ExtractedEntitySummary]: ...


@runtime_checkable
class ReviewBackend(Protocol):
    """Stores and retrieves review decisions.

    Provides CRUD operations for expert feedback on proposed classes.
    Used by CLI and web dashboard review modules (INTERFACE_CONTRACT.md §5
    defines the ReviewDecision schema).
    """

    def save_decision(self, decision: ReviewDecision) -> None: ...
    def get_decisions(self, proposal_id: str) -> list[ReviewDecision]: ...
    def get_all_decisions(self) -> list[ReviewDecision]: ...

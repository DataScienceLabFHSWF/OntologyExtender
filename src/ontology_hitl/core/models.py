"""Core data models for ontology extension workflow.

Includes mirrored KGB data models (read-only), retrieval pipeline types
(ported from GraphQAAgent), and HITL ontology-extension specific models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


# ── Knowledge-graph models (ported from GraphQAAgent) ───────────────


@dataclass
class KGEntity:
    """An entity node in the Neo4j knowledge graph."""

    id: str
    label: str
    entity_type: str = ""
    description: str = ""
    confidence: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)
    neo4j_labels: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KGRelation:
    """A directed relationship between two :class:`KGEntity` nodes."""

    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 0.0


@dataclass
class OntologyClass:
    """An OWL class from the Fuseki TBox."""

    uri: str
    label: str
    parent_uri: str | None = None
    description: str = ""


@dataclass
class OntologyProperty:
    """An OWL property from the Fuseki TBox."""

    uri: str
    label: str
    domain_uri: str = ""
    range_uri: str = ""
    property_type: str = "object"  # "object" | "datatype"


# ── Retrieval pipeline models (ported from GraphQAAgent) ────────────


@dataclass
class DocumentChunk:
    """Chunk read from Qdrant payload (matches KGB field names)."""

    id: str
    doc_id: str
    content: str
    strategy: str = ""
    embedding: list[float] | None = None


class QuestionType(Enum):
    """Classification of user questions."""

    FACTOID = "factoid"
    LIST = "list"
    BOOLEAN = "boolean"
    COMPARATIVE = "comparative"
    CAUSAL = "causal"
    AGGREGATION = "aggregation"


class RetrievalSource(Enum):
    """Provenance label for a retrieved context piece."""

    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"
    ONTOLOGY = "ontology"


@dataclass
class QAQuery:
    """Parsed user question enriched by question parser + ontology expansion."""

    raw_question: str
    question_type: QuestionType | None = None
    detected_entities: list[str] = field(default_factory=list)
    detected_types: list[str] = field(default_factory=list)
    expected_relations: list[str] = field(default_factory=list)
    sub_questions: list[str] = field(default_factory=list)
    language: str = "de"


@dataclass
class Provenance:
    """Tracks where a piece of evidence came from."""

    doc_id: str | None = None
    source_id: str | None = None
    entity_ids: list[str] = field(default_factory=list)
    retrieval_strategy: str = ""
    retrieval_score: float = 0.0


@dataclass
class RetrievedContext:
    """Single piece of retrieved evidence with provenance."""

    source: RetrievalSource
    text: str
    score: float = 0.0
    chunk: DocumentChunk | None = None
    subgraph: list[KGEntity | KGRelation] | None = None
    provenance: Provenance | None = None


@dataclass
class GraphExplorationState:
    """State of an iterative Think-on-Graph exploration."""

    visited_entity_ids: set[str] = field(default_factory=set)
    frontier_entity_ids: set[str] = field(default_factory=set)
    collected_entities: list[KGEntity] = field(default_factory=list)
    collected_relations: list[KGRelation] = field(default_factory=list)
    exploration_path: list[str] = field(default_factory=list)
    iterations: int = 0
    sufficient_evidence: bool = False


class ProposalStatus(str, Enum):
    """Status of an ontology class proposal."""

    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


@dataclass
class ExtractedEntitySummary:
    """Lightweight entity reference derived from KGB extraction checkpoint.

    See INTERFACE_CONTRACT.md §4 for the raw checkpoint schema.
    This model transforms checkpoint entities into the HITL workflow format.
    """

    id: str  # KGB entity ID: "ent_<hex12>"
    label: str
    entity_type: str
    description: str = ""  # Present in checkpoint
    aliases: list[str] = field(default_factory=list)  # Present in checkpoint
    confidence: float = 0.0
    frequency: int = 0  # Computed: len(evidence) or deduplicated source count
    source_ids: list[str] = field(default_factory=list)  # Derived: evidence[*].source_id
    evidence_spans: list[str] = field(default_factory=list)  # Derived: evidence[*].text_span


@dataclass
class GapCandidate:
    """Entity type not covered by current ontology."""

    entity_type: str
    representative_label: str
    examples: list[str]
    frequency: int
    avg_confidence: float
    closest_seed_class: str | None = None
    semantic_distance: float = 1.0  # 0 = identical, 1 = unrelated


@dataclass
class PropertyDef:
    """Proposed property for a class."""

    name: str
    datatype: str  # "xsd:string", "xsd:integer", etc.
    description: str
    required: bool = False
    max_count: int | None = None


@dataclass
class RelationDef:
    """Proposed relation (ObjectProperty)."""

    name: str
    domain: str  # class label
    range: str  # class label
    description: str
    inverse_name: str | None = None
    cardinality: str = "0..*"  # "1..1", "0..1", "0..*", "1..*"


@dataclass
class ProposedClass:
    """Candidate new ontology class."""

    id: str
    label: str
    definition: str
    parent_uri: str  # URI of seed class to be subClassOf
    parent_label: str
    examples: list[str] = field(default_factory=list)
    frequency: int = 0
    confidence: float = 0.0
    suggested_properties: list[PropertyDef] = field(default_factory=list)
    suggested_relations: list[RelationDef] = field(default_factory=list)
    status: ProposalStatus = ProposalStatus.PROPOSED
    source_gap_candidates: list[str] = field(default_factory=list)


@dataclass
class ReviewDecision:
    """Expert feedback on a proposed class."""

    proposal_id: str
    reviewer: str
    timestamp: datetime = field(default_factory=datetime.now)
    decision: Literal["accepted", "rejected", "needs_revision"] = "needs_revision"
    rationale: str = ""
    suggested_changes: dict[str, str] = field(default_factory=dict)
    confidence_in_decision: float = 0.5


@dataclass
class OntologyVersion:
    """Metadata for an ontology version."""

    version_id: str
    parent_version: str | None
    timestamp: datetime = field(default_factory=datetime.now)
    added_classes: list[str] = field(default_factory=list)
    removed_classes: list[str] = field(default_factory=list)
    added_relations: list[str] = field(default_factory=list)
    total_classes: int = 0
    total_relations: int = 0
    notes: str = ""


@dataclass
class OntologyDiff:
    """Change summary between two ontology versions."""

    from_version: str
    to_version: str
    added_classes: list[str] = field(default_factory=list)
    removed_classes: list[str] = field(default_factory=list)
    added_relations: list[tuple[str, str, str]] = field(default_factory=list)
    removed_relations: list[tuple[str, str, str]] = field(default_factory=list)
    cq_coverage_before: float = 0.0
    cq_coverage_after: float = 0.0
    entity_coverage_before: float = 0.0
    entity_coverage_after: float = 0.0


@dataclass
class GapReport:
    """Output of gap analysis."""

    ontology_version: str
    total_extracted_entities: int
    covered_entities: int
    uncovered_entities: int
    coverage_pct: float
    gap_candidates: list[GapCandidate] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class IterationResult:
    """Summary of one iteration cycle."""

    iteration_id: str
    ontology_version_before: str
    ontology_version_after: str
    proposals_generated: int
    proposals_accepted: int
    proposals_rejected: int
    cq_coverage_before: float
    cq_coverage_after: float
    entity_coverage_before: float
    entity_coverage_after: float
    timestamp: datetime = field(default_factory=datetime.now)

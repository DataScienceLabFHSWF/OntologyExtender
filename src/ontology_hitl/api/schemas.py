"""Pydantic request/response models for the OntologyExtender API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────

class TBoxChangeType(str, Enum):
    """Types of TBox changes the extender can apply."""

    NEW_CLASS = "tbox_new_class"
    MODIFY_CLASS = "tbox_modify_class"
    HIERARCHY_FIX = "tbox_hierarchy_fix"
    PROPERTY_FIX = "tbox_property_fix"


class DebateVerdictEnum(str, Enum):
    """Possible outcomes of a multi-agent debate."""

    CONSENSUS = "consensus"
    REVISED = "revised"
    ESCALATED = "escalated"
    PARTIAL = "partial"
    SKIPPED = "skipped"  # debate was not run (e.g. fallback mode)


# ── Extend ───────────────────────────────────────────────────────────────

class TBoxChangeRequest(BaseModel):
    """Request to apply a single TBox change.

    Sent by KGBuilder's HITL gap detector or by the review UI.
    When ``debate_enabled`` is True (default), NEW_CLASS changes are
    routed through the multi-agent debate pipeline for quality assurance.
    """

    change_type: TBoxChangeType
    review_item_id: str = Field(..., description="ID of the review item originating this change")
    reviewer_id: str = Field(default="system", description="Who approved / requested the change")
    rationale: str = Field(default="", description="Why this change is needed")
    suggested_changes: dict[str, str] = Field(
        default_factory=dict,
        description="Key-value pairs of suggested modifications (e.g. label, parent_uri, ...)",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    debate_enabled: bool = Field(
        default=True,
        description="Route through multi-agent debate pipeline (recommended for new classes)",
    )
    document_context: str = Field(
        default="",
        description="Domain document excerpts for the DomainExpert agent",
    )


# ── Debate result schemas ────────────────────────────────────────────────

class DebateMessageSummary(BaseModel):
    """Summary of a single message in a debate transcript."""

    role: str = Field(..., description="Agent role: ontology_engineer / domain_expert / critic")
    message_type: str = Field(..., description="proposal / review / revision")
    approves: bool | None = None
    issues_raised: list[str] = Field(default_factory=list)
    reasoning_excerpt: str = Field(default="", description="Truncated chain-of-thought")


class EscalatedQuestionInfo(BaseModel):
    """A question escalated from the debate for HITL review."""

    phase: str
    question: str
    context: str = ""


class DebateResult(BaseModel):
    """Full debate outcome attached to a TBox change response."""

    verdict: DebateVerdictEnum
    rounds: int = 0
    resolved_issues: list[str] = Field(default_factory=list)
    escalated_questions: list[EscalatedQuestionInfo] = Field(default_factory=list)
    transcript: list[DebateMessageSummary] = Field(default_factory=list)
    final_proposal: dict[str, Any] = Field(
        default_factory=dict,
        description="The debated & agreed-upon class definition JSON",
    )


class TBoxChangeResponse(BaseModel):
    """Result of applying a TBox change."""

    status: str = Field(
        ...,
        description="'applied' | 'staged' | 'needs_review' | 'rejected' | 'error'",
    )
    change_id: str = Field(..., description="Unique ID for the applied change")
    changes_applied: list[str] = Field(
        default_factory=list,
        description="Human-readable list of mutations",
    )
    new_ontology_version: str | None = Field(
        default=None,
        description="Version tag if the ontology was bumped",
    )
    debate: DebateResult | None = Field(
        default=None,
        description="Multi-agent debate result (present when debate_enabled=True)",
    )


class BulkExtendRequest(BaseModel):
    """Batch of TBox changes to apply atomically."""

    changes: list[TBoxChangeRequest]
    atomic: bool = Field(
        default=True,
        description="If True, all-or-nothing; if False, best-effort",
    )


# ── Browse ───────────────────────────────────────────────────────────────

class PropertyInfo(BaseModel):
    """An OWL datatype / object property."""

    uri: str
    label: str
    description: str = ""
    range_uri: str = ""


class OntologyClass(BaseModel):
    """A single OWL class in the ontology."""

    uri: str
    label: str
    description: str = ""
    parent_uri: str | None = None
    properties: list[PropertyInfo] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class OntologyRelation(BaseModel):
    """A single OWL object property / relation."""

    uri: str
    label: str
    description: str = ""
    domain: list[str] = Field(default_factory=list)
    range: list[str] = Field(default_factory=list)


class HierarchyEdge(BaseModel):
    """A parent → child edge in the class hierarchy."""

    parent_uri: str
    child_uri: str


class OntologySummary(BaseModel):
    """Full ontology overview."""

    classes: list[OntologyClass]
    relations: list[OntologyRelation]
    hierarchy: list[HierarchyEdge]
    class_count: int
    relation_count: int


# ── SHACL Validation ────────────────────────────────────────────────────

class SHACLValidationRequest(BaseModel):
    """Request to validate an RDF data graph against SHACL shapes."""

    shapes_path: str | None = Field(
        default=None,
        description="Path to shapes graph (default: auto-detect from Fuseki)",
    )
    data_graph_path: str | None = Field(
        default=None,
        description="Path to data graph (default: main Fuseki dataset)",
    )


class SHACLViolation(BaseModel):
    """A single SHACL validation violation."""

    focus_node: str
    path: str
    message: str
    severity: str  # "Violation" | "Warning" | "Info"


class SHACLValidationResponse(BaseModel):
    """Result of SHACL validation."""

    conforms: bool
    violations: list[SHACLViolation] = Field(default_factory=list)
    total_shapes: int = 0


# ── Health ───────────────────────────────────────────────────────────────

class ServiceHealth(BaseModel):
    """Health-check response."""

    status: str  # "ok" | "degraded"
    service: str = "ontology-extender"
    fuseki: str = "unknown"
    ollama: str = "unknown"
    version: str = "0.1.0"

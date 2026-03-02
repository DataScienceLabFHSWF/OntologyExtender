"""Pydantic request/response models for the OntologyExtender API."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────

class TBoxChangeType(str, Enum):
    """Types of TBox changes the extender can apply."""

    NEW_CLASS = "tbox_new_class"
    MODIFY_CLASS = "tbox_modify_class"
    HIERARCHY_FIX = "tbox_hierarchy_fix"
    PROPERTY_FIX = "tbox_property_fix"


# ── Extend ───────────────────────────────────────────────────────────────

class TBoxChangeRequest(BaseModel):
    """Request to apply a single TBox change.

    Sent by KGBuilder's HITL gap detector or by the review UI.
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


class TBoxChangeResponse(BaseModel):
    """Result of applying a TBox change."""

    status: str = Field(..., description="'applied' | 'staged' | 'rejected' | 'error'")
    change_id: str = Field(..., description="Unique ID for the applied change")
    changes_applied: list[str] = Field(
        default_factory=list,
        description="Human-readable list of mutations",
    )
    new_ontology_version: str | None = Field(
        default=None,
        description="Version tag if the ontology was bumped",
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

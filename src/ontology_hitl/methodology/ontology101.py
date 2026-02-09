"""Ontology 101 seven-phase framework — data models and pipeline.

Implements the Noy & McGuinness (2001) methodology as an agentic
pipeline where each phase encodes what a human ontology engineer would
think about.  The agent "acts like a researcher" — it poses the right
questions at each step, validates outputs against established rules
from the paper, and surfaces findings for human review.

Phases
------
1. **Scope & CQs**        — define domain, purpose, competency questions
2. **Reuse**              — check seed ontology coverage, identify import candidates
3. **Term enumeration**   — extract & categorise all domain terms from documents
4. **Class hierarchy**    — organise terms into is-a taxonomy (top-down + bottom-up)
5. **Properties (slots)** — attach data/object properties with domain & range
6. **Facets**             — cardinality, value-type restrictions, SHACL shapes
7. **Instance validation** — test with concrete examples, answer CQs

Each phase produces typed artefacts consumed by the next, and an
``AgentQuestion`` list surfaced to the HITL reviewer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


# ── Phase enum ──────────────────────────────────────────────────────

class Phase(str, Enum):
    """The seven Ontology-101 phases."""

    SCOPE = "1_scope"
    REUSE = "2_reuse"
    TERMS = "3_terms"
    HIERARCHY = "4_hierarchy"
    PROPERTIES = "5_properties"
    FACETS = "6_facets"
    INSTANCES = "7_instances"


# ── Cross-cutting: agent reasoning artefact ─────────────────────────

@dataclass
class AgentQuestion:
    """A question the agent surfaces for HITL review.

    Instead of just presenting proposals, the agent *asks* the expert
    the questions that a good ontology engineer would ask.  This is
    modeled after the "competency questions" concept from Ont-101
    but applied reflexively to the design process itself.
    """

    phase: Phase
    question: str
    context: str           # evidence / reasoning that prompted the question
    options: list[str] = field(default_factory=list)   # suggested answers
    default: str | None = None
    answer: str | None = None                          # filled by reviewer
    auto_resolved: bool = False                        # resolved by the agent


# ── Phase 1: Scope ──────────────────────────────────────────────────

@dataclass
class OntologyScope:
    """Output of Phase 1 — defines what the ontology should cover."""

    domain: str = ""
    purpose: str = ""
    intended_users: list[str] = field(default_factory=list)
    competency_questions: list[dict] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    language: str = "en"                    # de, en, mixed
    upper_ontology: str | None = None       # e.g. "BFO", "DOLCE", None
    timestamp: datetime = field(default_factory=datetime.now)


# ── Phase 2: Reuse ──────────────────────────────────────────────────

@dataclass
class ReuseCandidate:
    """An existing ontology (or part of it) that could be imported."""

    ontology_name: str
    uri: str
    overlap_terms: list[str] = field(default_factory=list)
    overlap_score: float = 0.0
    decision: Literal["import", "extend", "reference", "skip"] = "skip"
    rationale: str = ""


@dataclass
class ReuseReport:
    """Output of Phase 2 — what we could reuse from existing ontologies."""

    seed_ontology_classes: list[str] = field(default_factory=list)
    seed_ontology_properties: list[str] = field(default_factory=list)
    candidates: list[ReuseCandidate] = field(default_factory=list)
    terms_already_covered: list[str] = field(default_factory=list)
    terms_still_needed: list[str] = field(default_factory=list)


# ── Phase 3: Term Enumeration ──────────────────────────────────────

@dataclass
class DomainTerm:
    """A term extracted from the domain documents."""

    term: str
    category: Literal["class", "property", "relation", "instance", "unknown"] = "unknown"
    frequency: int = 1
    source_documents: list[str] = field(default_factory=list)
    evidence_snippets: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class TermEnumeration:
    """Output of Phase 3 — all important terms found in the domain."""

    terms: list[DomainTerm] = field(default_factory=list)
    class_candidates: list[str] = field(default_factory=list)
    property_candidates: list[str] = field(default_factory=list)
    relation_candidates: list[str] = field(default_factory=list)
    ambiguous_terms: list[str] = field(default_factory=list)


# ── Phase 4: Class Hierarchy ───────────────────────────────────────

@dataclass
class HierarchyNode:
    """A class in the proposed taxonomy."""

    uri: str
    label: str
    definition: str = ""
    parent_uri: str | None = None
    parent_label: str | None = None
    children_uris: list[str] = field(default_factory=list)
    is_from_seed: bool = False
    depth: int = 0
    disjoint_with: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    strategy: Literal["top-down", "bottom-up", "middle-out"] = "middle-out"


@dataclass
class ClassHierarchy:
    """Output of Phase 4 — the proposed is-a taxonomy."""

    nodes: list[HierarchyNode] = field(default_factory=list)
    root_uri: str = ""
    total_depth: int = 0
    new_classes_count: int = 0
    seed_classes_count: int = 0


# ── Phase 5: Properties ───────────────────────────────────────────

@dataclass
class PropertyProposal:
    """A proposed datatype or object property attached to a class."""

    name: str
    attached_to_class: str          # most general class that has this property
    property_type: Literal["datatype", "object"] = "datatype"
    description: str = ""
    # Datatype properties
    datatype: str = "xsd:string"    # xsd:string, xsd:integer, xsd:float, xsd:boolean, ...
    # Object properties
    range_class: str | None = None  # target class for object properties
    inverse_name: str | None = None
    # Shared
    inherited_by: list[str] = field(default_factory=list)
    source_evidence: list[str] = field(default_factory=list)

    # --- Ont-101 rules encoded ---------------------------------
    #  "A slot should be attached at the most general class that can
    #   have that property." (Section 3, Step 5)
    #  "Do not define a domain and range that is overly general."
    #   (Section 3, Step 6)


# ── Phase 6: Facets / Constraints ────────────────────────────────

@dataclass
class FacetSpec:
    """Cardinality and value-type constraints for a property on a class."""

    property_name: str
    on_class: str
    min_count: int | None = None    # sh:minCount
    max_count: int | None = None    # sh:maxCount
    value_type: str = "xsd:string"  # or class URI for object props
    allowed_values: list[str] | None = None  # enum / sh:in
    pattern: str | None = None      # regex / sh:pattern
    rationale: str = ""


@dataclass
class FacetReport:
    """Output of Phase 6 — all constraints defined."""

    facets: list[FacetSpec] = field(default_factory=list)
    shacl_shapes_turtle: str = ""   # generated SHACL


# ── Phase 7: Instance Validation ─────────────────────────────────

@dataclass
class SampleInstance:
    """A sample instance used to validate the ontology."""

    class_uri: str
    class_label: str
    property_values: dict[str, str | int | float | bool] = field(default_factory=dict)
    expected_valid: bool = True
    validation_result: bool | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class CQTestResult:
    """Whether a CQ can now be answered with the ontology."""

    cq_id: str
    question: str
    answerable: bool = False
    required_classes: list[str] = field(default_factory=list)
    required_properties: list[str] = field(default_factory=list)
    missing_elements: list[str] = field(default_factory=list)
    sparql_sketch: str = ""         # approximate SPARQL that would answer it


@dataclass
class ValidationReport:
    """Output of Phase 7 — does the ontology work?"""

    instances_tested: list[SampleInstance] = field(default_factory=list)
    cq_results: list[CQTestResult] = field(default_factory=list)
    cq_coverage_pct: float = 0.0
    instance_pass_rate: float = 0.0
    issues: list[str] = field(default_factory=list)


# ── Full pipeline artefact ──────────────────────────────────────────

@dataclass
class Ont101Iteration:
    """Everything produced by one pass through the 7 phases."""

    iteration: int = 1
    scope: OntologyScope | None = None
    reuse: ReuseReport | None = None
    terms: TermEnumeration | None = None
    hierarchy: ClassHierarchy | None = None
    properties: list[PropertyProposal] = field(default_factory=list)
    facets: FacetReport | None = None
    validation: ValidationReport | None = None
    questions: list[AgentQuestion] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

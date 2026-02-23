"""Closed-loop feedback protocol between OntologyExtender and KGBuilder.

This module defines the **Ontology↔KG Co-Evolution Loop** — the core
research contribution of this project. The key insight:

    Ontology extension should not be a one-shot process.  Each ontology
    update changes what the KG builder can extract, and new extractions
    reveal further gaps in the ontology.  By **measuring** this interplay
    across iterations we can show that guided co-evolution outperforms
    independent ontology extension.

Architecture
-----------

    ┌─────────────────────────────────┐
    │         Iteration N             │
    │                                 │
    │  ┌──────────┐   ┌───────────┐  │     ┌──────────────┐
    │  │ Ontology  │──▶│  Export    │──┼────▶│  KG Builder  │
    │  │ Extension │   │  OWL+CQs  │  │     │  (optional)  │
    │  └──────────┘   └───────────┘  │     └──────┬───────┘
    │       ▲                        │            │
    │       │     ┌────────────┐     │            │
    │       └─────│  Evaluate  │◀────┼────────────┘
    │             │  Δ metrics │     │     extraction results
    │             └────────────┘     │     + new checkpoint
    │                  │             │
    │            improvement?        │
    │           yes ↙     ↘ no       │
    │      iterate      stop/review  │
    └─────────────────────────────────┘

The loop can run in two modes:

1. **Coupled mode** (with KGB):
   After exporting the extended ontology, trigger KGB re-extraction,
   then measure improvement in entity coverage and CQ answerability.
   This produces the strongest evidence for the feedback hypothesis.

2. **Standalone mode** (without KGB):
   Use Qdrant documents directly for entity discovery and CQ evaluation.
   Still iterates (extend → evaluate → extend), but the "KG building"
   step is replaced by direct LLM-based entity extraction from documents.
   Useful for rapid prototyping or when KGB is not available.

Research Contribution
--------------------
The measurable claim: **Iterative co-evolution of ontology and KG
produces higher CQ answerability and entity coverage than one-shot
ontology extension**, because:

- Each KG extraction reveals entities the ontology doesn't cover yet
- New ontology classes enable extraction of previously missed entities  
- CQ coverage monotonically improves with well-guided extensions
- The improvement rate across iterations is itself a quality signal

The ``FeedbackMetrics`` dataclass tracks this across iterations,
enabling before/after/delta analysis that can be plotted in W&B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


class LoopMode(str, Enum):
    """How the feedback loop operates."""

    COUPLED = "coupled"      # Full KGB re-extraction after each ontology update
    STANDALONE = "standalone"  # Direct Qdrant + LLM extraction (no KGB dependency)


@dataclass
class FeedbackMetrics:
    """Metrics captured at one point in the co-evolution loop.

    Tracked per iteration so we can compute deltas and plot convergence.
    """

    iteration: int
    timestamp: datetime = field(default_factory=datetime.now)
    mode: str = "standalone"

    # Ontology state
    ontology_classes: int = 0
    ontology_relations: int = 0
    classes_added_this_iter: int = 0
    classes_rejected_this_iter: int = 0

    # Entity coverage (extracted entities that map to ontology classes)
    total_entities_extracted: int = 0
    entities_covered: int = 0
    entity_coverage_pct: float = 0.0

    # CQ answerability
    total_cqs: int = 0
    cqs_answerable: int = 0
    cq_coverage_pct: float = 0.0

    # Ontology quality metrics (scientific validation)
    ontology_consistency_score: float = 0.0
    ontology_coherence_score: float = 0.0
    ontology_modularity_score: float = 0.0
    ontology_expressiveness_score: float = 0.0
    ontology_overall_quality_score: float = 0.0

    # KG quality (only in coupled mode)
    kg_triples_before: int = 0
    kg_triples_after: int = 0
    kg_triple_delta: int = 0

    # Expert review signal
    proposals_generated: int = 0
    proposals_accepted: int = 0
    acceptance_rate: float = 0.0

    # Human-in-the-loop escalation signal (questions surfaced for review)
    questions_for_review: int = 0

    # Convergence signal: once improvement per iteration drops below
    # this threshold, the loop can recommend stopping
    improvement_over_previous: float = 0.0


@dataclass
class IterationPlan:
    """What the loop intends to do in the next iteration."""

    iteration: int
    mode: LoopMode
    focus_entity_types: list[str] = field(default_factory=list)
    max_proposals: int = 15
    trigger_kgb_reextract: bool = False
    notes: str = ""


@dataclass
class ConvergenceReport:
    """Summary across all iterations — the main research output.

    This is what goes into the paper / thesis to demonstrate that
    the feedback loop improves ontology quality over iterations.
    """

    total_iterations: int
    mode: str
    metrics_per_iteration: list[FeedbackMetrics] = field(default_factory=list)

    # Aggregate
    initial_entity_coverage: float = 0.0
    final_entity_coverage: float = 0.0
    initial_cq_coverage: float = 0.0
    final_cq_coverage: float = 0.0

    # Ontology quality progression
    initial_quality_score: float = 0.0
    final_quality_score: float = 0.0

    # Convergence analysis
    converged_at_iteration: int | None = None
    convergence_threshold: float = 0.02  # <2% improvement = converged

    def compute_summary(self) -> dict:
        """Compute aggregate statistics from per-iteration metrics."""
        if not self.metrics_per_iteration:
            return {}

        first = self.metrics_per_iteration[0]
        last = self.metrics_per_iteration[-1]

        self.initial_entity_coverage = first.entity_coverage_pct
        self.final_entity_coverage = last.entity_coverage_pct
        self.initial_cq_coverage = first.cq_coverage_pct
        self.final_cq_coverage = last.cq_coverage_pct
        self.initial_quality_score = first.ontology_overall_quality_score
        self.final_quality_score = last.ontology_overall_quality_score

        # Find convergence point
        for m in self.metrics_per_iteration[1:]:
            if m.improvement_over_previous < self.convergence_threshold:
                self.converged_at_iteration = m.iteration
                break

        total_escalations = sum(m.questions_for_review for m in self.metrics_per_iteration)
        avg_escalations = total_escalations / len(self.metrics_per_iteration)

        return {
            "total_iterations": self.total_iterations,
            "entity_coverage": {
                "initial": self.initial_entity_coverage,
                "final": self.final_entity_coverage,
                "delta": self.final_entity_coverage - self.initial_entity_coverage,
            },
            "cq_coverage": {
                "initial": self.initial_cq_coverage,
                "final": self.final_cq_coverage,
                "delta": self.final_cq_coverage - self.initial_cq_coverage,
            },
            "ontology_quality": {
                "initial": self.initial_quality_score,
                "final": self.final_quality_score,
                "delta": self.final_quality_score - self.initial_quality_score,
            },
            "converged_at": self.converged_at_iteration,
            "classes_added_total": sum(
                m.classes_added_this_iter for m in self.metrics_per_iteration
            ),
            "acceptance_rate_avg": (
                sum(m.acceptance_rate for m in self.metrics_per_iteration)
                / len(self.metrics_per_iteration)
            ),
            "escalations": {
                "total": total_escalations,
                "avg_per_iteration": avg_escalations,
            },
        }

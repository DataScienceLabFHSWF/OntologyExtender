"""Moderator — orchestrates discourse, detects drift, enforces grounding.

The Moderator is NOT an LLM agent. It is a deterministic orchestration
layer that:

1. Selects debate strategy based on phase and context
2. Enforces grounding constraints (document, CQ, seed)
3. Detects runaway ontology patterns (hallucination spirals, drift)
4. Injects corrective prompts when drift is detected
5. Tracks convergence and decides when to escalate

Philosophical grounding:
    The Moderator embodies Habermas's (1981) procedural conditions
    for rational discourse — it does not contribute content but
    ensures the *conditions* under which valid content can emerge.
    Combined with Feyerabend's (1975) principle that no strategy is
    universally best, it selects strategies contextually.

See docs/PHILOSOPHY.md §5 for the full design rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from ontology_hitl.agents.base import (
    AgentMessage,
    Debate,
    DebateOutcome,
    DebateStrategy,
    DebateVerdict,
)
from ontology_hitl.methodology.ontology101 import Phase

logger = structlog.get_logger(__name__)


# ── Grounding constraints (always in effect) ────────────────────────

GROUNDING_CONSTRAINTS = """\
GROUNDING CONSTRAINTS (always in effect):
1. Every proposed class, property, or relation MUST cite document evidence.
   If you cannot find evidence in the provided documents, do NOT propose it.
2. Every proposed element MUST serve at least one competency question.
   If it serves no CQ, it is scope creep — withdraw it.
3. Extensions MUST attach to the existing seed ontology structure.
   Free-floating concepts indicate drift.
4. Do NOT invent concepts that do not appear in the documents.
   Your role is to formalise existing domain knowledge, not create new knowledge.
5. Prefer simplicity — propose the MINIMUM structure needed to answer CQs.
   If a simpler design covers the same CQs, prefer it.
6. If uncertain about a classification, say so explicitly.
   Honest uncertainty is epistemically superior to confabulated confidence.
"""


# ── Strategy selection defaults per phase ───────────────────────────

DEFAULT_STRATEGY_MAP: dict[Phase, DebateStrategy] = {
    Phase.SCOPE: DebateStrategy.SOCRATIC,
    Phase.REUSE: DebateStrategy.CONSENSUS_BUILDING,
    Phase.TERMS: DebateStrategy.SOCRATIC,
    Phase.HIERARCHY: DebateStrategy.DIALECTICAL,
    Phase.PROPERTIES: DebateStrategy.DIALECTICAL,
    Phase.FACETS: DebateStrategy.DELPHI,
    Phase.INSTANCES: DebateStrategy.ABDUCTIVE,
}


# ── Drift detection thresholds ──────────────────────────────────────

@dataclass
class DriftThresholds:
    """Configurable thresholds for runaway detection."""

    # Minimum fraction of elements with document citations
    min_grounding_ratio: float = 0.85

    # Maximum drift score (1 - similarity to documents)
    max_drift_score: float = 0.4

    # Maximum new elements per iteration (complexity budget)
    max_new_elements_per_phase: int = 20

    # Minimum approval rate before halting
    min_approval_rate: float = 0.3

    # Maximum rounds of all-approve-no-issues (echo chamber)
    max_trivial_consensus_rounds: int = 2

    # Maximum consecutive revisions that only ADD elements
    max_additive_revisions: int = 3


@dataclass
class GroundingReport:
    """Report on how well-grounded a proposal is."""

    total_elements: int = 0
    elements_with_citations: int = 0
    elements_serving_cqs: int = 0
    elements_connected_to_seed: int = 0
    ungrounded_elements: list[str] = field(default_factory=list)
    orphan_elements: list[str] = field(default_factory=list)

    @property
    def grounding_ratio(self) -> float:
        if self.total_elements == 0:
            return 1.0
        return self.elements_with_citations / self.total_elements

    @property
    def cq_coverage_ratio(self) -> float:
        if self.total_elements == 0:
            return 1.0
        return self.elements_serving_cqs / self.total_elements

    @property
    def connectivity_ratio(self) -> float:
        if self.total_elements == 0:
            return 1.0
        return self.elements_connected_to_seed / self.total_elements

    @property
    def is_healthy(self) -> bool:
        return (
            self.grounding_ratio >= 0.85
            and self.cq_coverage_ratio >= 0.8
            and self.connectivity_ratio >= 0.9
        )


@dataclass
class DriftReport:
    """Report on detected drift patterns."""

    hallucination_spiral: bool = False
    complexity_ratchet: bool = False
    conceptual_drift: bool = False
    echo_chamber: bool = False
    scope_creep: bool = False
    details: list[str] = field(default_factory=list)

    @property
    def any_drift_detected(self) -> bool:
        return any([
            self.hallucination_spiral,
            self.complexity_ratchet,
            self.conceptual_drift,
            self.echo_chamber,
            self.scope_creep,
        ])


class Moderator:
    """Deterministic discourse facilitator.

    The Moderator does not use the LLM. It monitors debate health
    through structural analysis of proposals and agent messages,
    and injects corrective prompts when problems are detected.
    """

    def __init__(
        self,
        thresholds: DriftThresholds | None = None,
        strategy_overrides: dict[Phase, DebateStrategy] | None = None,
    ) -> None:
        self.thresholds = thresholds or DriftThresholds()
        self.strategy_map = {**DEFAULT_STRATEGY_MAP}
        if strategy_overrides:
            self.strategy_map.update(strategy_overrides)

        # Track history for drift detection
        self._revision_sizes: list[int] = []
        self._trivial_consensus_count: int = 0
        self._strategy_fallback_count: int = 0

    # ── Strategy selection ──────────────────────────────────────────

    def select_strategy(
        self,
        phase: Phase,
        prior_failures: int = 0,
    ) -> DebateStrategy:
        """Select debate strategy for a phase.

        Falls back to alternative strategies if the default fails.

        Args:
            phase: Current Ont-101 phase.
            prior_failures: Number of failed debates on this phase.

        Returns:
            The strategy to use.
        """
        default = self.strategy_map.get(phase, DebateStrategy.CONSENSUS_BUILDING)

        if prior_failures == 0:
            return default

        # Fallback sequence: try different philosophical approaches
        fallback_order = [
            DebateStrategy.CONSENSUS_BUILDING,
            DebateStrategy.DIALECTICAL,
            DebateStrategy.SOCRATIC,
            DebateStrategy.ABDUCTIVE,
            DebateStrategy.DELPHI,
        ]

        # Remove the default (already tried)
        fallback_order = [s for s in fallback_order if s != default]

        idx = min(prior_failures - 1, len(fallback_order) - 1)
        selected = fallback_order[idx]

        self._strategy_fallback_count += 1
        logger.info(
            "strategy_fallback",
            phase=phase.value,
            from_strategy=default.value,
            to_strategy=selected.value,
            prior_failures=prior_failures,
        )
        return selected

    # ── Grounding analysis ──────────────────────────────────────────

    def analyze_grounding(
        self,
        proposal: dict[str, Any],
        competency_questions: list[dict] | None = None,
        seed_classes: list[str] | None = None,
    ) -> GroundingReport:
        """Analyze how well-grounded a proposal is.

        Checks three grounding criteria:
        1. Document evidence (citations/evidence fields)
        2. CQ coverage (serves at least one CQ)
        3. Seed connectivity (parent/attachment to seed classes)

        Args:
            proposal: The JSON proposal from an agent.
            competency_questions: List of CQ dicts with 'id' key.
            seed_classes: List of seed ontology class labels.

        Returns:
            GroundingReport with detailed analysis.
        """
        report = GroundingReport()
        cq_ids = {cq.get("id", "") for cq in (competency_questions or [])}
        seed_set = set(seed_classes or [])

        # Collect all proposed elements across different proposal formats
        elements = []
        for key in ("nodes", "classes", "terms", "properties", "facets",
                     "test_instances", "reuse_candidates"):
            elements.extend(proposal.get(key, []))

        report.total_elements = len(elements)

        for elem in elements:
            label = elem.get("label", elem.get("name", elem.get("term", "unknown")))

            # Check document grounding
            has_evidence = bool(
                elem.get("evidence")
                or elem.get("citations")
                or elem.get("document_evidence")
                or elem.get("rationale")  # Weaker but still grounding
            )
            if has_evidence:
                report.elements_with_citations += 1
            else:
                report.ungrounded_elements.append(label)

            # Check CQ coverage
            served_cqs = elem.get("serves_cqs", elem.get("cq_ids", []))
            if served_cqs or elem.get("expected_entity_types"):
                report.elements_serving_cqs += 1

            # Check seed connectivity
            parent = elem.get("parent_uri", elem.get("parent_label",
                     elem.get("attached_to_class", "")))
            if parent and any(s in parent for s in seed_set):
                report.elements_connected_to_seed += 1
            elif not seed_set:
                # If we don't have seed info, give benefit of doubt
                report.elements_connected_to_seed += 1
            else:
                report.orphan_elements.append(label)

        return report

    # ── Drift detection ─────────────────────────────────────────────

    def detect_drift(
        self,
        debate: Debate,
        grounding: GroundingReport,
    ) -> DriftReport:
        """Detect runaway ontology patterns in a debate.

        Watches for five failure modes:
        1. Hallucination spiral: grounding drops below threshold
        2. Complexity ratchet: revisions only add, never remove
        3. Conceptual drift: proposal diverges from documents
        4. Echo chamber: trivial consensus without real examination
        5. Scope creep: elements that serve no competency question

        Args:
            debate: The ongoing debate.
            grounding: Grounding analysis of the latest proposal.

        Returns:
            DriftReport with detected patterns.
        """
        report = DriftReport()

        # 1. Hallucination spiral
        if grounding.grounding_ratio < self.thresholds.min_grounding_ratio:
            report.hallucination_spiral = True
            report.details.append(
                f"Grounding ratio {grounding.grounding_ratio:.2f} "
                f"< threshold {self.thresholds.min_grounding_ratio}. "
                f"Ungrounded elements: {', '.join(grounding.ungrounded_elements[:5])}"
            )

        # 2. Complexity ratchet
        revisions = [m for m in debate.messages if m.message_type == "revision"]
        if revisions:
            current_size = grounding.total_elements
            self._revision_sizes.append(current_size)

            if len(self._revision_sizes) >= self.thresholds.max_additive_revisions:
                recent = self._revision_sizes[-self.thresholds.max_additive_revisions:]
                if all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1)):
                    report.complexity_ratchet = True
                    report.details.append(
                        f"Last {len(recent)} revisions only added elements "
                        f"(sizes: {recent}). No simplification occurred."
                    )

        # 3. Conceptual drift (proxy: too many orphan elements)
        if grounding.connectivity_ratio < 0.6:
            report.conceptual_drift = True
            report.details.append(
                f"Connectivity ratio {grounding.connectivity_ratio:.2f} "
                f"< 0.6. Orphan elements: {', '.join(grounding.orphan_elements[:5])}"
            )

        # 4. Echo chamber
        reviews = [m for m in debate.messages if m.message_type == "review"]
        if reviews:
            recent_reviews = reviews[-3:]  # Last 3 reviews
            if (all(r.approves for r in recent_reviews)
                    and all(len(r.issues_raised) == 0 for r in recent_reviews)):
                self._trivial_consensus_count += 1
                if self._trivial_consensus_count >= self.thresholds.max_trivial_consensus_rounds:
                    report.echo_chamber = True
                    report.details.append(
                        f"All-approve-no-issues for {self._trivial_consensus_count} "
                        f"consecutive rounds. Possible echo chamber."
                    )
            else:
                self._trivial_consensus_count = 0

        # 5. Scope creep
        if grounding.cq_coverage_ratio < 0.8:
            report.scope_creep = True
            report.details.append(
                f"CQ coverage ratio {grounding.cq_coverage_ratio:.2f} "
                f"< 0.8. Elements may not serve competency questions."
            )

        if report.any_drift_detected:
            logger.warning(
                "drift_detected",
                phase=debate.phase.value,
                patterns=[
                    k for k, v in {
                        "hallucination_spiral": report.hallucination_spiral,
                        "complexity_ratchet": report.complexity_ratchet,
                        "conceptual_drift": report.conceptual_drift,
                        "echo_chamber": report.echo_chamber,
                        "scope_creep": report.scope_creep,
                    }.items() if v
                ],
            )

        return report

    # ── Corrective prompt injection ─────────────────────────────────

    def generate_corrective_context(
        self,
        drift: DriftReport,
        grounding: GroundingReport,
    ) -> str:
        """Generate corrective context to inject into the next prompt.

        The Moderator doesn't argue — it *reframes* the discourse by
        injecting structural constraints that redirect agents toward
        grounded reasoning.

        Args:
            drift: The detected drift patterns.
            grounding: The grounding analysis.

        Returns:
            A string to prepend to the next agent's context.
        """
        corrections: list[str] = []

        if drift.hallucination_spiral:
            ungrounded = ", ".join(grounding.ungrounded_elements[:5])
            corrections.append(
                f"⚠ GROUNDING ALERT: The following proposed elements lack "
                f"document evidence: [{ungrounded}]. Either provide specific "
                f"citations from the domain documents or WITHDRAW these elements. "
                f"Current grounding ratio: {grounding.grounding_ratio:.0%}."
            )

        if drift.complexity_ratchet:
            corrections.append(
                "⚠ COMPLEXITY CHECK: Recent revisions have only ADDED elements, "
                "never removed or simplified. Consider: which elements can be "
                "REMOVED or MERGED without losing CQ coverage? Simpler ontologies "
                "are more maintainable and less error-prone."
            )

        if drift.conceptual_drift:
            orphans = ", ".join(grounding.orphan_elements[:5])
            corrections.append(
                f"⚠ DRIFT DETECTED: The following elements are not connected "
                f"to the seed ontology: [{orphans}]. All extensions must attach "
                f"to established classes. Re-anchor your proposal."
            )

        if drift.echo_chamber:
            corrections.append(
                "⚠ ECHO CHAMBER WARNING: Multiple rounds of all-approve with "
                "no issues raised. This may indicate insufficient critical "
                "examination. Reviewers: actively look for weaknesses, edge "
                "cases, and missing alternatives. A proposal that no one "
                "questions may be a proposal no one truly examined."
            )

        if drift.scope_creep:
            corrections.append(
                "⚠ SCOPE CREEP: Some proposed elements do not serve any "
                "competency question. Every element must enable answering "
                "at least one CQ. Remove elements that exist only for "
                "theoretical completeness."
            )

        if not corrections:
            return ""

        header = (
            "━━━ MODERATOR INTERVENTION ━━━\n"
            "The following issues have been detected in the discourse:\n\n"
        )
        footer = (
            "\n\n━━━ END MODERATOR INTERVENTION ━━━\n"
            "Address these issues in your next response."
        )
        return header + "\n\n".join(corrections) + footer

    # ── Debate health assessment ────────────────────────────────────

    def assess_debate_health(self, debate: Debate) -> dict[str, Any]:
        """Produce a health summary of the current debate.

        Returns:
            Dictionary with health indicators.
        """
        messages = debate.messages
        proposals = [m for m in messages if m.message_type in ("proposal", "revision")]
        reviews = [m for m in messages if m.message_type == "review"]

        approve_count = sum(1 for r in reviews if r.approves)
        total_issues = sum(len(r.issues_raised) for r in reviews)

        return {
            "phase": debate.phase.value,
            "strategy": debate.strategy.value,
            "rounds_completed": len(proposals),
            "max_rounds": debate.max_rounds,
            "total_messages": len(messages),
            "approval_rate": approve_count / max(len(reviews), 1),
            "total_issues_raised": total_issues,
            "avg_issues_per_review": total_issues / max(len(reviews), 1),
            "has_consensus": debate.has_consensus,
            "unresolved_issues": len(debate.unresolved_issues),
            "strategy_fallbacks": self._strategy_fallback_count,
        }

    def generate_competency_questions(
        self,
        accepted_classes: list[dict],
        existing_cqs: list[dict] | None = None,
    ) -> list[dict]:
        """Generate competency questions for newly accepted classes.

        The Moderator generates CQs based on the debate outcomes,
        ensuring they reflect the actual extensions made during discourse.

        Args:
            accepted_classes: List of accepted class proposals from the debate.
            existing_cqs: Existing CQs to avoid duplication.

        Returns:
            List of new CQ dictionaries.
        """
        existing_ids = {cq.get("id", "") for cq in (existing_cqs or [])}
        new_cqs = []

        for cls in accepted_classes:
            # Handle both dict and object (ProposedClass)
            if isinstance(cls, dict):
                class_label = cls.get("label", "")
            else:
                class_label = getattr(cls, "label", "")
            
            if not class_label:
                continue

            # Generate 2-3 CQs per class based on debate-discovered needs
            base_id = f"cq_{class_label.lower().replace(' ', '_')}"

            # CQ 1: Properties question
            cq_id = f"{base_id}_properties"
            if cq_id not in existing_ids:
                new_cqs.append({
                    "id": cq_id,
                    "class": class_label,
                    "question": f"What properties does a {class_label} have?",
                    "expected_answer_type": "list",
                    "generated_during": "debate_phase",
                })

            # CQ 2: Hierarchy question
            if isinstance(cls, dict):
                parent = cls.get("parent_label", "entity")
                suggested_relations = cls.get("suggested_relations")
            else:
                parent = getattr(cls, "parent_label", "entity")
                suggested_relations = getattr(cls, "suggested_relations", None)
            
            cq_id = f"{base_id}_hierarchy"
            if cq_id not in existing_ids:
                new_cqs.append({
                    "id": cq_id,
                    "class": class_label,
                    "question": f"Which {parent} instances are also {class_label}?",
                    "expected_answer_type": "list",
                    "generated_during": "debate_phase",
                })

            # CQ 3: Relations question (if relations were proposed)
            if suggested_relations:
                for rel in suggested_relations[:2]:  # Limit to 2 relations
                    rel_name = rel.get("name", "") if isinstance(rel, dict) else getattr(rel, "name", "")
                    rel_range = rel.get("range", "") if isinstance(rel, dict) else getattr(rel, "range", "")
                    if rel_name and rel_range:
                        cq_id = f"{base_id}_rel_{rel_name}"
                        if cq_id not in existing_ids:
                            new_cqs.append({
                                "id": cq_id,
                                "class": class_label,
                                "question": f"What {rel_range} does {class_label} {rel_name}?",
                                "expected_answer_type": "list",
                                "generated_during": "debate_phase",
                            })

        logger.info(
            "generated_cqs",
            new_count=len(new_cqs),
            classes=len(accepted_classes),
        )
        return new_cqs

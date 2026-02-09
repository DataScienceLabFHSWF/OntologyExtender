"""F — Feedback Learning Loop: learn from HITL decisions to improve proposals.

Inspired by the arXiv HITL paper (John et al., 2025) which found that
iterative feedback loops improve quality, and by the general HITL
literature on teaching reasoning systems (Dalvi Mishra et al., 2022).

When a human reviewer accepts or rejects proposals:
1. The decision + rationale are stored as a training signal.
2. Accepted patterns become **few-shot examples** for future proposals.
3. Rejection reasons are used to **bias prompts** against known pitfalls.
4. Acceptance rates are tracked per class type to detect systematic issues.

This is not fine-tuning the LLM — it's dynamic prompt engineering that
incorporates human feedback into the agent system prompts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)


@dataclass
class FeedbackSignal:
    """A single piece of human feedback on a proposal."""

    element_label: str
    element_type: str                # "class", "property", "relation"
    decision: str                    # "accepted", "rejected", "revised"
    rationale: str = ""              # why the reviewer made this decision
    original_proposal: dict = field(default_factory=dict)
    revised_version: dict | None = None  # if "revised", the corrected version
    iteration: int = 0
    phase: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FeedbackPattern:
    """An aggregated pattern from multiple feedback signals."""

    pattern_type: str                # "accepted_class", "rejected_naming", etc.
    count: int = 0
    examples: list[dict] = field(default_factory=list)
    summary: str = ""


@dataclass
class FeedbackMemory:
    """Accumulated feedback across all iterations."""

    signals: list[FeedbackSignal] = field(default_factory=list)
    acceptance_rate: float = 0.0
    rejection_patterns: list[FeedbackPattern] = field(default_factory=list)
    accepted_examples: list[dict] = field(default_factory=list)


class FeedbackLearner:
    """Learn from HITL decisions to improve future proposals.

    Maintains a memory of past feedback signals and generates
    prompt augmentations that bias the agents toward patterns
    the reviewer approves and away from patterns they reject.

    Parameters
    ----------
    settings:
        Application configuration.
    memory_path:
        Path to persist feedback memory across sessions.
    max_few_shot:
        Maximum number of few-shot examples to include in prompts.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        memory_path: str | Path | None = None,
        max_few_shot: int = 5,
    ) -> None:
        self.settings = settings or Settings()
        self.memory_path = Path(memory_path) if memory_path else None
        self.max_few_shot = max_few_shot
        self._signals: list[FeedbackSignal] = []
        self._load_memory()

    # ── Recording feedback ──────────────────────────────────────────

    def record(
        self,
        element_label: str,
        element_type: str,
        decision: str,
        rationale: str = "",
        original_proposal: dict | None = None,
        revised_version: dict | None = None,
        iteration: int = 0,
        phase: str = "",
    ) -> FeedbackSignal:
        """Record a single piece of reviewer feedback.

        Args:
            element_label: Label of the reviewed element.
            element_type: "class", "property", or "relation".
            decision: "accepted", "rejected", or "revised".
            rationale: Human explanation of the decision.
            original_proposal: The proposed element as a dict.
            revised_version: The corrected version (if "revised").
            iteration: Current iteration number.
            phase: Ont-101 phase.

        Returns:
            The recorded ``FeedbackSignal``.
        """
        signal = FeedbackSignal(
            element_label=element_label,
            element_type=element_type,
            decision=decision,
            rationale=rationale,
            original_proposal=original_proposal or {},
            revised_version=revised_version,
            iteration=iteration,
            phase=phase,
        )
        self._signals.append(signal)
        self._save_memory()

        logger.info(
            "feedback_recorded",
            label=element_label,
            decision=decision,
            iteration=iteration,
        )
        return signal

    # ── Prompt augmentation ─────────────────────────────────────────

    def get_few_shot_examples(self, phase: str = "") -> str:
        """Generate few-shot examples from accepted proposals.

        These are injected into the OntologyEngineer's prompt to guide
        it toward patterns the reviewer has approved.

        Args:
            phase: Filter examples to a specific phase (empty = all).

        Returns:
            Formatted text block with examples.
        """
        accepted = [
            s for s in self._signals
            if s.decision == "accepted"
            and (not phase or s.phase == phase)
        ]

        if not accepted:
            return ""

        # Take the most recent examples
        recent = accepted[-self.max_few_shot:]

        lines = ["## Previously Accepted Examples (from reviewer feedback)\n"]
        for s in recent:
            lines.append(f"### {s.element_label} ({s.element_type})")
            if s.original_proposal:
                lines.append(f"```json\n{json.dumps(s.original_proposal, indent=2)}\n```")
            if s.rationale:
                lines.append(f"Reviewer note: {s.rationale}")
            lines.append("")

        return "\n".join(lines)

    def get_rejection_warnings(self, phase: str = "") -> str:
        """Generate warnings from rejected proposals.

        Injected into the OntologyEngineer's prompt as anti-patterns
        to avoid.

        Args:
            phase: Filter to a specific phase.

        Returns:
            Formatted text block with warnings.
        """
        rejected = [
            s for s in self._signals
            if s.decision == "rejected"
            and (not phase or s.phase == phase)
        ]

        if not rejected:
            return ""

        # Aggregate rejection reasons
        reasons: dict[str, int] = {}
        for s in rejected:
            key = s.rationale[:100] if s.rationale else "unspecified"
            reasons[key] = reasons.get(key, 0) + 1

        lines = ["## Common Rejection Reasons (avoid these patterns)\n"]
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            lines.append(f"- ({count}x) {reason}")

        # Show recent rejection examples
        recent = rejected[-3:]
        if recent:
            lines.append("\n### Recent Rejected Examples")
            for s in recent:
                lines.append(
                    f"- **{s.element_label}**: {s.rationale or 'no reason given'}"
                )

        return "\n".join(lines)

    def augment_prompt(self, base_prompt: str, phase: str = "") -> str:
        """Augment an agent prompt with feedback-derived context.

        Adds few-shot examples and rejection warnings to help the
        agent learn from past HITL decisions.

        Args:
            base_prompt: The original agent prompt.
            phase: Current Ont-101 phase for filtering.

        Returns:
            Augmented prompt string.
        """
        parts = [base_prompt]

        examples = self.get_few_shot_examples(phase)
        if examples:
            parts.append("\n\n" + examples)

        warnings = self.get_rejection_warnings(phase)
        if warnings:
            parts.append("\n\n" + warnings)

        return "\n".join(parts)

    # ── Analytics ───────────────────────────────────────────────────

    def acceptance_rate(self, element_type: str | None = None) -> float:
        """Compute acceptance rate, optionally filtered by element type.

        Args:
            element_type: "class", "property", "relation", or ``None`` for all.

        Returns:
            Acceptance rate as a float (0.0 – 1.0).
        """
        signals = (
            [s for s in self._signals if s.element_type == element_type]
            if element_type else self._signals
        )
        if not signals:
            return 0.0
        accepted = sum(1 for s in signals if s.decision == "accepted")
        return accepted / len(signals)

    def acceptance_trend(self, window: int = 5) -> list[float]:
        """Compute rolling acceptance rate over recent signals.

        Args:
            window: Window size for rolling average.

        Returns:
            List of acceptance rates per window.
        """
        if len(self._signals) < window:
            return [self.acceptance_rate()]

        rates = []
        for i in range(window, len(self._signals) + 1):
            chunk = self._signals[i - window:i]
            accepted = sum(1 for s in chunk if s.decision == "accepted")
            rates.append(accepted / window)
        return rates

    def get_memory(self) -> FeedbackMemory:
        """Return the full feedback memory as a structured report."""
        return FeedbackMemory(
            signals=list(self._signals),
            acceptance_rate=self.acceptance_rate(),
            accepted_examples=[
                s.original_proposal for s in self._signals
                if s.decision == "accepted" and s.original_proposal
            ][-self.max_few_shot:],
        )

    # ── Persistence ─────────────────────────────────────────────────

    def _save_memory(self) -> None:
        """Persist feedback signals to disk."""
        if not self.memory_path:
            return

        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "element_label": s.element_label,
                "element_type": s.element_type,
                "decision": s.decision,
                "rationale": s.rationale,
                "original_proposal": s.original_proposal,
                "revised_version": s.revised_version,
                "iteration": s.iteration,
                "phase": s.phase,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in self._signals
        ]
        self.memory_path.write_text(json.dumps(data, indent=2))

    def _load_memory(self) -> None:
        """Load previously saved feedback signals."""
        if not self.memory_path or not self.memory_path.exists():
            return

        try:
            data = json.loads(self.memory_path.read_text())
            for item in data:
                self._signals.append(FeedbackSignal(
                    element_label=item.get("element_label", ""),
                    element_type=item.get("element_type", ""),
                    decision=item.get("decision", ""),
                    rationale=item.get("rationale", ""),
                    original_proposal=item.get("original_proposal", {}),
                    revised_version=item.get("revised_version"),
                    iteration=item.get("iteration", 0),
                    phase=item.get("phase", ""),
                    timestamp=datetime.fromisoformat(item["timestamp"])
                    if "timestamp" in item else datetime.now(),
                ))
            logger.info("feedback_memory_loaded", signals=len(self._signals))
        except Exception as e:
            logger.warning("feedback_memory_load_failed", error=str(e))

    def signal_count(self) -> int:
        """Total number of feedback signals recorded."""
        return len(self._signals)

    def clear(self) -> None:
        """Clear all feedback signals."""
        self._signals.clear()
        if self.memory_path and self.memory_path.exists():
            self.memory_path.unlink()

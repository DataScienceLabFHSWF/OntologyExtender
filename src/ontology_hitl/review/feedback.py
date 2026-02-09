"""C1.4.3 — FeedbackCollector: persist and analyze expert review feedback."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from ontology_hitl.core.models import ReviewDecision

logger = structlog.get_logger(__name__)


class FeedbackCollector:
    """Collect, persist, and analyze expert review feedback.

    Tracks acceptance/rejection patterns and expert agreement rates.
    """

    def __init__(self, storage_dir: Path | str = "data/feedback") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._decisions: list[ReviewDecision] = []

    def save_decision(self, decision: ReviewDecision) -> None:
        """Persist a review decision."""
        self._decisions.append(decision)
        self._write_to_disk()
        logger.info(
            "decision_saved",
            proposal_id=decision.proposal_id,
            decision=decision.decision,
            reviewer=decision.reviewer,
        )

    def get_decisions(self, proposal_id: str) -> list[ReviewDecision]:
        """Get all decisions for a specific proposal."""
        return [d for d in self._decisions if d.proposal_id == proposal_id]

    def get_all_decisions(self) -> list[ReviewDecision]:
        """Get all stored decisions."""
        return list(self._decisions)

    def compute_agreement_rate(self) -> float:
        """Compute inter-reviewer agreement rate.

        Returns:
            Agreement rate as float (0.0 to 1.0).
        """
        # Group by proposal_id
        from collections import defaultdict

        grouped: dict[str, list[ReviewDecision]] = defaultdict(list)
        for d in self._decisions:
            grouped[d.proposal_id].append(d)

        if not grouped:
            return 0.0

        agreements = 0
        multi_review = 0
        for pid, decisions in grouped.items():
            if len(decisions) < 2:
                continue
            multi_review += 1
            # Check if all reviewers agree
            verdicts = {d.decision for d in decisions}
            if len(verdicts) == 1:
                agreements += 1

        return agreements / multi_review if multi_review > 0 else 0.0

    def _write_to_disk(self) -> None:
        """Write current decisions to JSON file."""
        path = self.storage_dir / "decisions_log.json"
        data = [
            {
                "proposal_id": d.proposal_id,
                "reviewer": d.reviewer,
                "decision": d.decision,
                "rationale": d.rationale,
                "timestamp": d.timestamp.isoformat(),
                "confidence": d.confidence_in_decision,
            }
            for d in self._decisions
        ]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

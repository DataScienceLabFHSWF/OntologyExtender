"""Tests for FeedbackCollector."""

from __future__ import annotations

from pathlib import Path

from ontology_hitl.review.feedback import FeedbackCollector
from ontology_hitl.core.models import ReviewDecision


class TestFeedbackCollector:
    """Test feedback collection and persistence."""

    def test_save_and_retrieve_decision(self, tmp_path: Path) -> None:
        """Test saving and retrieving a decision."""
        collector = FeedbackCollector(storage_dir=tmp_path / "feedback")
        decision = ReviewDecision(
            proposal_id="prop_001",
            reviewer="expert_1",
            decision="accepted",
            rationale="Good class definition.",
        )
        collector.save_decision(decision)

        retrieved = collector.get_decisions("prop_001")
        assert len(retrieved) == 1
        assert retrieved[0].decision == "accepted"

    def test_agreement_rate_single_reviewer(self, tmp_path: Path) -> None:
        """Test agreement rate with single reviewer per proposal."""
        collector = FeedbackCollector(storage_dir=tmp_path / "feedback")
        collector.save_decision(ReviewDecision(
            proposal_id="prop_001",
            reviewer="expert_1",
            decision="accepted",
        ))
        # Single reviewer → no multi-review pairs → 0.0
        assert collector.compute_agreement_rate() == 0.0

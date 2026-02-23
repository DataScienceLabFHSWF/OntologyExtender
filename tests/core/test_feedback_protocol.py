"""Tests for the feedback loop protocol and orchestrator."""

from __future__ import annotations

import pytest

from ontology_hitl.core.feedback_protocol import (
    ConvergenceReport,
    FeedbackMetrics,
    IterationPlan,
    LoopMode,
)


class TestFeedbackMetrics:
    def test_defaults(self):
        m = FeedbackMetrics(iteration=1)
        assert m.entity_coverage_pct == 0.0
        assert m.cq_coverage_pct == 0.0
        assert m.mode == "standalone"

    def test_improvement_tracking(self):
        m1 = FeedbackMetrics(iteration=1, entity_coverage_pct=0.40)
        m2 = FeedbackMetrics(iteration=2, entity_coverage_pct=0.65)
        m2.improvement_over_previous = m2.entity_coverage_pct - m1.entity_coverage_pct
        assert m2.improvement_over_previous == pytest.approx(0.25)


class TestConvergenceReport:
    def test_compute_summary_empty(self):
        report = ConvergenceReport(total_iterations=0, mode="standalone")
        assert report.compute_summary() == {}

    def test_compute_summary_with_iterations(self):
        metrics = [
            FeedbackMetrics(iteration=1, entity_coverage_pct=0.30,
                            cq_coverage_pct=0.20, classes_added_this_iter=8,
                            acceptance_rate=0.8, improvement_over_previous=0.30, questions_for_review=2),
            FeedbackMetrics(iteration=2, entity_coverage_pct=0.55,
                            cq_coverage_pct=0.50, classes_added_this_iter=6,
                            acceptance_rate=0.75, improvement_over_previous=0.25, questions_for_review=3),
            FeedbackMetrics(iteration=3, entity_coverage_pct=0.70,
                            cq_coverage_pct=0.65, classes_added_this_iter=4,
                            acceptance_rate=0.9, improvement_over_previous=0.15, questions_for_review=1),
            FeedbackMetrics(iteration=4, entity_coverage_pct=0.71,
                            cq_coverage_pct=0.66, classes_added_this_iter=1,
                            acceptance_rate=0.5, improvement_over_previous=0.01, questions_for_review=0),
        ]

        report = ConvergenceReport(
            total_iterations=4,
            mode="standalone",
            metrics_per_iteration=metrics,
            convergence_threshold=0.02,
        )
        summary = report.compute_summary()

        assert summary["entity_coverage"]["initial"] == 0.30
        assert summary["entity_coverage"]["final"] == 0.71
        assert summary["entity_coverage"]["delta"] == pytest.approx(0.41)
        assert summary["converged_at"] == 4  # iteration 4 had <2% improvement
        assert summary["classes_added_total"] == 19

    def test_no_convergence(self):
        """All iterations have >2% improvement → no convergence."""
        metrics = [
            FeedbackMetrics(iteration=1, improvement_over_previous=0.30),
            FeedbackMetrics(iteration=2, improvement_over_previous=0.20),
        ]
        report = ConvergenceReport(
            total_iterations=2, mode="coupled",
            metrics_per_iteration=metrics,
        )
        summary = report.compute_summary()
        assert summary["converged_at"] is None


class TestIterationPlan:
    def test_plan_fields(self):
        plan = IterationPlan(
            iteration=1,
            mode=LoopMode.STANDALONE,
            focus_entity_types=["Facility", "Permit"],
            max_proposals=15,
        )
        assert plan.mode == LoopMode.STANDALONE
        assert len(plan.focus_entity_types) == 2


class TestLoopMode:
    def test_enum_values(self):
        assert LoopMode.COUPLED.value == "coupled"
        assert LoopMode.STANDALONE.value == "standalone"

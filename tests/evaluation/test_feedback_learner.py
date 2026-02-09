"""Tests for F — Feedback Learning Loop (evaluation.feedback_learner)."""

from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from ontology_hitl.evaluation.feedback_learner import (
    FeedbackLearner,
    FeedbackMemory,
    FeedbackPattern,
    FeedbackSignal,
)


# ── Data models ─────────────────────────────────────────────────────

def test_feedback_signal():
    s = FeedbackSignal(
        element_label="Reactor",
        element_type="class",
        decision="accepted",
        rationale="Good placement",
    )
    assert s.decision == "accepted"
    assert s.element_label == "Reactor"


def test_feedback_pattern():
    p = FeedbackPattern(
        pattern_type="rejected_naming",
        count=3,
        summary="Lowercase class names were rejected",
    )
    assert p.count == 3


def test_feedback_memory():
    m = FeedbackMemory(signals=[], acceptance_rate=0.0)
    assert len(m.signals) == 0


# ── Recording ───────────────────────────────────────────────────────

def test_record_accept():
    learner = FeedbackLearner()
    learner.record("Reactor", "class", "accepted", "LGTM")
    assert learner.signal_count() == 1
    assert learner._signals[0].decision == "accepted"


def test_record_reject():
    learner = FeedbackLearner()
    learner.record("Motor", "class", "rejected", "Wrong parent")
    assert learner.signal_count() == 1
    assert learner._signals[0].decision == "rejected"


# ── Few-shot examples ──────────────────────────────────────────────

def test_few_shot_returns_string():
    learner = FeedbackLearner(max_few_shot=2)
    for i in range(5):
        learner.record(f"C{i}", "class", "accepted", f"ok{i}")
    examples = learner.get_few_shot_examples()
    assert isinstance(examples, str)
    assert "Previously Accepted" in examples


def test_few_shot_empty():
    learner = FeedbackLearner()
    assert learner.get_few_shot_examples() == ""


# ── Rejection warnings ─────────────────────────────────────────────

def test_rejection_warnings():
    learner = FeedbackLearner()
    learner.record("Motor", "class", "rejected", "Should be Actuator")
    learner.record("Motor", "class", "rejected", "Actuator is better")
    warnings = learner.get_rejection_warnings()
    # Should have a warning about Motor being rejected
    assert "Motor" in warnings or "Rejection" in warnings


def test_no_warnings_when_accepted():
    learner = FeedbackLearner()
    learner.record("Motor", "class", "accepted", "OK")
    learner.record("Motor", "class", "accepted", "Fine")
    warnings = learner.get_rejection_warnings()
    assert warnings == ""


# ── Prompt augmentation ────────────────────────────────────────────

def test_augment_prompt_adds_examples():
    learner = FeedbackLearner()
    learner.record("Pump", "class", "accepted", "Perfect")
    result = learner.augment_prompt("Place this class.")
    assert "Place this class." in result
    assert "Pump" in result


def test_augment_prompt_no_history():
    learner = FeedbackLearner()
    result = learner.augment_prompt("Place this class.")
    # No feedback → no augmentation
    assert "Place this class." in result


# ── Acceptance rate / trend ─────────────────────────────────────────

def test_acceptance_rate():
    learner = FeedbackLearner()
    learner.record("A", "class", "accepted")
    learner.record("B", "class", "rejected")
    learner.record("C", "class", "accepted")
    assert learner.acceptance_rate() == pytest.approx(2 / 3)


def test_acceptance_rate_empty():
    learner = FeedbackLearner()
    assert learner.acceptance_rate() == 0.0


def test_acceptance_trend():
    learner = FeedbackLearner()
    for i in range(10):
        decision = "accepted" if i >= 5 else "rejected"
        learner.record(f"C{i}", "class", decision)
    trend = learner.acceptance_trend(window=5)
    assert trend[-1] == 1.0  # last 5 all accepted


# ── Persistence ─────────────────────────────────────────────────────

def test_persistence_save_load():
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "memory.json"
        learner = FeedbackLearner(memory_path=path)
        learner.record("Pump", "class", "accepted", "Good")

        # Memory was auto-saved; create a new learner that loads from the path
        learner2 = FeedbackLearner(memory_path=path)
        assert learner2.signal_count() == 1
        assert learner2._signals[0].element_label == "Pump"


def test_clear():
    learner = FeedbackLearner()
    learner.record("A", "class", "accepted")
    learner.record("C", "class", "rejected")
    learner.clear()
    assert learner.signal_count() == 0


# ── Memory model ────────────────────────────────────────────────────

def test_get_memory_snapshot():
    learner = FeedbackLearner()
    learner.record("X", "class", "accepted")
    mem = learner.get_memory()
    assert len(mem.signals) == 1
    assert mem.acceptance_rate == 1.0

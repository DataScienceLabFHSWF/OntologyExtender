"""Tests for E — Ensemble Strategy (discovery.ensemble_strategy)."""

from __future__ import annotations

import pytest

from ontology_hitl.discovery.ensemble_strategy import (
    EnsembleDecision,
    EnsembleReport,
    EnsembleStrategy,
    StrategyName,
    StrategyVote,
)


# ── Data models ─────────────────────────────────────────────────────

def test_strategy_vote_creation():
    vote = StrategyVote(
        strategy=StrategyName.LLM,
        proposed_label="Facility",
        recommended_parent_uri="http://ex.org/Thing",
        recommended_parent_label="Thing",
        confidence=0.9,
    )
    assert vote.strategy == StrategyName.LLM


def test_ensemble_decision():
    d = EnsembleDecision(
        proposed_label="Facility",
        final_parent_uri="http://ex.org/Thing",
        final_parent_label="Thing",
        final_confidence=0.8,
        agreement_score=1.0,
    )
    assert d.agreement_score == 1.0


# ── Aggregation ─────────────────────────────────────────────────────

def test_aggregate_unanimous():
    """All three strategies agree on the same parent."""
    strategy = EnsembleStrategy()

    votes = {
        "Facility": [
            StrategyVote(StrategyName.LLM, "Facility", "http://ex.org/T", "T", 0.9),
            StrategyVote(StrategyName.EMBEDDING, "Facility", "http://ex.org/T", "T", 0.85),
            StrategyVote(StrategyName.COOCCURRENCE, "Facility", "http://ex.org/T", "T", 0.7),
        ],
    }

    report = strategy.aggregate(votes)
    assert len(report.decisions) == 1
    d = report.decisions[0]
    assert d.final_parent_uri == "http://ex.org/T"
    assert d.agreement_score == 1.0
    assert report.unanimous_count == 1


def test_aggregate_split():
    """Strategies disagree on parent."""
    strategy = EnsembleStrategy()

    votes = {
        "Facility": [
            StrategyVote(StrategyName.LLM, "Facility", "http://ex.org/A", "A", 0.9),
            StrategyVote(StrategyName.EMBEDDING, "Facility", "http://ex.org/B", "B", 0.85),
            StrategyVote(StrategyName.COOCCURRENCE, "Facility", "http://ex.org/C", "C", 0.7),
        ],
    }

    report = strategy.aggregate(votes)
    d = report.decisions[0]
    # LLM has highest weight (0.5) and highest confidence (0.9)
    assert d.final_parent_uri == "http://ex.org/A"
    assert d.agreement_score < 1.0


def test_aggregate_two_agree():
    """Two out of three agree."""
    strategy = EnsembleStrategy()

    votes = {
        "Facility": [
            StrategyVote(StrategyName.LLM, "Facility", "http://ex.org/X", "X", 0.8),
            StrategyVote(StrategyName.EMBEDDING, "Facility", "http://ex.org/X", "X", 0.7),
            StrategyVote(StrategyName.COOCCURRENCE, "Facility", "http://ex.org/Y", "Y", 0.9),
        ],
    }

    report = strategy.aggregate(votes)
    d = report.decisions[0]
    assert d.final_parent_uri == "http://ex.org/X"
    assert d.agreement_score == pytest.approx(2 / 3)


def test_aggregate_empty():
    strategy = EnsembleStrategy()
    report = strategy.aggregate({})
    assert len(report.decisions) == 0


def test_aggregate_no_votes():
    strategy = EnsembleStrategy()
    report = strategy.aggregate({"X": []})
    assert len(report.decisions) == 1
    assert report.decisions[0].final_parent_uri == ""


# ── Custom weights ──────────────────────────────────────────────────

def test_custom_weights():
    """With embedding weight >> LLM, embedding's choice should win."""
    strategy = EnsembleStrategy(weights={
        StrategyName.LLM: 0.1,
        StrategyName.EMBEDDING: 0.8,
        StrategyName.COOCCURRENCE: 0.1,
    })

    votes = {
        "X": [
            StrategyVote(StrategyName.LLM, "X", "http://ex.org/A", "A", 1.0),
            StrategyVote(StrategyName.EMBEDDING, "X", "http://ex.org/B", "B", 1.0),
            StrategyVote(StrategyName.COOCCURRENCE, "X", "http://ex.org/A", "A", 1.0),
        ],
    }

    report = strategy.aggregate(votes)
    d = report.decisions[0]
    # Embedding (weight 0.8) should outweigh LLM + cooccurrence (0.1 + 0.1)
    assert d.final_parent_uri == "http://ex.org/B"


# ── Co-occurrence votes ─────────────────────────────────────────────

def test_cooccurrence_votes():
    proposed = [{"label": "Reactor"}]
    documents = [
        "The reactor is part of the facility complex.",
        "A facility contains multiple reactors.",
        "The reactor generates power alongside other equipment.",
    ]
    seed = [
        {"uri": "http://ex.org/Facility", "label": "Facility"},
        {"uri": "http://ex.org/Equipment", "label": "Equipment"},
    ]

    votes = EnsembleStrategy.compute_cooccurrence_votes(
        proposed, documents, seed,
    )

    assert len(votes) == 1
    v = votes[0]
    assert v.strategy == StrategyName.COOCCURRENCE
    # "Facility" co-occurs with "Reactor" in 2 chunks
    assert v.recommended_parent_label == "Facility"


def test_cooccurrence_no_match():
    votes = EnsembleStrategy.compute_cooccurrence_votes(
        [{"label": "QuantumEntangler"}],
        ["No relevant text here"],
        [{"uri": "http://ex.org/X", "label": "X"}],
    )
    assert len(votes) == 1
    assert votes[0].confidence == 0.0

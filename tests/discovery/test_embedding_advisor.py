"""Tests for C — Embedding Advisor (discovery.embedding_advisor)."""

from __future__ import annotations

import pytest

from ontology_hitl.discovery.embedding_advisor import (
    EmbeddingAdvisor,
    EmbeddingAdvisorReport,
    ParentRecommendation,
)


# ── Data model tests ────────────────────────────────────────────────

def test_parent_recommendation_creation():
    rec = ParentRecommendation(
        proposed_label="Facility",
        recommended_parent_uri="http://ex.org/Thing",
        recommended_parent_label="Thing",
        similarity=0.85,
        structural_confidence=0.3,
    )
    assert rec.similarity == 0.85
    assert rec.structural_confidence == 0.3


def test_advisor_report_creation():
    report = EmbeddingAdvisorReport(
        recommendations=[],
        avg_confidence=0.0,
        model_used="gemma4:31b",
    )
    assert report.model_used == "gemma4:31b"


# ── Cosine similarity ──────────────────────────────────────────────

def test_cosine_similarity():
    assert EmbeddingAdvisor._cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert EmbeddingAdvisor._cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert EmbeddingAdvisor._cosine_similarity([0, 0], [1, 1]) == 0.0


# ── Index + recommend with mock embeddings ──────────────────────────

def test_recommend_parents_no_seed():
    advisor = EmbeddingAdvisor()
    report = advisor.recommend_parents([{"label": "X", "definition": "test"}])
    assert len(report.recommendations) == 0


def test_recommend_parents_with_mocked_embeddings():
    """Test recommendation with injected embeddings (no Ollama needed)."""
    advisor = EmbeddingAdvisor()

    # Manually set up seed embeddings
    advisor._seed_embeddings = {
        "http://ex.org/Thing": [1.0, 0.0, 0.0],
        "http://ex.org/Process": [0.0, 1.0, 0.0],
        "http://ex.org/Agent": [0.0, 0.0, 1.0],
    }
    advisor._seed_info = {
        "http://ex.org/Thing": {"label": "Thing", "definition": ""},
        "http://ex.org/Process": {"label": "Process", "definition": ""},
        "http://ex.org/Agent": {"label": "Agent", "definition": ""},
    }

    # Inject embedding for proposed class close to "Thing"
    advisor._cache["Facility: A physical place"] = [0.95, 0.05, 0.0]

    report = advisor.recommend_parents([
        {"label": "Facility", "definition": "A physical place"},
    ])

    assert len(report.recommendations) == 1
    rec = report.recommendations[0]
    assert rec.proposed_label == "Facility"
    assert rec.recommended_parent_uri == "http://ex.org/Thing"
    assert rec.similarity > 0.9


def test_structural_confidence():
    """Confidence should be the gap between 1st and 2nd best parent."""
    advisor = EmbeddingAdvisor()

    advisor._seed_embeddings = {
        "http://ex.org/A": [1.0, 0.0],
        "http://ex.org/B": [0.9, 0.1],  # close to A
    }
    advisor._seed_info = {
        "http://ex.org/A": {"label": "A", "definition": ""},
        "http://ex.org/B": {"label": "B", "definition": ""},
    }
    advisor._cache["X: test"] = [1.0, 0.0]

    report = advisor.recommend_parents([{"label": "X", "definition": "test"}])
    rec = report.recommendations[0]

    # Both are close, so confidence (gap) should be small
    assert rec.structural_confidence < 0.5


# ── Cache management ────────────────────────────────────────────────

def test_clear_cache():
    advisor = EmbeddingAdvisor()
    advisor._cache["test"] = [1.0]
    advisor._seed_embeddings["x"] = [1.0]
    advisor.clear_cache()
    assert len(advisor._cache) == 0
    assert len(advisor._seed_embeddings) == 0

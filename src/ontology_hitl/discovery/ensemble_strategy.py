"""E — Ensemble Strategy: multi-strategy class hierarchy placement.

Inspired by the DFG project (Mossakowski, 2023+) finding that different
ML approaches suit different entity types, and the box embeddings paper
(Memariani et al., 2025) showing that structural signals complement
text-based classification.

Instead of relying on a single LLM for hierarchy placement, the ensemble
combines three independent strategies:

1. **LLM-based** (OntologyEngineer) — the current approach;
   reasons about definitions, Ont-101 rules, and methodology.
2. **Embedding-based** (EmbeddingAdvisor) — cosine similarity between
   proposed class and seed class embeddings via Ollama.
3. **Frequency/co-occurrence** — statistical signal from documents;
   classes that co-occur in the same chunks are more likely siblings.

The ``EnsembleStrategy`` aggregates these into a final recommendation
via weighted voting.  Weights can be tuned per domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)


class StrategyName(str, Enum):
    """Available classification strategies."""

    LLM = "llm"                    # OntologyEngineer proposal
    EMBEDDING = "embedding"        # EmbeddingAdvisor cosine similarity
    COOCCURRENCE = "cooccurrence"  # Document frequency / co-occurrence


@dataclass
class StrategyVote:
    """A single strategy's recommendation for one class."""

    strategy: StrategyName
    proposed_label: str
    recommended_parent_uri: str
    recommended_parent_label: str
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class EnsembleDecision:
    """Aggregated decision for one class across all strategies."""

    proposed_label: str
    final_parent_uri: str
    final_parent_label: str
    final_confidence: float = 0.0
    votes: list[StrategyVote] = field(default_factory=list)
    agreement_score: float = 0.0   # 0-1: how many strategies agree
    decision_method: str = "weighted_vote"


@dataclass
class EnsembleReport:
    """Output of the ensemble strategy for all proposed classes."""

    decisions: list[EnsembleDecision] = field(default_factory=list)
    avg_agreement: float = 0.0
    avg_confidence: float = 0.0
    unanimous_count: int = 0
    split_count: int = 0


class EnsembleStrategy:
    """Aggregate multiple classification strategies via weighted voting.

    Parameters
    ----------
    settings:
        Application configuration.
    weights:
        Weight per strategy (higher = more influence).
        Default: LLM=0.5, Embedding=0.3, Co-occurrence=0.2.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        weights: dict[StrategyName, float] | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.weights = weights or {
            StrategyName.LLM: 0.5,
            StrategyName.EMBEDDING: 0.3,
            StrategyName.COOCCURRENCE: 0.2,
        }

    # ── Main API ────────────────────────────────────────────────────

    def aggregate(
        self,
        votes_per_class: dict[str, list[StrategyVote]],
    ) -> EnsembleReport:
        """Aggregate strategy votes into final decisions.

        Args:
            votes_per_class: ``{proposed_label: [StrategyVote, ...]}``.

        Returns:
            ``EnsembleReport`` with final decisions.
        """
        decisions: list[EnsembleDecision] = []
        unanimous = 0
        split = 0

        for label, votes in votes_per_class.items():
            decision = self._decide(label, votes)
            decisions.append(decision)
            if decision.agreement_score >= 1.0:
                unanimous += 1
            elif decision.agreement_score < 0.5:
                split += 1

        avg_agree = (
            sum(d.agreement_score for d in decisions) / len(decisions)
            if decisions else 0.0
        )
        avg_conf = (
            sum(d.final_confidence for d in decisions) / len(decisions)
            if decisions else 0.0
        )

        report = EnsembleReport(
            decisions=decisions,
            avg_agreement=avg_agree,
            avg_confidence=avg_conf,
            unanimous_count=unanimous,
            split_count=split,
        )

        logger.info(
            "ensemble_complete",
            classes=len(decisions),
            unanimous=unanimous,
            split=split,
            avg_agreement=f"{avg_agree:.2f}",
        )
        return report

    # ── Co-occurrence signal ────────────────────────────────────────

    @staticmethod
    def compute_cooccurrence_votes(
        proposed_classes: list[dict[str, str]],
        document_chunks: list[str],
        seed_classes: list[dict[str, str]],
    ) -> list[StrategyVote]:
        """Compute parent recommendations based on co-occurrence.

        If a proposed class label frequently co-occurs with a seed class
        label in the same document chunks, they are likely related.

        Args:
            proposed_classes: ``[{label, definition}]``.
            document_chunks: Raw text chunks from Qdrant.
            seed_classes: ``[{uri, label}]``.

        Returns:
            List of ``StrategyVote`` objects.
        """
        votes: list[StrategyVote] = []

        for proposed in proposed_classes:
            plabel = proposed.get("label", "").lower()
            if not plabel:
                continue

            # Count co-occurrences with each seed class
            cooccur: dict[str, int] = {}
            for chunk in document_chunks:
                chunk_lower = chunk.lower()
                if plabel in chunk_lower:
                    for seed in seed_classes:
                        slabel = seed.get("label", "").lower()
                        if slabel and slabel in chunk_lower:
                            cooccur[seed.get("uri", "")] = cooccur.get(
                                seed.get("uri", ""), 0
                            ) + 1

            if cooccur:
                best_uri = max(cooccur, key=cooccur.get)  # type: ignore[arg-type]
                best_count = cooccur[best_uri]
                total = sum(cooccur.values())
                confidence = best_count / total if total > 0 else 0.0

                best_info = next(
                    (s for s in seed_classes if s.get("uri") == best_uri), {}
                )

                votes.append(StrategyVote(
                    strategy=StrategyName.COOCCURRENCE,
                    proposed_label=proposed.get("label", ""),
                    recommended_parent_uri=best_uri,
                    recommended_parent_label=best_info.get("label", ""),
                    confidence=confidence,
                    reasoning=f"Co-occurred {best_count} times in {len(document_chunks)} chunks",
                ))
            else:
                votes.append(StrategyVote(
                    strategy=StrategyName.COOCCURRENCE,
                    proposed_label=proposed.get("label", ""),
                    recommended_parent_uri="",
                    recommended_parent_label="",
                    confidence=0.0,
                    reasoning="No co-occurrence signal found",
                ))

        return votes

    # ── Internal ────────────────────────────────────────────────────

    def _decide(
        self,
        label: str,
        votes: list[StrategyVote],
    ) -> EnsembleDecision:
        """Weighted aggregation for a single class."""
        if not votes:
            return EnsembleDecision(
                proposed_label=label,
                final_parent_uri="",
                final_parent_label="",
            )

        # Aggregate scores per candidate parent
        parent_scores: dict[str, float] = {}
        parent_labels: dict[str, str] = {}

        for vote in votes:
            w = self.weights.get(vote.strategy, 0.0)
            uri = vote.recommended_parent_uri
            if not uri:
                continue
            parent_scores[uri] = parent_scores.get(uri, 0.0) + w * vote.confidence
            parent_labels[uri] = vote.recommended_parent_label

        if not parent_scores:
            return EnsembleDecision(
                proposed_label=label,
                final_parent_uri="",
                final_parent_label="",
                votes=votes,
            )

        # Winner
        best_uri = max(parent_scores, key=parent_scores.get)  # type: ignore[arg-type]
        best_score = parent_scores[best_uri]
        total_weight = sum(self.weights.values())
        normalised = best_score / total_weight if total_weight > 0 else 0.0

        # Agreement: fraction of strategies that voted for the winner
        agreeing = sum(
            1 for v in votes
            if v.recommended_parent_uri == best_uri and v.recommended_parent_uri
        )
        agreement = agreeing / len(votes) if votes else 0.0

        return EnsembleDecision(
            proposed_label=label,
            final_parent_uri=best_uri,
            final_parent_label=parent_labels.get(best_uri, ""),
            final_confidence=normalised,
            votes=votes,
            agreement_score=agreement,
        )

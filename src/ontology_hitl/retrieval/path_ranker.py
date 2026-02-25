"""Relation-aware path ranker — re-ranks graph paths by ontology relevance.

Ported from GraphQAAgent.  Inspired by PathCon (Wang et al. 2021) and PRA
(Lao et al. 2011).  Scores paths by semantic relevance to the question
using expected ontology relations to boost matching paths.
"""

from __future__ import annotations

import structlog

from ontology_hitl.core.models import KGRelation, QAQuery, RetrievedContext

logger = structlog.get_logger(__name__)


class PathRanker:
    """Score and re-rank graph paths by ontology-relevance to the query.

    Scoring formula for a path P = [r1, r2, ..., rn]::

        path_score(P) = α * avg_confidence(P)
                      + β * relation_relevance(P, expected_relations)
                      + γ * path_length_penalty(P)
    """

    def __init__(
        self,
        *,
        alpha: float = 0.4,
        beta: float = 0.45,
        gamma: float = 0.15,
    ) -> None:
        self._alpha = alpha
        self._beta = beta
        self._gamma = gamma

    def rank_paths(
        self,
        contexts: list[RetrievedContext],
        query: QAQuery,
    ) -> list[RetrievedContext]:
        """Re-rank graph contexts by ontology-informed path scores."""
        expected = set(r.lower() for r in query.expected_relations)
        scored: list[tuple[RetrievedContext, float]] = []

        for ctx in contexts:
            if ctx.subgraph:
                relations = [
                    el for el in ctx.subgraph if isinstance(el, KGRelation)
                ]
                score = self._score_path(relations, expected)
                ctx.score = score
            scored.append((ctx, ctx.score))

        scored.sort(key=lambda x: x[1], reverse=True)

        ranked = [ctx for ctx, _ in scored]
        logger.info(
            "path_ranker.ranked",
            total=len(contexts),
            with_subgraph=sum(1 for c in contexts if c.subgraph),
            expected_relations=len(expected),
        )
        return ranked

    def _score_path(
        self,
        relations: list[KGRelation],
        expected_relations: set[str],
    ) -> float:
        if not relations:
            return 0.0

        avg_conf = sum(r.confidence for r in relations) / len(relations)

        if expected_relations:
            matches = sum(
                1
                for r in relations
                if r.relation_type.lower() in expected_relations
                or any(exp in r.relation_type.lower() for exp in expected_relations)
            )
            rel_relevance = matches / len(relations)
        else:
            rel_relevance = 0.5

        length_score = 1.0 / len(relations)

        score = (
            self._alpha * avg_conf
            + self._beta * rel_relevance
            + self._gamma * length_score
        )
        return min(max(score, 0.0), 1.0)

    @staticmethod
    def explain_score(
        relations: list[KGRelation],
        expected_relations: set[str],
    ) -> dict[str, float | list[str]]:
        """Break down the path score for transparency/debugging."""
        if not relations:
            return {"avg_confidence": 0.0, "relation_relevance": 0.0, "path_length": 0}

        matched = [
            r.relation_type
            for r in relations
            if r.relation_type.lower() in expected_relations
            or any(exp in r.relation_type.lower() for exp in expected_relations)
        ]
        return {
            "avg_confidence": sum(r.confidence for r in relations) / len(relations),
            "relation_relevance": len(matched) / len(relations) if relations else 0.0,
            "matched_relations": matched,
            "path_length": len(relations),
        }

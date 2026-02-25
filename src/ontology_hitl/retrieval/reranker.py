"""Cross-encoder reranker — final-stage relevance scoring.

Ported from GraphQAAgent.  Applies a cross-encoder model to (query, context)
pairs to produce a more accurate relevance estimate than vector cosine
similarity alone.
"""

from __future__ import annotations

import structlog

from ontology_hitl.core.models import RetrievedContext

logger = structlog.get_logger(__name__)


class CrossEncoderReranker:
    """Reranks retrieved contexts using a cross-encoder model.

    Loaded lazily on first call to avoid import overhead when not used.
    """

    def __init__(
        self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ) -> None:
        self._model_name = model_name
        self._model = None

    def _load_model(self):  # noqa: ANN202
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
            logger.info("reranker.loaded", model=self._model_name)
        return self._model

    def rerank(
        self,
        query: str,
        contexts: list[RetrievedContext],
        top_k: int = 5,
    ) -> list[RetrievedContext]:
        """Score each (query, context.text) pair and return the top-k."""
        if not contexts:
            return []

        model = self._load_model()
        pairs = [(query, ctx.text) for ctx in contexts]
        scores = model.predict(pairs)

        for ctx, score in zip(contexts, scores):
            ctx.score = float(score)

        ranked = sorted(contexts, key=lambda c: c.score, reverse=True)
        logger.info(
            "reranker.done",
            input_count=len(contexts),
            output_count=min(top_k, len(ranked)),
        )
        return ranked[:top_k]

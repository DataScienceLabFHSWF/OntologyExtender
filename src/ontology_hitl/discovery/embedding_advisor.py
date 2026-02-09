"""C — Embedding Advisor: structural embedding signals for hierarchy placement.

Inspired by the Box Embeddings paper (Memariani et al., 2025) and the
DFG "Structured-entities Ontology Extension" project (Mossakowski, 2023+).

Uses Ollama embeddings to provide a **second opinion** on where new
classes should sit in the taxonomy.  This augments the LLM-based
OntologyEngineer with a structural signal:

1. Encode every seed class (label + definition) as an embedding vector.
2. For each proposed new class, find the top-k most similar seed classes.
3. Recommend the best parent and flag potential siblings.
4. Compute a **structural confidence** score — high when there's a clear
   single best parent, low when multiple candidates are close.

This is a lightweight precursor to the full box-embedding approach.
The advisor does *not* replace the OntologyEngineer — it acts as an
additional evidence source that the ``EnsembleStrategy`` (module E)
aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import structlog

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)


@dataclass
class ParentRecommendation:
    """A recommendation for parent placement of a new class."""

    proposed_label: str
    recommended_parent_uri: str
    recommended_parent_label: str
    similarity: float                    # cosine similarity
    runner_up_parent_uri: str = ""
    runner_up_parent_label: str = ""
    runner_up_similarity: float = 0.0
    structural_confidence: float = 0.0   # gap between 1st and 2nd
    potential_siblings: list[str] = field(default_factory=list)


@dataclass
class EmbeddingAdvisorReport:
    """Output of the embedding advisor for all proposed classes."""

    recommendations: list[ParentRecommendation] = field(default_factory=list)
    avg_confidence: float = 0.0
    model_used: str = ""


class EmbeddingAdvisor:
    """Use Ollama embeddings to recommend parent classes.

    Encodes the seed ontology classes as vectors, then for each proposed
    class finds the nearest neighbour as a parent recommendation.

    Parameters
    ----------
    settings:
        Application configuration (Ollama URL and model).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._seed_embeddings: dict[str, list[float]] = {}
        self._seed_info: dict[str, dict] = {}   # uri → {label, definition}
        self._cache: dict[str, list[float]] = {}

    # ── Seed indexing ───────────────────────────────────────────────

    def index_seed_classes(
        self,
        classes: list[dict[str, str]],
    ) -> int:
        """Compute and cache embeddings for seed ontology classes.

        Args:
            classes: List of ``{uri, label, definition}`` dicts.

        Returns:
            Number of classes successfully embedded.
        """
        count = 0
        for cls in classes:
            uri = cls["uri"]
            label = cls.get("label", "")
            definition = cls.get("definition", "")
            text = f"{label}: {definition}" if definition else label

            emb = self._get_embedding(text)
            if emb:
                self._seed_embeddings[uri] = emb
                self._seed_info[uri] = {"label": label, "definition": definition}
                count += 1

        logger.info("seed_classes_indexed", count=count, total=len(classes))
        return count

    # ── Recommendation ──────────────────────────────────────────────

    def recommend_parents(
        self,
        proposed_classes: list[dict[str, str]],
        top_k: int = 3,
    ) -> EmbeddingAdvisorReport:
        """Find the best parent for each proposed class via embedding similarity.

        Args:
            proposed_classes: List of ``{label, definition}`` dicts.
            top_k: Number of candidates to consider per class.

        Returns:
            ``EmbeddingAdvisorReport`` with recommendations.
        """
        if not self._seed_embeddings:
            logger.warning("no_seed_embeddings", msg="Call index_seed_classes first")
            return EmbeddingAdvisorReport(model_used=self.settings.ollama_model)

        recommendations: list[ParentRecommendation] = []

        for cls in proposed_classes:
            label = cls.get("label", "")
            definition = cls.get("definition", "")
            text = f"{label}: {definition}" if definition else label

            emb = self._get_embedding(text)
            if not emb:
                continue

            # Rank seed classes by cosine similarity
            scored = []
            for uri, seed_emb in self._seed_embeddings.items():
                sim = self._cosine_similarity(emb, seed_emb)
                scored.append((uri, sim))

            scored.sort(key=lambda x: x[1], reverse=True)
            top = scored[:top_k]

            if not top:
                continue

            best_uri, best_sim = top[0]
            best_info = self._seed_info.get(best_uri, {})

            runner_uri, runner_sim = ("", 0.0)
            runner_info: dict[str, str] = {}
            if len(top) > 1:
                runner_uri, runner_sim = top[1]
                runner_info = self._seed_info.get(runner_uri, {})

            # Confidence = gap between 1st and 2nd (0-1 normalised)
            confidence = best_sim - runner_sim if runner_uri else best_sim

            # Siblings = other proposed classes also close to same parent
            siblings = [
                c.get("label", "")
                for c in proposed_classes
                if c.get("label", "") != label
                and self._would_share_parent(c, best_uri)
            ]

            recommendations.append(ParentRecommendation(
                proposed_label=label,
                recommended_parent_uri=best_uri,
                recommended_parent_label=best_info.get("label", ""),
                similarity=best_sim,
                runner_up_parent_uri=runner_uri,
                runner_up_parent_label=runner_info.get("label", ""),
                runner_up_similarity=runner_sim,
                structural_confidence=min(confidence, 1.0),
                potential_siblings=siblings[:5],
            ))

        avg_conf = (
            sum(r.structural_confidence for r in recommendations) / len(recommendations)
            if recommendations else 0.0
        )

        report = EmbeddingAdvisorReport(
            recommendations=recommendations,
            avg_confidence=avg_conf,
            model_used=self.settings.ollama_model,
        )

        logger.info(
            "embedding_advisor_complete",
            classes=len(proposed_classes),
            recommendations=len(recommendations),
            avg_confidence=f"{avg_conf:.2f}",
        )
        return report

    # ── Embedding helpers ───────────────────────────────────────────

    def _get_embedding(self, text: str) -> list[float] | None:
        """Get embedding from Ollama (cached)."""
        if text in self._cache:
            return self._cache[text]

        try:
            resp = httpx.post(
                f"{self.settings.ollama_url}/api/embed",
                json={
                    "model": self.settings.ollama_model,
                    "input": text,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            embeddings = resp.json().get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                vec = embeddings[0]
                self._cache[text] = vec
                return vec
            return None
        except Exception as e:
            logger.warning("embedding_call_failed", text=text[:50], error=str(e))
            return None

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _would_share_parent(self, cls: dict[str, str], parent_uri: str) -> bool:
        """Quick check if *cls* would also map to *parent_uri*."""
        label = cls.get("label", "")
        definition = cls.get("definition", "")
        text = f"{label}: {definition}" if definition else label
        emb = self._get_embedding(text)
        if not emb:
            return False
        parent_emb = self._seed_embeddings.get(parent_uri)
        if not parent_emb:
            return False
        return self._cosine_similarity(emb, parent_emb) > 0.6

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
        self._seed_embeddings.clear()
        self._seed_info.clear()

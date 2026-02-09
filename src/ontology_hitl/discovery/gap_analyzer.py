"""C1.2.1 — OntologyGapAnalyzer: find entities not covered by seed ontology.

Implementation Guide
--------------------
This module compares KGB extraction checkpoint entities against the current
ontology in Fuseki to identify gap candidates — entity types that should
become new ontology classes.

Three methods still need real implementation (marked with TODO):
  1. ``_get_ontology_classes()``  — SPARQL query against Fuseki
  2. ``_classify_entities()``     — Embedding-based semantic matching
  3. ``_build_gap_candidates()``  — Semantic grouping via embeddings

Dependencies:
  - ``httpx`` for Fuseki SPARQL and Ollama /api/embed calls
  - ``numpy`` for cosine similarity (only needed for semantic matching)

Reference: KGB ``FusekiOntologyService.get_all_classes()`` in
``src/kgbuilder/storage/ontology.py`` for the SPARQL pattern.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import httpx
import numpy as np
import structlog

from ontology_hitl.core.models import ExtractedEntitySummary, GapCandidate, GapReport

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPARQL_ALL_CLASSES = """\
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?class ?label
WHERE {
    ?class a owl:Class .
    OPTIONAL { ?class rdfs:label ?label . }
}
ORDER BY ?class
"""


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors.

    Returns:
        Float in [-1, 1].  Returns 0.0 if either vector is zero.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class OntologyGapAnalyzer:
    """Analyze which extracted entities don't fit seed ontology classes.

    Compares KGB extraction checkpoint entities against the current ontology
    to identify gap candidates that should become new classes.

    Parameters
    ----------
    fuseki_url:
        Base URL of the Fuseki server (e.g. ``http://localhost:3030``).
    dataset:
        Fuseki dataset name (e.g. ``kgbuilder``).
    ollama_url:
        Base URL of the Ollama server for embeddings (e.g. ``http://localhost:18135``).
    embedding_model:
        Ollama model name for ``/api/embed`` calls.
    min_frequency:
        Minimum number of entity mentions to qualify as a gap candidate.
    similarity_threshold:
        Cosine similarity above which an entity is considered "covered"
        by an ontology class (0.0–1.0).
    """

    def __init__(
        self,
        fuseki_url: str = "http://localhost:3030",
        dataset: str = "kgbuilder",
        ollama_url: str = "http://localhost:18135",
        embedding_model: str = "qwen3-next",
        min_frequency: int = 3,
        similarity_threshold: float = 0.65,
    ) -> None:
        self.fuseki_url = fuseki_url.rstrip("/")
        self.dataset = dataset
        self.ollama_url = ollama_url.rstrip("/")
        self.embedding_model = embedding_model
        self.min_frequency = min_frequency
        self.similarity_threshold = similarity_threshold

        # Caches populated lazily
        self._class_embeddings: dict[str, np.ndarray] = {}

    # ── Public API ──────────────────────────────────────────────────

    def analyze(self, checkpoint_path: Path) -> GapReport:
        """Run gap analysis on KGB extraction checkpoint.

        Args:
            checkpoint_path: Path to extraction_checkpoint.json from KGB.

        Returns:
            GapReport with coverage stats and gap candidates.
        """
        logger.info("gap_analysis_start", checkpoint=str(checkpoint_path))

        entities = self._load_checkpoint(checkpoint_path)
        ontology_classes = self._get_ontology_classes()
        covered, uncovered = self._classify_entities(entities, ontology_classes)
        gap_candidates = self._build_gap_candidates(uncovered, ontology_classes)

        total = len(entities)
        covered_count = len(covered)
        uncovered_count = len(uncovered)
        coverage_pct = covered_count / total if total > 0 else 0.0

        report = GapReport(
            ontology_version="seed-v1.0",
            total_extracted_entities=total,
            covered_entities=covered_count,
            uncovered_entities=uncovered_count,
            coverage_pct=coverage_pct,
            gap_candidates=gap_candidates,
        )

        logger.info(
            "gap_analysis_complete",
            total=total,
            covered=covered_count,
            gaps=len(gap_candidates),
            coverage_pct=f"{coverage_pct:.1%}",
        )
        return report

    # ── Checkpoint loading (complete) ───────────────────────────────

    def _load_checkpoint(self, path: Path) -> list[ExtractedEntitySummary]:
        """Load entities from KGB extraction checkpoint JSON.

        Expected JSON structure::

            {
                "entities": [
                    {
                        "label": "Stilllegung KKE",
                        "entity_type": "Action",
                        "confidence": 0.85,
                        "evidence": [
                            {"document": "doc1.pdf", "text_snippet": "..."}
                        ]
                    }
                ]
            }
        """
        with open(path) as f:
            data = json.load(f)

        entities: list[ExtractedEntitySummary] = []
        for ent in data.get("entities", []):
            entities.append(
                ExtractedEntitySummary(
                    label=ent["label"],
                    entity_type=ent.get("entity_type", "Unknown"),
                    confidence=ent.get("confidence", 0.0),
                    frequency=len(ent.get("evidence", [])),
                    source_documents=[
                        ev.get("document", "") for ev in ent.get("evidence", [])
                    ],
                    evidence_snippets=[
                        ev.get("text_snippet", "") for ev in ent.get("evidence", [])
                    ],
                )
            )
        return entities

    # ── Fuseki SPARQL (TODO) ────────────────────────────────────────

    def _get_ontology_classes(self) -> list[str]:
        """Get all class labels from the current ontology via SPARQL.

        TODO: Implement this method.

        Steps:
            1. Build the SPARQL endpoint URL:
               ``f"{self.fuseki_url}/{self.dataset}/sparql"``
            2. POST the ``_SPARQL_ALL_CLASSES`` query using httpx:
               ``httpx.post(url, data={"query": _SPARQL_ALL_CLASSES},
                            headers={"Accept": "application/sparql-results+json"},
                            timeout=30.0)``
            3. Parse the JSON response.  Structure is:
               ``{"results": {"bindings": [{"class": {"value": "..."}, "label": {"value": "..."}}]}}``
            4. For each binding:
               - Use ``label["value"]`` if present
               - Otherwise extract local name from URI: ``uri.split("#")[-1].split("/")[-1]``
            5. Return the deduplicated list of label strings.
            6. On error (httpx.HTTPError), log a warning and return ``[]``.

        Reference: KGB ``FusekiOntologyService.get_all_classes()`` in
        ``src/kgbuilder/storage/ontology.py`` lines 53-100.

        Returns:
            List of class label strings from the ontology.
        """
        # Placeholder — will query Fuseki in implementation
        logger.warning("using_placeholder_ontology_classes")
        return []

    # ── Embedding helper (TODO) ─────────────────────────────────────

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector for a text string via Ollama /api/embed.

        TODO: Implement this method.

        Steps:
            1. POST to ``f"{self.ollama_url}/api/embed"`` with JSON body:
               ``{"model": self.embedding_model, "input": text}``
            2. Parse response JSON: ``{"embeddings": [[0.1, 0.2, ...]]}``
            3. Return ``np.array(response["embeddings"][0], dtype=np.float32)``
            4. On error, log warning and return zero vector ``np.zeros(1)``

        Reference: OntologyExtender ``EmbeddingAdvisor._get_embedding()``
        in ``discovery/embedding_advisor.py``.

        Args:
            text: Input text to embed.

        Returns:
            1-D numpy array of floats (embedding vector).
        """
        return np.zeros(1)

    def _get_class_embeddings(self, classes: list[str]) -> dict[str, np.ndarray]:
        """Embed all ontology class labels, using cache.

        TODO: Implement this method.

        Steps:
            1. For each class label not in ``self._class_embeddings``:
               - Call ``self._get_embedding(label)``
               - Store in ``self._class_embeddings[label] = vec``
            2. Return the full cache dict.

        Args:
            classes: List of class label strings.

        Returns:
            Dict mapping class label → embedding vector.
        """
        return self._class_embeddings

    # ── Entity classification (TODO: add semantic matching) ─────────

    def _classify_entities(
        self,
        entities: list[ExtractedEntitySummary],
        ontology_classes: list[str],
    ) -> tuple[list[ExtractedEntitySummary], list[ExtractedEntitySummary]]:
        """Split entities into covered (match ontology) and uncovered.

        TODO: Enhance with embedding-based semantic matching.

        Current behaviour: exact string match on entity_type vs class labels.

        Target behaviour:
            1. Build ``ontology_set = {c.lower() for c in ontology_classes}``
            2. For each entity:
               a. If ``entity.entity_type.lower() in ontology_set`` → covered (exact match).
               b. Otherwise, compute ``entity_embed = self._get_embedding(entity.entity_type)``
               c. Get class embeddings via ``self._get_class_embeddings(ontology_classes)``
               d. Find ``best_class, best_sim = max over classes of cosine_similarity``
               e. If ``best_sim >= self.similarity_threshold`` → covered.
                  Set ``entity.entity_type`` note or log the match.
               f. Otherwise → uncovered.  Set ``closest_seed_class = best_class``,
                  ``semantic_distance = 1.0 - best_sim`` on the GapCandidate later.
            3. Return ``(covered, uncovered)`` tuple.

        Args:
            entities: All extracted entities from checkpoint.
            ontology_classes: Class labels from Fuseki.

        Returns:
            Tuple of (covered_entities, uncovered_entities).
        """
        covered: list[ExtractedEntitySummary] = []
        uncovered: list[ExtractedEntitySummary] = []

        ontology_set = {c.lower() for c in ontology_classes}

        for entity in entities:
            if entity.entity_type.lower() in ontology_set:
                covered.append(entity)
            else:
                uncovered.append(entity)

        return covered, uncovered

    # ── Gap candidate grouping (TODO: add semantic grouping) ────────

    def _build_gap_candidates(
        self,
        uncovered: list[ExtractedEntitySummary],
        ontology_classes: list[str] | None = None,
    ) -> list[GapCandidate]:
        """Group uncovered entities into gap candidates by entity type.

        TODO: Add semantic similarity grouping and closest_seed_class.

        Current behaviour: groups by exact ``entity_type`` string.

        Target behaviour:
            1. Group by ``entity_type`` into ``type_groups`` (current logic).
            2. For each group, find ``closest_seed_class``:
               a. Embed the ``entity_type`` label.
               b. Compare against all ontology class embeddings.
               c. Record the closest class and its ``semantic_distance = 1 - similarity``.
            3. (Optional) Merge groups whose entity_type embeddings are
               very similar (cosine > 0.85): agglomerative merge.
               This handles cases like "Reactor" and "Nuclear Reactor"
               being separate entity_type strings but semantically identical.
            4. Filter: only keep groups with ``freq >= self.min_frequency``.
            5. Sort by frequency descending.

        Args:
            uncovered: Entities not matched to any ontology class.
            ontology_classes: Class labels for nearest-seed computation.

        Returns:
            Sorted list of GapCandidate objects.
        """
        type_groups: dict[str, list[ExtractedEntitySummary]] = defaultdict(list)
        for entity in uncovered:
            type_groups[entity.entity_type].append(entity)

        candidates: list[GapCandidate] = []
        for entity_type, group in type_groups.items():
            freq = len(group)
            if freq < self.min_frequency:
                continue

            candidates.append(
                GapCandidate(
                    entity_type=entity_type,
                    representative_label=group[0].label,
                    examples=[e.label for e in group[:5]],
                    frequency=freq,
                    avg_confidence=sum(e.confidence for e in group) / freq,
                    # TODO: Set closest_seed_class and semantic_distance
                    # by embedding comparison against ontology_classes.
                )
            )

        candidates.sort(key=lambda c: c.frequency, reverse=True)
        return candidates

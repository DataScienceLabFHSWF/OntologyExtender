"""C1.5.2 — CompletenessAnalyzer: entity schema coverage measurement.

Implementation Guide
--------------------
This module measures what percentage of entities extracted by
KnowledgeGraphBuilder are covered by the current ontology schema.

Two matching strategies are used (in order):
  A. **Exact/fuzzy label match** — compare entity ``entity_type`` against
     ontology class labels (case-insensitive, with simple normalization).
  B. **Embedding-based match** — if no exact match, compute cosine similarity
     between entity label embedding and class label embeddings.  Accept
     if similarity ≥ threshold (default 0.80).

Three methods need implementation (marked with TODO):
  1. ``measure_schema_coverage()``  — Main entry, loads checkpoint + queries graph
  2. ``_get_ontology_classes()``    — SPARQL query for owl:Class labels
  3. ``_match_entity_to_class()``   — Exact + embedding match logic

Dependencies:
  - ``httpx``    for Fuseki SPARQL + Ollama embedding calls
  - ``numpy``   for cosine similarity
  - ``json``    for loading checkpoint files

Reference: ``GapAnalyzer`` in ``discovery/gap_analyzer.py`` uses the same
SPARQL and embedding patterns — reuse or import from there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SPARQL templates (same as GapAnalyzer — consider extracting to shared module)
# ---------------------------------------------------------------------------

_SPARQL_ALL_CLASSES = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?class ?label WHERE {
    ?class a owl:Class .
    OPTIONAL { ?class rdfs:label ?label }
}
"""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


class CompletenessAnalyzer:
    """Measure what percentage of extracted entities are covered by the ontology.

    Compares extracted entity types against ontology classes to determine
    how well the schema represents the document domain.
    """

    def __init__(
        self,
        fuseki_url: str = "http://localhost:3031",
        dataset: str = "kgbuilder",
        ollama_url: str = "http://localhost:18135",
        model: str = "qwen3-next",
        similarity_threshold: float = 0.80,
    ) -> None:
        self.fuseki_url = fuseki_url.rstrip("/")
        self.dataset = dataset
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.similarity_threshold = similarity_threshold
        self._embedding_cache: dict[str, list[float]] = {}

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_ontology_classes(self) -> list[str]:
        """Fetch all owl:Class labels from Fuseki.

        TODO: Implement (same pattern as GapAnalyzer._get_ontology_classes).

        Steps:
            1. ``url = f"{self.fuseki_url}/{self.dataset}/sparql"``
            2. POST with ``Content-Type: application/sparql-query``,
               ``Accept: application/sparql-results+json``
            3. Parse bindings, extract ``label`` values.
            4. Return list of class label strings.
            5. On error, log warning and return ``[]``.
        """
        url = f"{self.fuseki_url}/{self.dataset}/sparql"
        try:
            resp = httpx.post(url, data={"query": _SPARQL_ALL_CLASSES},
                             headers={"Accept": "application/sparql-results+json"})
            resp.raise_for_status()
            data = resp.json()
            labels = []
            for binding in data.get("results", {}).get("bindings", []):
                if "label" in binding and binding["label"]["value"]:
                    labels.append(binding["label"]["value"])
                elif "class" in binding:
                    uri = binding["class"]["value"]
                    local_name = uri.split("#")[-1].split("/")[-1]
                    if local_name:
                        labels.append(local_name)
            return list(set(labels))
        except Exception as e:
            logger.warning("failed_to_query_ontology_classes", error=str(e))
            return []

    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding vector for text via Ollama /api/embed.

        TODO: Implement (same pattern as GapAnalyzer._get_embedding).

        Steps:
            1. Check ``self._embedding_cache`` first.
            2. ``url = f"{self.ollama_url}/api/embed"``
            3. POST JSON: ``{"model": self.model, "input": text}``
            4. Extract: ``resp.json()["embeddings"][0]``
            5. Store in ``self._embedding_cache[text]``
            6. Return embedding vector.
            7. On error, return ``[]``.
        """
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        url = f"{self.ollama_url}/api/embed"
        try:
            resp = httpx.post(url, json={"model": self.model, "input": text}, timeout=30.0)
            resp.raise_for_status()
            embedding = resp.json()["embeddings"][0]
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            logger.warning("failed_to_get_embedding", text=text, error=str(e))
            return []

    def _match_entity_to_class(
        self,
        entity_type: str,
        class_labels: list[str],
        class_embeddings: dict[str, list[float]] | None = None,
    ) -> tuple[bool, str | None, float]:
        """Match an entity type to an ontology class.

        TODO: Implement two-stage matching.

        Steps:
            1. **Exact match** (case-insensitive):
               ``normalized = entity_type.lower().strip().replace("_", " ")``
               For each label in class_labels:
                 If ``label.lower().strip() == normalized``:
                   Return ``(True, label, 1.0)``
            2. **Substring/fuzzy match**:
               For each label in class_labels:
                 If ``normalized in label.lower()`` or ``label.lower() in normalized``:
                   Return ``(True, label, 0.9)``
            3. **Embedding match** (if class_embeddings provided):
               ``entity_emb = self._get_embedding(entity_type)``
               If ``entity_emb`` is empty, return ``(False, None, 0.0)``
               For each label, emb in class_embeddings.items():
                 ``sim = _cosine_similarity(entity_emb, emb)``
               Find ``best_label, best_sim = max(...)``
               If ``best_sim >= self.similarity_threshold``:
                 Return ``(True, best_label, best_sim)``
            4. Return ``(False, None, 0.0)``

        Args:
            entity_type: The entity type string from KGB extraction.
            class_labels: All ontology class labels.
            class_embeddings: Optional precomputed {label: embedding} dict.

        Returns:
            Tuple of (matched: bool, matched_class: str|None, similarity: float).
        """
        normalized = entity_type.lower().strip().replace("_", " ")
        for label in class_labels:
            if label.lower().strip() == normalized:
                return (True, label, 1.0)
        for label in class_labels:
            if normalized in label.lower() or label.lower() in normalized:
                return (True, label, 0.9)
        if class_embeddings:
            entity_emb = self._get_embedding(entity_type)
            if not entity_emb:
                return (False, None, 0.0)
            best_label = None
            best_sim = -1.0
            for label, emb in class_embeddings.items():
                sim = _cosine_similarity(entity_emb, emb)
                if sim > best_sim:
                    best_sim = sim
                    best_label = label
            if best_sim >= self.similarity_threshold:
                return (True, best_label, best_sim)
        return (False, None, 0.0)

    # ── Public API ───────────────────────────────────────────────────

    def measure_schema_coverage(
        self,
        checkpoint_path: str,
    ) -> dict:
        """Measure entity-to-schema coverage.

        TODO: Implement full coverage measurement.

        Steps:
            1. Load checkpoint:
               ``data = json.loads(Path(checkpoint_path).read_text())``
               Expected format (KGB checkpoint):
               ``{"entities": [{"label": "...", "entity_type": "...", ...}, ...]}``
               Extract unique entity types:
               ``entity_types = list({e["entity_type"] for e in data.get("entities", [])})``
            2. Get ontology classes:
               ``class_labels = self._get_ontology_classes()``
            3. Optionally precompute class embeddings:
               ``class_embeddings = {lbl: self._get_embedding(lbl) for lbl in class_labels}``
               (Skip this step if you want faster execution without embedding fallback.)
            4. Match each entity type:
               ```python
               results = []
               for et in entity_types:
                   matched, cls, sim = self._match_entity_to_class(et, class_labels, class_embeddings)
                   results.append({"entity_type": et, "matched": matched,
                                   "matched_class": cls, "similarity": sim})
               ```
            5. Compute aggregates:
               ``covered = sum(1 for r in results if r["matched"])``
               ``total = len(entity_types)``
               ``coverage_pct = covered / total * 100 if total > 0 else 0.0``
               ``gap_types = [r["entity_type"] for r in results if not r["matched"]]``
            6. Return:
               ``{"covered_entities": covered, "total_entities": total,
                 "coverage_pct": coverage_pct, "gap_entities": len(gap_types),
                 "gap_entity_types": gap_types, "details": results}``

        Args:
            checkpoint_path: Path to KGB extraction checkpoint.

        Returns:
            Dict with coverage stats.
        """
        logger.info("measuring_coverage", checkpoint=checkpoint_path)

        data = json.loads(Path(checkpoint_path).read_text())
        entity_types = list({e["entity_type"] for e in data.get("entities", [])})
        class_labels = self._get_ontology_classes()
        class_embeddings = {lbl: self._get_embedding(lbl) for lbl in class_labels}
        results = []
        for et in entity_types:
            matched, cls, sim = self._match_entity_to_class(et, class_labels, class_embeddings)
            results.append({"entity_type": et, "matched": matched, "matched_class": cls, "similarity": sim})
        covered = sum(1 for r in results if r["matched"])
        total = len(entity_types)
        coverage_pct = covered / total * 100 if total > 0 else 0.0
        gap_types = [r["entity_type"] for r in results if not r["matched"]]
        return {
            "covered_entities": covered,
            "total_entities": total,
            "coverage_pct": coverage_pct,
            "gap_entities": len(gap_types),
            "gap_entity_types": gap_types,
            "details": results,
        }

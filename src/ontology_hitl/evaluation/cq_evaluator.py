"""C1.5.1 — CQEvaluator: measure competency question answerability.

Implementation Guide
--------------------
This module evaluates whether competency questions (CQs) can be answered
by the current ontology/graph.  Two strategies are used:

  A. **Structural matching** — check that the classes and properties
     referenced in a CQ exist in the graph (fast, no LLM).
  B. **LLM-to-SPARQL** — ask the LLM to translate a CQ into SPARQL,
     then execute the SPARQL and check if results are non-empty.

Three methods need implementation (marked with TODO):
  1. ``evaluate_coverage()``    — Main entry, iterates over CQ list
  2. ``_structural_check()``    — Check class/property existence via SPARQL
  3. ``_llm_to_sparql()``       — Translate CQ to SPARQL via Ollama, then execute

Dependencies:
  - ``httpx``  for Fuseki SPARQL + Ollama HTTP calls
  - ``json``   for loading CQ files and parsing LLM output
  - ``re``     for extracting JSON/SPARQL from LLM response

Reference: KGB ``CQGenerator`` in ``src/kgbuilder/cq/generator.py`` for CQ
structure and ``FusekiOntologyService`` for SPARQL patterns.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SPARQL templates
# ---------------------------------------------------------------------------

# Check if a given class URI exists as owl:Class
_SPARQL_CLASS_EXISTS = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
ASK {{ <{class_uri}> a owl:Class }}
"""

# Get all class labels (for structural matching)
_SPARQL_ALL_CLASS_LABELS = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label WHERE {{
    ?c a owl:Class .
    ?c rdfs:label ?label .
}}
"""

# ---------------------------------------------------------------------------
# LLM prompt for CQ → SPARQL translation
# ---------------------------------------------------------------------------

_CQ_TO_SPARQL_PROMPT = """\
You are an ontology evaluation assistant.  Given a competency question
and a list of ontology classes, generate a SPARQL ASK query that would
return true if the ontology can answer the question.

Ontology classes: {class_labels}

Competency question: {cq_text}

Respond ONLY with a valid SPARQL ASK query.  No explanation.
"""


class CQEvaluator:
    """Evaluate competency question answerability against a knowledge graph.

    Runs SPARQL queries derived from competency questions and measures
    what percentage can be answered from the current graph.
    """

    def __init__(
        self,
        fuseki_url: str = "http://localhost:3031",
        dataset: str = "kgbuilder",
        ollama_url: str = "http://localhost:18135",
        model: str = "qwen3-next",
    ) -> None:
        self.fuseki_url = fuseki_url.rstrip("/")
        self.dataset = dataset
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    # ── Helpers ──────────────────────────────────────────────────────

    def _sparql_query(self, query: str) -> list[dict[str, Any]]:
        """Execute SPARQL SELECT and return bindings.

        TODO: Implement (same pattern as VersionManager._sparql_query).

        Steps:
            1. ``url = f"{self.fuseki_url}/{self.dataset}/sparql"``
            2. POST with ``Content-Type: application/sparql-query``,
               ``Accept: application/sparql-results+json``
            3. Parse ``resp.json()["results"]["bindings"]``
            4. Return list of dicts mapping var names → values
        """
        raise NotImplementedError("_sparql_query")

    def _sparql_ask(self, query: str) -> bool:
        """Execute SPARQL ASK and return boolean.

        TODO: Implement.

        Steps:
            1. ``url = f"{self.fuseki_url}/{self.dataset}/sparql"``
            2. POST with ``Content-Type: application/sparql-query``,
               ``Accept: application/sparql-results+json``
            3. Return ``resp.json()["boolean"]``
            4. On error, log warning and return ``False``
        """
        raise NotImplementedError("_sparql_ask")

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama /api/generate and return the response text.

        TODO: Implement (same pattern as ClassGenerator._call_llm).

        Steps:
            1. ``url = f"{self.ollama_url}/api/generate"``
            2. POST JSON: ``{"model": self.model, "prompt": prompt, "stream": False}``
            3. Strip ``<think>...</think>`` blocks: ``re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)``
            4. Return stripped text
        """
        raise NotImplementedError("_call_llm")

    # ── Public API ───────────────────────────────────────────────────

    def evaluate_coverage(
        self,
        cq_path: str,
    ) -> dict:
        """Evaluate CQ answerability against the current graph.

        TODO: Implement full evaluation loop.

        Steps:
            1. Load CQ file: ``cqs = json.loads(Path(cq_path).read_text())``
               Expected format: list of dicts with at minimum a ``"question"`` key.
               May also have ``"id"``, ``"expected_classes"`` keys.
            2. Get all class labels from graph:
               ``labels_result = self._sparql_query(_SPARQL_ALL_CLASS_LABELS)``
               ``class_labels = [r["label"] for r in labels_result]``
            3. For each CQ:
               a. Try structural check first via ``_structural_check(cq, class_labels)``
               b. If structural check is inconclusive (returns None), try LLM:
                  ``sparql = self._llm_to_sparql(cq["question"], class_labels)``
                  ``answerable = self._sparql_ask(sparql) if sparql else False``
               c. Record result: ``{"cq": cq["question"], "answerable": bool, "method": "structural"|"llm"}``
            4. Compute aggregate:
               ``answerable_count = sum(1 for r in results if r["answerable"])``
               ``coverage_pct = answerable_count / len(cqs) * 100 if cqs else 0.0``
            5. Return dict:
               ``{"total_cqs": len(cqs), "answerable": answerable_count,
                 "coverage_pct": coverage_pct, "results": results}``

        Args:
            cq_path: Path to competency questions JSON.

        Returns:
            Dict with per-CQ results and aggregate coverage.
        """
        logger.info("evaluating_cq_coverage", cq_path=cq_path)

        # Placeholder
        return {
            "total_cqs": 0,
            "answerable": 0,
            "coverage_pct": 0.0,
            "results": [],
        }

    def _structural_check(
        self,
        cq: dict[str, Any],
        class_labels: list[str],
    ) -> bool | None:
        """Check if a CQ's expected classes exist in the ontology.

        TODO: Implement structural matching.

        Steps:
            1. If ``"expected_classes"`` key not in ``cq``, return ``None`` (inconclusive).
            2. For each expected class label in ``cq["expected_classes"]``:
               a. Check if label (case-insensitive) is in ``class_labels``.
            3. If ALL expected classes found, return ``True``.
            4. If ANY expected class missing, return ``False``.

        Args:
            cq: Single CQ dict with ``"question"`` and optionally ``"expected_classes"``.
            class_labels: All class labels currently in the ontology graph.

        Returns:
            True if all expected classes found, False if any missing,
            None if no expected_classes defined (inconclusive).
        """
        return None

    def _llm_to_sparql(
        self,
        cq_text: str,
        class_labels: list[str],
    ) -> str | None:
        """Translate a competency question to a SPARQL ASK query via LLM.

        TODO: Implement LLM-based CQ→SPARQL translation.

        Steps:
            1. Format prompt: ``_CQ_TO_SPARQL_PROMPT.format(
                   class_labels=", ".join(class_labels), cq_text=cq_text)``
            2. Call LLM: ``response = self._call_llm(prompt)``
            3. Extract SPARQL from response:
               Try ``re.search(r"(ASK\\s*\\{.*?\\})", response, re.DOTALL)``
               If no match, check if entire response looks like SPARQL (starts with ASK or PREFIX).
            4. Return extracted SPARQL string, or ``None`` if extraction fails.

        Args:
            cq_text: Natural language competency question.
            class_labels: All class labels in the ontology.

        Returns:
            SPARQL ASK query string, or None if translation fails.
        """
        return None

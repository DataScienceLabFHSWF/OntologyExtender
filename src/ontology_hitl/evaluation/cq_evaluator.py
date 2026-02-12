"""C1.5.1 — CQEvaluator: measure competency question answerability.

Implementation Guide
--------------------
This module evaluates whether competency questions (CQs) can be answered
by the current ontology/graph.  Two strategies are used:

  A. **Structural matching** — check that the classes and properties
     referenced in a CQ exist in the graph (fast, no LLM).
  B. **LLM-to-SPARQL** — ask the LLM to translate a CQ into SPARQL,
     then execute the SPARQL and check if results are non-empty.

All methods are implemented with:
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
        """Execute SPARQL SELECT and return bindings."""
        url = f"{self.fuseki_url}/{self.dataset}/sparql"
        try:
            resp = httpx.post(url, content=query,
                             headers={"Content-Type": "application/sparql-query",
                                      "Accept": "application/sparql-results+json"})
            resp.raise_for_status()
            bindings = resp.json()["results"]["bindings"]
            return [
                {var: b[var]["value"] for var in b}
                for b in bindings
            ]
        except Exception as e:
            logger.warning("sparql_query_failed", error=str(e))
            return []

    def _sparql_ask(self, query: str) -> bool:
        """Execute SPARQL ASK and return boolean."""
        url = f"{self.fuseki_url}/{self.dataset}/sparql"
        try:
            resp = httpx.post(url, content=query,
                             headers={"Content-Type": "application/sparql-query",
                                      "Accept": "application/sparql-results+json"})
            resp.raise_for_status()
            return resp.json().get("boolean", False)
        except Exception as e:
            logger.warning("sparql_ask_failed", error=str(e))
            return False

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama /api/generate and return the response text."""
        url = f"{self.ollama_url}/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        try:
            resp = httpx.post(url, json=payload, timeout=120.0)
            resp.raise_for_status()
            text = resp.json()["response"].strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            return text
        except Exception as e:
            logger.warning("llm_call_failed", error=str(e))
            return ""

    # ── Public API ───────────────────────────────────────────────────

    def evaluate_coverage(
        self,
        cq_path: str,
    ) -> dict:
        """Evaluate CQ answerability against the current graph."""
        logger.info("evaluating_cq_coverage", cq_path=cq_path)

        cqs = json.loads(Path(cq_path).read_text())
        labels_result = self._sparql_query(_SPARQL_ALL_CLASS_LABELS)
        class_labels = [r["label"] for r in labels_result]
        results = []
        for cq in cqs:
            res = {"cq": cq["question"]}
            struct = self._structural_check(cq, class_labels)
            if struct is not None:
                res["answerable"] = struct
                res["method"] = "structural"
            else:
                sparql = self._llm_to_sparql(cq["question"], class_labels)
                answerable = self._sparql_ask(sparql) if sparql else False
                res["answerable"] = answerable
                res["method"] = "llm"
            results.append(res)
        answerable_count = sum(1 for r in results if r["answerable"])
        coverage_pct = answerable_count / len(cqs) * 100 if cqs else 0.0
        return {
            "total_cqs": len(cqs),
            "answerable": answerable_count,
            "coverage_pct": coverage_pct,
            "results": results,
        }

    def _structural_check(
        self,
        cq: dict[str, Any],
        class_labels: list[str],
    ) -> bool | None:
        """Check if a CQ's expected classes exist in the ontology."""
        if "expected_classes" not in cq:
            return None
        expected = cq["expected_classes"]
        if not expected:
            return None
        class_labels_lower = [label.lower() for label in class_labels]
        for cls in expected:
            if cls.lower() not in class_labels_lower:
                return False
        return True

    def _llm_to_sparql(
        self,
        cq_text: str,
        class_labels: list[str],
    ) -> str | None:
        """Translate a competency question to a SPARQL ASK query via LLM."""
        prompt = _CQ_TO_SPARQL_PROMPT.format(
            class_labels=", ".join(class_labels),
            cq_text=cq_text
        )
        response = self._call_llm(prompt)
        if not response:
            return None
        # Try to extract ASK query
        match = re.search(r"(ASK\s*\{.*?\})", response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Check if whole response is SPARQL
        stripped = response.strip()
        if stripped.upper().startswith("ASK") or stripped.upper().startswith("PREFIX"):
            return stripped
        return None

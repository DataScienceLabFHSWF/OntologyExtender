"""C1.2.2 — ClassDefinitionGenerator: LLM-based class definition proposals.

Implementation Guide
--------------------
This module takes gap candidates (entity types not in the ontology) and
generates fully specified ``ProposedClass`` objects with definitions,
parent classes, and suggested properties via LLM calls.

Three methods need real implementation (marked with TODO):
  1. ``_generate_single()``          — Call Ollama to produce a class definition
  2. ``_suggest_default_properties()``— Call Ollama to propose properties
  3. ``_get_parent_candidates()``     — SPARQL query for potential parent classes

Dependencies:
  - ``httpx``  for Ollama ``/api/generate`` and Fuseki SPARQL
  - ``json``   for parsing structured LLM output

Reference: KGB ``LLMEntityExtractor._build_prompt()`` in
``src/kgbuilder/extraction/entity.py`` and ``ExtractionChains`` in
``src/kgbuilder/extraction/chains.py`` for structured LLM output patterns.
"""

from __future__ import annotations

import json
import re

import httpx
import structlog

from ontology_hitl.core.models import GapCandidate, ProposedClass, PropertyDef

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SPARQL query templates
# ---------------------------------------------------------------------------

_SPARQL_CLASS_HIERARCHY = """\
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?class ?label ?parent ?parentLabel
WHERE {
    ?class a owl:Class .
    OPTIONAL { ?class rdfs:label ?label . }
    OPTIONAL {
        ?class rdfs:subClassOf ?parent .
        ?parent a owl:Class .
        OPTIONAL { ?parent rdfs:label ?parentLabel . }
    }
}
ORDER BY ?class
"""

# ---------------------------------------------------------------------------
# LLM prompt templates
# ---------------------------------------------------------------------------

_CLASS_DEFINITION_PROMPT = """\
You are an ontology engineer. Given a gap entity type discovered in documents,
generate a class definition for an OWL ontology extension.

## Entity Type
- Label: {entity_type}
- Example instances: {examples}
- Frequency in corpus: {frequency} mentions
- Extraction confidence: {avg_confidence:.2f}

## Existing Ontology Classes (potential parents)
{parent_candidates}

## Task
Generate a JSON object with these exact keys:
{{
  "label": "<PascalCase class name>",
  "definition": "<1-2 sentence formal definition>",
  "parent_class": "<label of the best parent class from the list above>",
  "properties": [
    {{
      "name": "<snake_case property name>",
      "datatype": "<xsd:string|xsd:integer|xsd:float|xsd:date|xsd:boolean>",
      "description": "<what this property captures>",
      "required": <true|false>
    }}
  ]
}}

Rules:
- parent_class MUST be one of the existing classes listed above.
- Include 2-5 domain-relevant properties (not just label/description).
- Properties should be specific to this entity type.
- Definition should be precise and unambiguous.

Respond with ONLY the JSON object, no markdown fences."""


_PROPERTY_SUGGESTION_PROMPT = """\
You are an ontology engineer. Suggest 3-5 OWL DatatypeProperties for the class "{entity_type}".

Respond with a JSON array:
[
  {{
    "name": "<snake_case>",
    "datatype": "<xsd:string|xsd:integer|xsd:float|xsd:date|xsd:boolean>",
    "description": "<purpose>",
    "required": <true|false>
  }}
]

Only respond with the JSON array, no markdown fences."""


class ClassDefinitionGenerator:
    """Generate structured class definitions via LLM.

    Takes gap candidates and produces fully specified ProposedClass objects
    with definitions, parent classes, and suggested properties.

    Parameters
    ----------
    ollama_url:
        Base URL of the Ollama server (e.g. ``http://localhost:18135``).
    model:
        Ollama model name for ``/api/generate`` calls.
    fuseki_url:
        Base URL of the Fuseki server.
    dataset:
        Fuseki dataset name.
    temperature:
        LLM sampling temperature.  Lower = more deterministic.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:18135",
        model: str = "qwen3-next",
        fuseki_url: str = "http://localhost:3030",
        dataset: str = "kgbuilder",
        temperature: float = 0.5,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.fuseki_url = fuseki_url.rstrip("/")
        self.dataset = dataset
        self.temperature = temperature

    # ── Public API ──────────────────────────────────────────────────

    def generate_from_gaps(
        self,
        gap_candidates: list[dict] | list[GapCandidate],
        max_proposals: int = 30,
    ) -> list[ProposedClass]:
        """Generate class proposals from gap candidates.

        Args:
            gap_candidates: Gap analysis results (dicts or GapCandidate objects).
            max_proposals: Maximum proposals to generate.

        Returns:
            List of ProposedClass with definitions and properties.
        """
        logger.info("generating_proposals", candidates=len(gap_candidates))

        # Pre-fetch parent candidates once
        parent_candidates = self._get_parent_candidates()

        proposals: list[ProposedClass] = []
        for i, candidate in enumerate(gap_candidates[:max_proposals]):
            if isinstance(candidate, dict):
                entity_type = candidate["entity_type"]
                examples = candidate.get("examples", [])
                frequency = candidate.get("frequency", 0)
                avg_confidence = candidate.get("avg_confidence", 0.0)
            else:
                entity_type = candidate.entity_type
                examples = candidate.examples
                frequency = candidate.frequency
                avg_confidence = candidate.avg_confidence

            proposal = self._generate_single(
                proposal_id=f"prop_{i + 1:03d}",
                entity_type=entity_type,
                examples=examples,
                frequency=frequency,
                avg_confidence=avg_confidence,
                parent_candidates=parent_candidates,
            )
            proposals.append(proposal)

        logger.info("proposals_generated", count=len(proposals))
        return proposals

    # ── LLM call (TODO) ────────────────────────────────────────────

    def _generate_single(
        self,
        proposal_id: str,
        entity_type: str,
        examples: list[str],
        frequency: int,
        avg_confidence: float,
        parent_candidates: list[dict[str, str]] | None = None,
    ) -> ProposedClass:
        """Generate a single class proposal via LLM.

        TODO: Implement this method.

        Steps:
            1. Format ``_CLASS_DEFINITION_PROMPT`` with:
               - ``entity_type``, ``examples`` (comma-joined, max 5),
               - ``frequency``, ``avg_confidence``
               - ``parent_candidates``: format as bullet list
                 ``"- {label} ({uri})"`` for each candidate.
                 If ``parent_candidates`` is None or empty, use
                 ``"- Thing (owl:Thing)"`` as the only option.

            2. Call ``self._call_llm(prompt)`` to get the LLM response string.

            3. Parse the JSON response:
               a. Try ``json.loads(response)``
               b. On failure: extract JSON with regex:
                  ``re.search(r'\\{.*\\}', response, re.DOTALL)``
               c. On failure: log warning, return fallback proposal.

            4. Extract fields from parsed JSON dict:
               - ``label = parsed.get("label", entity_type)``
               - ``definition = parsed.get("definition", "")``
               - ``parent_label = parsed.get("parent_class", "Thing")``
               - ``properties_raw = parsed.get("properties", [])``

            5. Resolve ``parent_uri``:
               - Search ``parent_candidates`` for matching label.
               - If found, use its URI.  Otherwise use ``"owl:Thing"``.

            6. Convert ``properties_raw`` to ``list[PropertyDef]``:
               ```python
               props = []
               for p in properties_raw:
                   props.append(PropertyDef(
                       name=p.get("name", "unknown"),
                       datatype=p.get("datatype", "xsd:string"),
                       description=p.get("description", ""),
                       required=p.get("required", False),
                   ))
               ```

            7. Return ``ProposedClass(id=proposal_id, label=label, ...)``

        Args:
            proposal_id: Unique ID like "prop_001".
            entity_type: The entity type string from gap analysis.
            examples: Example entity labels found in documents.
            frequency: How many times this type appeared.
            avg_confidence: Average extraction confidence.
            parent_candidates: Available parent classes from SPARQL.

        Returns:
            A fully populated ProposedClass.
        """
        logger.info("generating_class_definition", entity_type=entity_type)

        # Fallback: return placeholder until LLM call is implemented
        return ProposedClass(
            id=proposal_id,
            label=entity_type,
            definition=f"A {entity_type} in the nuclear decommissioning domain.",
            parent_uri="http://purl.org/2024/planning-ontology#DomainConstant",
            parent_label="DomainConstant",
            examples=examples,
            frequency=frequency,
            confidence=avg_confidence,
            suggested_properties=self._suggest_default_properties(entity_type),
            source_gap_candidates=[entity_type],
        )

    # ── Property generation (TODO) ──────────────────────────────────

    def _suggest_default_properties(self, entity_type: str) -> list[PropertyDef]:
        """Generate properties for a class.

        TODO: Replace with LLM-generated properties.

        Steps:
            1. Format ``_PROPERTY_SUGGESTION_PROMPT`` with ``entity_type``.
            2. Call ``self._call_llm(prompt)``.
            3. Parse JSON array response (same fallback pattern as above).
            4. Convert each item to ``PropertyDef``.
            5. On failure, return the two default properties below.

        Args:
            entity_type: Class label to generate properties for.

        Returns:
            List of PropertyDef objects.
        """
        return [
            PropertyDef(
                name="label",
                datatype="xsd:string",
                description=f"Human-readable label for this {entity_type}.",
                required=True,
                max_count=1,
            ),
            PropertyDef(
                name="description",
                datatype="xsd:string",
                description=f"Description of this {entity_type}.",
                required=False,
            ),
        ]

    # ── Fuseki parent lookup (TODO) ─────────────────────────────────

    def _get_parent_candidates(self) -> list[dict[str, str]]:
        """Get potential parent classes from Fuseki for the LLM to choose from.

        TODO: Implement this method.

        Steps:
            1. Build SPARQL endpoint: ``f"{self.fuseki_url}/{self.dataset}/sparql"``
            2. POST ``_SPARQL_CLASS_HIERARCHY`` query using httpx.
            3. Parse JSON response bindings.
            4. Build list of dicts: ``[{"uri": "...", "label": "...", "parent": "..."}]``
               - Use label if present, otherwise extract from URI.
            5. Return the list.  On error, return
               ``[{"uri": "owl:Thing", "label": "Thing", "parent": ""}]``.

        Returns:
            List of dicts with keys ``uri``, ``label``, ``parent``.
        """
        return [{"uri": "owl:Thing", "label": "Thing", "parent": ""}]

    # ── Shared LLM call (TODO) ──────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama /api/generate and return the response text.

        TODO: Implement this method.

        Steps:
            1. POST to ``f"{self.ollama_url}/api/generate"`` with JSON:
               ``{
                   "model": self.model,
                   "prompt": prompt,
                   "stream": False,
                   "options": {"temperature": self.temperature}
               }``
            2. Set timeout to 300 seconds (large model, complex prompts).
            3. Parse response: ``response.json()["response"]``
            4. Strip leading/trailing whitespace.
            5. If response contains ``<think>...</think>`` tags (qwen3 reasoning),
               extract only the content after the closing ``</think>`` tag.
            6. On ``httpx.HTTPError``: log error, return empty string.
            7. On timeout: log error, return empty string.

        Args:
            prompt: The full prompt string.

        Returns:
            LLM response text, or empty string on error.
        """
        return ""

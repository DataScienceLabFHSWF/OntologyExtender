"""C1.2.2 — ClassDefinitionGenerator: LLM-based class definition proposals.

Implementation Guide
--------------------
This module takes gap candidates (entity types not in the ontology) and
generates fully specified ``ProposedClass`` objects with definitions,
parent classes, and suggested properties via LLM calls.

All methods are implemented with LLM integration for:
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
        model: str = "gemma4:31b",
        fuseki_url: str = "http://localhost:3030",
        dataset: str = "kgbuilder",
        temperature: float = 0.5,
        domain_name: str = "",
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.fuseki_url = fuseki_url.rstrip("/")
        self.dataset = dataset
        self.temperature = temperature
        self._domain_name = domain_name

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

        # Format parent_candidates
        if not parent_candidates:
            parent_candidates = [{"uri": "owl:Thing", "label": "Thing", "parent": ""}]
        parent_list = "\n".join(f"- {c['label']} ({c['uri']})" for c in parent_candidates)

        # Format examples
        examples_str = ", ".join(examples[:5])

        prompt = _CLASS_DEFINITION_PROMPT.format(
            entity_type=entity_type,
            examples=examples_str,
            frequency=frequency,
            avg_confidence=avg_confidence,
            parent_candidates=parent_list
        )

        response = self._call_llm(prompt)
        if not response:
            # Fallback
            return ProposedClass(
                id=proposal_id,
                label=entity_type,
                definition=f"A {entity_type} in the {self._domain_name + ' ' if self._domain_name else ''}domain.",
                parent_uri="http://purl.org/2024/planning-ontology#DomainConstant",
                parent_label="DomainConstant",
                examples=examples,
                frequency=frequency,
                confidence=avg_confidence,
                suggested_properties=self._suggest_default_properties(entity_type),
                source_gap_candidates=[entity_type],
            )

        # Parse JSON
        parsed = None
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if not parsed or not isinstance(parsed, dict):
            logger.warning("failed_to_parse_llm_response", entity_type=entity_type)
            # Fallback
            return ProposedClass(
                id=proposal_id,
                label=entity_type,
                definition=f"A {entity_type} in the {self._domain_name + ' ' if self._domain_name else ''}domain.",
                parent_uri="http://purl.org/2024/planning-ontology#DomainConstant",
                parent_label="DomainConstant",
                examples=examples,
                frequency=frequency,
                confidence=avg_confidence,
                suggested_properties=self._suggest_default_properties(entity_type),
                source_gap_candidates=[entity_type],
            )

        # Extract fields
        label = parsed.get("label", entity_type)
        definition = parsed.get("definition", "")
        parent_label = parsed.get("parent_class", "Thing")
        properties_raw = parsed.get("properties", [])

        # Resolve parent_uri
        parent_uri = "owl:Thing"
        for c in parent_candidates:
            if c["label"] == parent_label:
                parent_uri = c["uri"]
                break

        # Convert properties
        props = []
        for p in properties_raw:
            props.append(PropertyDef(
                name=p.get("name", "unknown"),
                datatype=p.get("datatype", "xsd:string"),
                description=p.get("description", ""),
                required=p.get("required", False),
            ))

        return ProposedClass(
            id=proposal_id,
            label=label,
            definition=definition,
            parent_uri=parent_uri,
            parent_label=parent_label,
            examples=examples,
            frequency=frequency,
            confidence=avg_confidence,
            suggested_properties=props,
            source_gap_candidates=[entity_type],
        )

    def _suggest_default_properties(self, entity_type: str) -> list[PropertyDef]:
        """Generate properties for a class via LLM.

        Args:
            entity_type: Class label to generate properties for.

        Returns:
            List of PropertyDef objects.
        """
        prompt = _PROPERTY_SUGGESTION_PROMPT.format(entity_type=entity_type)
        response = self._call_llm(prompt)
        if not response:
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
        try:
            properties_raw = json.loads(response)
            if not isinstance(properties_raw, list):
                raise ValueError("Not a list")
            props = []
            for p in properties_raw:
                props.append(PropertyDef(
                    name=p.get("name", "unknown"),
                    datatype=p.get("datatype", "xsd:string"),
                    description=p.get("description", ""),
                    required=p.get("required", False),
                ))
            return props
        except (json.JSONDecodeError, ValueError):
            # Fallback to regex
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                try:
                    properties_raw = json.loads(match.group(0))
                    props = []
                    for p in properties_raw:
                        props.append(PropertyDef(
                            name=p.get("name", "unknown"),
                            datatype=p.get("datatype", "xsd:string"),
                            description=p.get("description", ""),
                            required=p.get("required", False),
                        ))
                    return props
                except:
                    pass
            logger.warning("failed_to_parse_properties", entity_type=entity_type)
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

    def _get_parent_candidates(self) -> list[dict[str, str]]:
        """Get potential parent classes from Fuseki for the LLM to choose from.

        Returns:
            List of dicts with keys ``uri``, ``label``, ``parent``.
        """
        endpoint = f"{self.fuseki_url}/{self.dataset}/sparql"
        try:
            response = httpx.post(
                endpoint,
                data={"query": _SPARQL_CLASS_HIERARCHY},
                headers={"Accept": "application/sparql-results+json"}
            )
            response.raise_for_status()
            data = response.json()
            candidates = []
            for binding in data.get("results", {}).get("bindings", []):
                uri = binding["class"]["value"]
                label = binding.get("label", {}).get("value", "")
                if not label:
                    # Extract local name from URI
                    label = uri.split("#")[-1] if "#" in uri else uri.split("/")[-1]
                parent = binding.get("parent", {}).get("value", "")
                candidates.append({"uri": uri, "label": label, "parent": parent})
            return candidates if candidates else [{"uri": "owl:Thing", "label": "Thing", "parent": ""}]
        except Exception as e:
            logger.error("sparql_query_failed", error=str(e))
            return [{"uri": "owl:Thing", "label": "Thing", "parent": ""}]

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama /api/generate and return the response text.

        Args:
            prompt: The full prompt string.

        Returns:
            LLM response text, or empty string on error.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature}
        }
        try:
            response = httpx.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=300.0
            )
            response.raise_for_status()
            raw_response = response.json()["response"]
            cleaned = raw_response.strip()
            # Extract after </think> if present
            think_match = re.search(r'</think>\s*(.*)', cleaned, re.DOTALL)
            if think_match:
                cleaned = think_match.group(1).strip()
            return cleaned
        except httpx.HTTPError as e:
            logger.error("llm_call_failed", error=str(e))
            return ""
        except Exception as e:
            logger.error("llm_call_error", error=str(e))
            return ""

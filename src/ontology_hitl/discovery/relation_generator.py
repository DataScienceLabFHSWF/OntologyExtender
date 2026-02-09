"""C1.2.3 — RelationProposalGenerator: suggest ObjectProperties between classes.

Implementation Guide
--------------------
This module uses LLM calls to suggest OWL ObjectProperties connecting
proposed new classes to existing ontology classes.

Two methods need real implementation (marked with TODO):
  1. ``suggest_relations()``        — LLM-based relation inference
  2. ``_get_existing_relations()``  — SPARQL for current ObjectProperties

Dependencies:
  - ``httpx``  for Ollama ``/api/generate`` and Fuseki SPARQL
  - ``json``   for parsing structured LLM output

Reference: KGB ``OntologyRelationDef`` schema in ``src/kgbuilder/extraction/schemas.py``
and ``FusekiOntologyService.get_all_relations()`` in ``src/kgbuilder/storage/ontology.py``.
"""

from __future__ import annotations

import json
import re

import httpx
import structlog

from ontology_hitl.core.models import ProposedClass, RelationDef

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SPARQL query templates
# ---------------------------------------------------------------------------

_SPARQL_EXISTING_RELATIONS = """\
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?prop ?label ?domainLabel ?rangeLabel
WHERE {
    ?prop a owl:ObjectProperty .
    OPTIONAL { ?prop rdfs:label ?label . }
    OPTIONAL {
        ?prop rdfs:domain ?domain .
        OPTIONAL { ?domain rdfs:label ?domainLabel . }
    }
    OPTIONAL {
        ?prop rdfs:range ?range .
        OPTIONAL { ?range rdfs:label ?rangeLabel . }
    }
}
ORDER BY ?prop
"""

# ---------------------------------------------------------------------------
# LLM prompt template
# ---------------------------------------------------------------------------

_RELATION_PROMPT = """\
You are an ontology engineer. Given a proposed new class and the existing ontology
classes, suggest relationships (OWL ObjectProperties) that connect them.

## Proposed Class
- Label: {proposed_label}
- Definition: {proposed_definition}
- Parent: {proposed_parent}
- Examples: {proposed_examples}

## Existing Ontology Classes
{existing_classes_list}

## Existing Relations (avoid duplicates)
{existing_relations_list}

## Task
Suggest 1-5 new ObjectProperty relations. For each, specify:
- Which class is the domain (subject) and which is the range (object).
- The relation name should be snake_case (e.g. ``involves``, ``located_in``).

Respond with a JSON array:
[
  {{
    "name": "<snake_case relation name>",
    "domain": "<class label that is the subject>",
    "range": "<class label that is the object>",
    "description": "<what this relation means>",
    "inverse_name": "<reverse relation name or null>",
    "cardinality": "<0..*|1..*|0..1|1..1>"
  }}
]

Rules:
- domain and range MUST be either the proposed class or one of the existing classes.
- Do NOT duplicate existing relations.
- Each relation must connect the proposed class to at least one existing class.

Respond with ONLY the JSON array, no markdown fences."""


class RelationProposalGenerator:
    """Suggest relations (ObjectProperties) between proposed and existing classes.

    Uses LLM to infer likely relationships from document evidence.

    Parameters
    ----------
    ollama_url:
        Base URL of the Ollama server.
    model:
        Ollama model name for ``/api/generate`` calls.
    fuseki_url:
        Base URL of the Fuseki server.
    dataset:
        Fuseki dataset name.
    temperature:
        LLM sampling temperature.
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

    def suggest_relations(
        self,
        proposed_class: ProposedClass,
        existing_classes: list[str],
    ) -> list[RelationDef]:
        """Suggest relations for a proposed class.

        TODO: Implement this method.

        Steps:
            1. Fetch existing relations:
               ``existing_rels = self._get_existing_relations()``

            2. Format ``_RELATION_PROMPT`` with:
               - ``proposed_label``: ``proposed_class.label``
               - ``proposed_definition``: ``proposed_class.definition``
               - ``proposed_parent``: ``proposed_class.parent_label``
               - ``proposed_examples``: comma-joined ``proposed_class.examples[:5]``
               - ``existing_classes_list``: bullet list ``"- {cls}"`` per class
               - ``existing_relations_list``:
                 bullet list ``"- {name} ({domain} → {range})"`` per relation,
                 or ``"(none)"`` if empty.

            3. Call ``self._call_llm(prompt)`` to get LLM response.

            4. Parse JSON array:
               a. ``json.loads(response)``
               b. On failure: regex ``re.search(r'\\[.*\\]', response, re.DOTALL)``
               c. On failure: log warning, return ``[]``

            5. Validate each relation dict:
               a. ``domain`` must be in ``existing_classes + [proposed_class.label]``
               b. ``range`` must be in ``existing_classes + [proposed_class.label]``
               c. ``name`` must not duplicate existing relations
               d. Skip invalid relations with a log warning.

            6. Convert valid dicts to ``RelationDef`` objects:
               ```python
               RelationDef(
                   name=rel["name"],
                   domain=rel["domain"],
                   range=rel["range"],
                   description=rel.get("description", ""),
                   inverse_name=rel.get("inverse_name"),
                   cardinality=rel.get("cardinality", "0..*"),
               )
               ```

            7. Return the list of validated ``RelationDef`` objects.

        Args:
            proposed_class: The new class to find relations for.
            existing_classes: Labels of existing ontology classes.

        Returns:
            List of suggested RelationDef objects.
        """
        logger.info(
            "suggesting_relations",
            proposed=proposed_class.label,
            existing_count=len(existing_classes),
        )

        existing_rels = self._get_existing_relations()
        existing_rel_names = {rel.get('name') for rel in existing_rels}
        existing_classes_set = set(existing_classes + [proposed_class.label])
        existing_classes_list = "\n".join(f"- {cls}" for cls in existing_classes)
        existing_relations_list = "\n".join(
            f"- {rel.get('name')} ({rel.get('domain')}  {rel.get('range')})" for rel in existing_rels
        ) or "(none)"
        prompt = _RELATION_PROMPT.format(
            proposed_label=proposed_class.label,
            proposed_definition=proposed_class.definition,
            proposed_parent=proposed_class.parent_label,
            proposed_examples=", ".join(proposed_class.examples[:5]),
            existing_classes_list=existing_classes_list,
            existing_relations_list=existing_relations_list
        )
        response = self._call_llm(prompt)
        if not response:
            return []
        try:
            rels_raw = json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                try:
                    rels_raw = json.loads(match.group(0))
                except Exception:
                    logger.warning("failed_to_parse_llm_relations", response=response)
                    return []
            else:
                logger.warning("failed_to_parse_llm_relations", response=response)
                return []
        results = []
        for rel in rels_raw:
            name = rel.get("name")
            domain = rel.get("domain")
            range_ = rel.get("range")
            if not name or not domain or not range_:
                logger.warning("invalid_relation_dict", rel=rel)
                continue
            if name in existing_rel_names:
                continue
            if domain not in existing_classes_set or range_ not in existing_classes_set:
                logger.warning("invalid_domain_or_range", rel=rel)
                continue
            results.append(RelationDef(
                name=name,
                domain=domain,
                range=range_,
                description=rel.get("description", ""),
                inverse_name=rel.get("inverse_name"),
                cardinality=rel.get("cardinality", "0..*")
            ))
        return results

    # ── Fuseki existing relations (TODO) ────────────────────────────

    def _get_existing_relations(self) -> list[dict[str, str]]:
        """Get existing ObjectProperties from Fuseki via SPARQL.

        TODO: Implement this method.

        Steps:
            1. Build SPARQL endpoint: ``f"{self.fuseki_url}/{self.dataset}/sparql"``
            2. POST ``_SPARQL_EXISTING_RELATIONS`` query using httpx.
            3. Parse JSON response bindings.
            4. Return list of dicts:
               ``[{"name": "involves", "domain": "Action", "range": "Phase"}]``
               - ``name``: use ``label`` if present, else extract from URI
               - ``domain``: use ``domainLabel`` if present, else ""
               - ``range``: use ``rangeLabel`` if present, else ""
            5. On error, log warning and return ``[]``.

        Returns:
            List of existing relation dicts.
        """
        return []

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
            2. Set timeout to 300 seconds.
            3. Parse response: ``response.json()["response"]``
            4. Strip whitespace.  If response contains ``<think>...</think>``,
               extract only content after ``</think>``.
            5. On error, return empty string.

        Args:
            prompt: Full prompt string.

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

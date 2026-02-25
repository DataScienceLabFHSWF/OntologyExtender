"""OntologyRetriever — ontology-guided query expansion.

Ported from GraphQAAgent.  Uses the Fuseki ontology to expand queries with
class hierarchies, synonyms, and expected relations *before* retrieval,
making downstream retrieval (vector, graph, hybrid) ontology-aware.
"""

from __future__ import annotations

import structlog

from ontology_hitl.connectors.fuseki import FusekiConnector
from ontology_hitl.core.models import QAQuery, QuestionType

logger = structlog.get_logger(__name__)


class OntologyRetriever:
    """Ontology-guided query expansion using Fuseki SPARQL endpoint.

    Enriches the :class:`QAQuery` with parent classes, sibling classes,
    expected relations, and synonyms before downstream retrieval.
    """

    def __init__(self, fuseki: FusekiConnector) -> None:
        self._fuseki = fuseki
        self._available = True

    async def expand_query(self, query: QAQuery) -> QAQuery:
        """Expand the query using ontology knowledge.

        Mutates and returns the same ``QAQuery`` instance for convenience.
        """
        if not self._available:
            return query

        expanded_types: list[str] = list(query.detected_types)
        expanded_relations: list[str] = list(query.expected_relations)

        for type_label in query.detected_types:
            try:
                cls = await self._fuseki.get_class_by_label(type_label)
                if cls is None:
                    continue

                # Add subclasses (expands recall)
                subclasses = await self._fuseki.get_subclasses(cls.uri)
                for sub in subclasses:
                    if sub.label not in expanded_types:
                        expanded_types.append(sub.label)

                # Add synonyms
                synonyms = await self._fuseki.get_synonyms(cls.uri)
                for syn in synonyms:
                    if syn not in expanded_types:
                        expanded_types.append(syn)

                # Add expected relations
                props = await self._fuseki.get_class_properties(cls.uri)
                for prop in props:
                    if prop.label not in expanded_relations:
                        expanded_relations.append(prop.label)
            except Exception as exc:
                logger.warning(
                    "ontology.expand_failed", type_label=type_label, error=str(exc)
                )
                self._available = False
                break

        query.detected_types = expanded_types
        query.expected_relations = expanded_relations

        logger.info(
            "ontology.expand",
            original_types=len(query.detected_types),
            expanded_types=len(expanded_types),
            expected_relations=len(expanded_relations),
        )
        return query

    async def get_expected_relations(self, entity_types: list[str]) -> list[str]:
        """Given ontology classes, return which relations to prioritise."""
        if not self._available:
            return []

        relations: list[str] = []
        for type_label in entity_types:
            try:
                cls = await self._fuseki.get_class_by_label(type_label)
                if cls is None:
                    continue
                props = await self._fuseki.get_class_properties(cls.uri)
                relations.extend(p.label for p in props if p.label not in relations)
            except Exception as exc:
                logger.warning(
                    "ontology.relations_failed", type_label=type_label, error=str(exc)
                )
                break
        return relations

    async def get_answer_template(
        self,
        question_type: QuestionType | None,
        entity_types: list[str],
    ) -> str:
        """Generate an answer-structure hint based on ontology and question type."""
        if not question_type:
            return ""

        type_labels = ", ".join(entity_types[:3]) if entity_types else "relevant entities"

        templates = {
            QuestionType.FACTOID: f"Provide a concise factual answer about {type_labels}.",
            QuestionType.LIST: f"List all instances of {type_labels} that match the question.",
            QuestionType.BOOLEAN: "Answer with Yes or No, then provide justification.",
            QuestionType.COMPARATIVE: f"Compare the mentioned {type_labels}, highlighting differences.",
            QuestionType.CAUSAL: "Explain the causal chain, citing specific entities and relations.",
            QuestionType.AGGREGATION: f"Provide the count or aggregation over {type_labels}.",
        }
        return templates.get(question_type, "")

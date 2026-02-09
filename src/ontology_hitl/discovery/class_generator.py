"""C1.2.2 — ClassDefinitionGenerator: LLM-based class definition proposals."""

from __future__ import annotations

import structlog

from ontology_hitl.core.models import GapCandidate, ProposedClass, PropertyDef

logger = structlog.get_logger(__name__)


class ClassDefinitionGenerator:
    """Generate structured class definitions via LLM.

    Takes gap candidates and produces fully specified ProposedClass objects
    with definitions, parent classes, and suggested properties.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:18134",
        model: str = "qwen3:8b",
        fuseki_url: str = "http://localhost:3030",
        dataset: str = "kgbuilder",
        temperature: float = 0.5,
    ) -> None:
        self.ollama_url = ollama_url
        self.model = model
        self.fuseki_url = fuseki_url
        self.dataset = dataset
        self.temperature = temperature

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
    ) -> ProposedClass:
        """Generate a single class proposal via LLM.

        TODO: Implement LLM call for definition generation.
        """
        # Placeholder — will call Ollama in full implementation
        logger.info("generating_class_definition", entity_type=entity_type)

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

    def _suggest_default_properties(self, entity_type: str) -> list[PropertyDef]:
        """Generate default properties for a class.

        TODO: Replace with LLM-generated properties.
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

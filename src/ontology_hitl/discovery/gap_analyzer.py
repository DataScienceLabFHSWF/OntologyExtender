"""C1.2.1 — OntologyGapAnalyzer: find entities not covered by seed ontology."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from ontology_hitl.core.models import ExtractedEntitySummary, GapCandidate, GapReport

logger = structlog.get_logger(__name__)


class OntologyGapAnalyzer:
    """Analyze which extracted entities don't fit seed ontology classes.

    Compares KGB extraction checkpoint entities against the current ontology
    to identify gap candidates that should become new classes.
    """

    def __init__(
        self,
        fuseki_url: str = "http://localhost:3030",
        dataset: str = "kgbuilder",
        min_frequency: int = 3,
        similarity_threshold: float = 0.65,
    ) -> None:
        self.fuseki_url = fuseki_url
        self.dataset = dataset
        self.min_frequency = min_frequency
        self.similarity_threshold = similarity_threshold

    def analyze(self, checkpoint_path: Path) -> GapReport:
        """Run gap analysis on KGB extraction checkpoint.

        Args:
            checkpoint_path: Path to extraction_checkpoint.json from KGB.

        Returns:
            GapReport with coverage stats and gap candidates.
        """
        logger.info("gap_analysis_start", checkpoint=str(checkpoint_path))

        # Load checkpoint
        entities = self._load_checkpoint(checkpoint_path)

        # Get current ontology classes
        ontology_classes = self._get_ontology_classes()

        # Classify entities as covered or uncovered
        covered, uncovered = self._classify_entities(entities, ontology_classes)

        # Group uncovered into gap candidates
        gap_candidates = self._build_gap_candidates(uncovered)

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

    def _load_checkpoint(self, path: Path) -> list[ExtractedEntitySummary]:
        """Load entities from KGB extraction checkpoint JSON."""
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

    def _get_ontology_classes(self) -> list[str]:
        """Get all class labels from the current ontology via SPARQL.

        TODO: Implement SPARQL query against Fuseki.
        """
        # Placeholder — will query Fuseki in implementation
        logger.warning("using_placeholder_ontology_classes")
        return []

    def _classify_entities(
        self,
        entities: list[ExtractedEntitySummary],
        ontology_classes: list[str],
    ) -> tuple[list[ExtractedEntitySummary], list[ExtractedEntitySummary]]:
        """Split entities into covered (match ontology) and uncovered.

        TODO: Implement semantic matching with similarity threshold.
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

    def _build_gap_candidates(
        self,
        uncovered: list[ExtractedEntitySummary],
    ) -> list[GapCandidate]:
        """Group uncovered entities into gap candidates by entity type.

        TODO: Add semantic similarity grouping via embeddings.
        """
        from collections import Counter, defaultdict

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
                )
            )

        # Sort by frequency descending
        candidates.sort(key=lambda c: c.frequency, reverse=True)
        return candidates

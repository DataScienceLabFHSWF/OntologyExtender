"""C1.3.1 — OntologySchemaManager: add/remove classes with validation."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from ontology_hitl.core.exceptions import SchemaUpdateError
from ontology_hitl.core.models import ProposedClass

logger = structlog.get_logger(__name__)


class OntologySchemaManager:
    """Manage ontology schema: add/remove classes, export OWL.

    Operates on a seed ontology and applies accepted proposals
    to produce an extended version.
    """

    def __init__(self, seed_ontology_path: Path | str) -> None:
        self.seed_ontology_path = Path(seed_ontology_path)
        self._accepted_classes: list[ProposedClass] = []

    def apply_decisions(
        self,
        proposals_path: Path | str,
        decisions_path: Path | str,
    ) -> list[ProposedClass]:
        """Load proposals + decisions, return accepted ProposedClass list.

        Args:
            proposals_path: JSON file with proposals.
            decisions_path: JSON file with review decisions.

        Returns:
            List of accepted ProposedClass objects.
        """
        with open(proposals_path) as f:
            proposals = json.load(f)
        with open(decisions_path) as f:
            decisions = json.load(f)

        # Index decisions by proposal_id
        decision_map = {d["proposal_id"]: d for d in decisions}

        accepted: list[ProposedClass] = []
        for prop in proposals:
            pid = prop.get("id", "")
            dec = decision_map.get(pid, {})
            if dec.get("decision") == "accept":
                accepted.append(
                    ProposedClass(
                        id=pid,
                        label=prop["label"],
                        definition=prop.get("definition", ""),
                        parent_uri=prop.get("parent_uri", ""),
                        parent_label=prop.get("parent_label", ""),
                        examples=prop.get("examples", []),
                        frequency=prop.get("frequency", 0),
                        confidence=prop.get("confidence", 0.0),
                    )
                )

        self._accepted_classes = accepted
        logger.info("decisions_applied", accepted=len(accepted), total=len(proposals))
        return accepted

    def export_owl(self, output_path: Path | str) -> None:
        """Export extended ontology as OWL/XML.

        TODO: Implement OWL serialization with rdflib.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "export_owl",
            path=str(output_path),
            classes=len(self._accepted_classes),
        )
        # Placeholder — will use rdflib to build and serialize OWL graph
        raise NotImplementedError("OWL export not yet implemented")

    def export_updated_cqs(self, output_path: Path | str) -> None:
        """Export updated competency questions JSON.

        TODO: Implement CQ generation from accepted classes.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("export_cqs", path=str(output_path))
        # Placeholder
        raise NotImplementedError("CQ export not yet implemented")

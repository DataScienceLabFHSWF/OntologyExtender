#!/usr/bin/env python3
"""Step 5: Export accepted proposals as extended ontology + updated CQs.

Usage:
    python scripts/export_ontology.py \
        --decisions data/iterations/v1/decisions.json \
        --proposals data/iterations/v1/proposals.json \
        --seed data/seed_ontology/plan-ontology-v1.0.owl \
        --output-owl data/exports/ontology_v2.0.owl \
        --output-cq data/exports/cq_v2.0.json
"""
from __future__ import annotations

from pathlib import Path

import typer
import structlog

from ontology_hitl.agents.moderator import Moderator
from ontology_hitl.schema.manager import OntologySchemaManager
from ontology_hitl.schema.shacl_generator import SHACLGenerator

logger = structlog.get_logger(__name__)
app = typer.Typer()


@app.command()
def main(
    decisions: Path = typer.Option(..., help="Review decisions JSON"),
    proposals: Path = typer.Option(..., help="Proposals JSON"),
    seed: Path = typer.Option("data/seed_ontology/plan-ontology-v1.0.owl", help="Seed ontology"),
    output_owl: Path = typer.Option("data/exports/ontology_latest.owl", help="Output OWL file"),
    output_cq: Path = typer.Option("data/exports/cq_latest.json", help="Output CQ JSON"),
    existing_cq: Path = typer.Option("data/evaluation/competency_questions.json", help="Existing CQ file to extend"),
    experiment_name: str = typer.Option("", help="Experiment name for directory lookup"),
) -> None:
    """Export accepted proposals as extended ontology."""
    # Set default paths based on experiment name
    if experiment_name:
        base_iterations = Path("data/iterations") / experiment_name
        base_exports = Path("data/exports") / experiment_name
        base_exports.mkdir(parents=True, exist_ok=True)

        decisions = decisions or base_iterations / "decisions.json"
        proposals = proposals or base_iterations / "proposals.json"
        output_owl = output_owl or base_exports / "ontology_latest.owl"
        output_cq = output_cq or base_exports / "cq_latest.json"
    else:
        # Legacy defaults
        decisions = decisions or Path("data/iterations/v1/decisions.json")
        proposals = proposals or Path("data/iterations/v1/proposals.json")
        output_owl = output_owl or Path("data/exports/ontology_latest.owl")
        output_cq = output_cq or Path("data/exports/cq_latest.json")

    manager = OntologySchemaManager(seed_ontology_path=seed)

    # Load accepted proposals
    accepted_classes = manager.apply_decisions(
        proposals_path=proposals,
        decisions_path=decisions,
    )

    # Load existing CQs for extension
    existing_cqs = []
    if existing_cq.exists():
        import json
        with open(existing_cq) as f:
            existing_cqs = json.load(f)

    # Generate new CQs based on accepted classes (debate outcomes)
    moderator = Moderator()
    new_cqs = moderator.generate_competency_questions(
        accepted_classes=accepted_classes,
        existing_cqs=existing_cqs,
    )

    # Extend existing CQs with new ones
    extended_cqs = existing_cqs + new_cqs

    # Generate SHACL shapes
    shacl_gen = SHACLGenerator()
    for cls in accepted_classes:
        shacl_gen.generate_shape(cls)

    # Export
    output_owl.parent.mkdir(parents=True, exist_ok=True)
    manager.export_owl(output_owl)
    manager.export_updated_cqs(output_cq)

    # Save extended CQs
    import json
    with open(output_cq, "w") as f:
        json.dump(extended_cqs, f, indent=2)

    logger.info(
        "export_complete",
        classes_added=len(accepted_classes),
        new_cqs_generated=len(new_cqs),
        total_cqs=len(extended_cqs),
        owl_path=str(output_owl),
        cq_path=str(output_cq),
    )


if __name__ == "__main__":
    app()

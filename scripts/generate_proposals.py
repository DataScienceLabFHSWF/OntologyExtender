#!/usr/bin/env python3
"""Step 3: Generate proposed ontology classes from gap report.

Usage:
    python scripts/generate_proposals.py \
        --gap-report data/iterations/v1/gap_report.json \
        --output data/iterations/v1/proposals.json
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
import structlog

from ontology_hitl.core.config import Settings
from ontology_hitl.discovery.class_generator import ClassDefinitionGenerator
from ontology_hitl.discovery.relation_generator import RelationProposalGenerator

logger = structlog.get_logger(__name__)
app = typer.Typer()


@app.command()
def main(
    gap_report: Path = typer.Option(..., help="Gap report JSON from step 2"),
    output: Path = typer.Option("data/iterations/v1/proposals.json", help="Output proposals"),
    max_proposals: int = typer.Option(30, help="Max number of proposals to generate"),
) -> None:
    """Generate class and relation proposals from gap analysis."""
    settings = Settings()

    with open(gap_report) as f:
        report = json.load(f)

    class_gen = ClassDefinitionGenerator(
        ollama_url=settings.ollama_url,
        model=settings.ollama_model,
        fuseki_url=settings.fuseki_url,
        dataset=settings.fuseki_dataset,
    )

    proposals = class_gen.generate_from_gaps(
        gap_candidates=report["gap_candidates"],
        max_proposals=max_proposals,
    )

    # Also generate relation proposals
    relation_gen = RelationProposalGenerator(
        ollama_url=settings.ollama_url,
        model=settings.ollama_model,
    )
    for proposal in proposals:
        proposal.suggested_relations = relation_gen.suggest_relations(
            proposed_class=proposal,
            existing_classes=report.get("existing_classes", []),
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump([p.__dict__ for p in proposals], f, indent=2, default=str)

    logger.info("proposals_generated", count=len(proposals))


if __name__ == "__main__":
    app()

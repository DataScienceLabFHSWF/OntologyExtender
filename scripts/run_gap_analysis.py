#!/usr/bin/env python3
"""Step 2: Analyze gaps between KGB extraction and current ontology.

Usage:
    python scripts/run_gap_analysis.py \
        --checkpoint ../KnowledgeGraphBuilder/output/extraction_checkpoint.json \
        --ontology data/seed_ontology/plan-ontology-v1.0.owl \
        --output data/iterations/v1/gap_report.json
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
import structlog

from ontology_hitl.core.config import Settings
from ontology_hitl.discovery.gap_analyzer import OntologyGapAnalyzer

logger = structlog.get_logger(__name__)
app = typer.Typer()


@app.command()
def main(
    checkpoint: Path = typer.Option(..., help="KGB extraction checkpoint JSON"),
    ontology: Path = typer.Option(None, help="Ontology file (OWL/TTL). Uses Fuseki if not set."),
    output: Path = typer.Option("data/iterations/v1/gap_report.json", help="Output gap report"),
    min_frequency: int = typer.Option(3, help="Min entity frequency to consider"),
) -> None:
    """Run gap analysis on KGB extraction results."""
    settings = Settings()

    analyzer = OntologyGapAnalyzer(
        fuseki_url=settings.fuseki_url,
        dataset=settings.fuseki_dataset,
        min_frequency=min_frequency,
    )

    report = analyzer.analyze(checkpoint_path=checkpoint)

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(
        "gap_analysis_complete",
        total=report.total_extracted_entities,
        covered=report.covered_entities,
        gaps=len(report.gap_candidates),
        coverage_pct=f"{report.coverage_pct:.1%}",
    )


if __name__ == "__main__":
    app()

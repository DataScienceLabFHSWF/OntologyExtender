#!/usr/bin/env python3
"""Step 7: Evaluate improvement after re-running KGB with extended ontology.

Usage:
    python scripts/evaluate_iteration.py \
        --before output/kg_metrics_v1.json \
        --after ../KnowledgeGraphBuilder/output/kg_metrics.json \
        --output data/iterations/v1/evaluation_report.json
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
import structlog
from rich.console import Console
from rich.table import Table

from ontology_hitl.evaluation.reporter import IterationReporter

logger = structlog.get_logger(__name__)
console = Console()
app = typer.Typer()


@app.command()
def main(
    before: Path = typer.Option(..., help="KG metrics JSON before extension"),
    after: Path = typer.Option(..., help="KG metrics JSON after extension"),
    output: Path = typer.Option("data/iterations/v1/evaluation_report.json", help="Report output"),
) -> None:
    """Compare before/after metrics for an iteration."""
    reporter = IterationReporter()

    report = reporter.compare(before_path=before, after_path=after)

    # Display results
    table = Table(title="Iteration Evaluation")
    table.add_column("Metric", style="bold")
    table.add_column("Before", justify="right")
    table.add_column("After", justify="right")
    table.add_column("Change", justify="right")

    for metric in report["metrics"]:
        change = metric["after"] - metric["before"]
        color = "green" if change > 0 else "red" if change < 0 else "white"
        table.add_row(
            metric["name"],
            f"{metric['before']:.2%}",
            f"{metric['after']:.2%}",
            f"[{color}]{change:+.2%}[/{color}]",
        )

    console.print(table)

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("evaluation_complete")


if __name__ == "__main__":
    app()

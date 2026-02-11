#!/usr/bin/env python3
"""Run the Ontology↔KG co-evolution feedback loop.

This is the main entry point for the iterative ontology extension process.
It can run in standalone mode (Qdrant-only) or coupled mode (with KGB).

Usage — standalone (no KGB dependency):
    python scripts/run_feedback_loop.py --mode standalone --max-iterations 4

Usage — coupled (with KGB):
    python scripts/run_feedback_loop.py --mode coupled \
        --checkpoint ../KnowledgeGraphBuilder/output/extraction_checkpoint.json \
        --max-iterations 4

Usage — auto-accept (for experiments, no interactive review):
    python scripts/run_feedback_loop.py --mode standalone --auto-review
"""
from __future__ import annotations

from pathlib import Path

import typer
import structlog

from ontology_hitl.core.config import Settings
from ontology_hitl.core.feedback_protocol import LoopMode
from ontology_hitl.core.loop_orchestrator import FeedbackLoopOrchestrator

logger = structlog.get_logger(__name__)
app = typer.Typer()


@app.command()
def main(
    mode: str = typer.Option("standalone", help="Loop mode: 'standalone' or 'coupled'"),
    checkpoint: Path = typer.Option(None, help="KGB checkpoint (coupled mode)"),
    max_iterations: int = typer.Option(4, help="Max iteration cycles"),
    convergence_threshold: float = typer.Option(0.02, help="Stop when improvement < this"),
    auto_review: bool = typer.Option(False, help="Auto-accept proposals (no interactive review)"),
    experiment_name: str = typer.Option("", help="Experiment name for wandb run naming"),
) -> None:
    """Run the ontology extension feedback loop."""
    settings = Settings()

    loop_mode = LoopMode.COUPLED if mode == "coupled" else LoopMode.STANDALONE

    if loop_mode == LoopMode.COUPLED and checkpoint is None:
        logger.warning("coupled_mode_no_checkpoint",
                       msg="No checkpoint provided, will fall back to Qdrant")

    orchestrator = FeedbackLoopOrchestrator(
        settings=settings,
        mode=loop_mode,
        max_iterations=max_iterations,
        convergence_threshold=convergence_threshold,
        experiment_name=experiment_name,
    )

    report = orchestrator.run(
        checkpoint_path=checkpoint,
        auto_review=auto_review,
    )

    summary = report.compute_summary()
    logger.info(
        "feedback_loop_complete",
        iterations=report.total_iterations,
        entity_coverage_delta=f"{summary.get('entity_coverage', {}).get('delta', 0):.1%}",
        cq_coverage_delta=f"{summary.get('cq_coverage', {}).get('delta', 0):.1%}",
        converged_at=summary.get("converged_at", "N/A"),
    )


if __name__ == "__main__":
    app()

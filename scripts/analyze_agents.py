#!/usr/bin/env python3
"""Demonstrate agent performance analytics and debate strategies.

Usage:
    python scripts/analyze_agents.py --iterations 3 --strategy dialectical
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
import structlog

from ontology_hitl.agents import AgentTeam, DebateStrategy
from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)
app = typer.Typer()


@app.command()
def main(
    iterations: int = typer.Option(3, help="Number of debate iterations to run"),
    strategy: str = typer.Option("consensus", help="Debate strategy: consensus, dialectical, socratic, delphi"),
    output: Path = typer.Option("agent_analytics.json", help="Output file for analytics"),
) -> None:
    """Run agent debates and analyze performance."""

    settings = Settings()
    strategy_enum = DebateStrategy(strategy)

    # Sample document context for testing
    sample_docs = """
    Nuclear decommissioning involves safely dismantling nuclear facilities.
    Facilities contain radioactive materials that require special handling.
    Decommissioning strategies include immediate dismantling and safe enclosure.
    Regulatory requirements govern all decommissioning activities.
    Radiation hazards must be monitored continuously during operations.
    """

    # Create agent team
    team = AgentTeam(
        settings=settings,
        document_context=sample_docs,
        max_debate_rounds=2,
    )

    # Set sample competency questions for critic
    sample_cqs = [
        {"id": "CQ1", "question": "What are the main decommissioning strategies?"},
        {"id": "CQ2", "question": "What safety requirements apply to decommissioning?"},
    ]
    team.set_competency_questions(sample_cqs)

    # Run debates across different phases
    from ontology_hitl.methodology.ontology101 import Phase

    phases_to_test = [Phase.SCOPE_AND_CQS, Phase.TERMS, Phase.CLASS_HIERARCHY]

    for i in range(iterations):
        for phase in phases_to_test:
            context = f"Sample context for {phase.value} (iteration {i+1})"
            outcome = team.run_debate(phase, context)
            logger.info("debate_completed", phase=phase.value, verdict=outcome.verdict.value)

    # Get performance analytics
    analytics = team.get_performance_analytics()

    # Save results
    results = {
        "strategy": strategy,
        "iterations": iterations,
        "phases_tested": [p.value for p in phases_to_test],
        "performance_analytics": analytics,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(results, f, indent=2)

    # Display summary
    print(f"\n🤖 Agent Performance Analytics ({strategy} strategy)")
    print("=" * 60)

    for agent, metrics in analytics.items():
        print(f"\n{agent.upper()}:")
        print(f"  Total debates: {metrics['total_debates']}")
        print(f"  Consensus contributions: {metrics['consensus_contributions']}")
        print(f"  Revisions requested: {metrics['revisions_requested']}")
        print(f"  Escalations caused: {metrics['escalations_caused']}")
        print(".1f")
        print(".2f")
        print(f"  Issues per debate: {metrics['issues_raised_per_debate']:.2f}")

    print(f"\n📊 Results saved to {output}")


if __name__ == "__main__":
    app()
#!/usr/bin/env python3
"""Step 4: Interactive CLI review of proposed classes.

Usage:
    python scripts/review_proposals.py \
        --proposals data/iterations/v1/proposals.json \
        --output data/iterations/v1/decisions.json
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

logger = structlog.get_logger(__name__)
console = Console()
app = typer.Typer()


@app.command()
def main(
    proposals: Path = typer.Option(..., help="Proposals JSON from step 3"),
    output: Path = typer.Option("data/iterations/v1/decisions.json", help="Output decisions"),
    reviewer: str = typer.Option("expert", help="Reviewer name"),
) -> None:
    """Interactive review session for proposed ontology classes."""
    with open(proposals) as f:
        proposal_list = json.load(f)

    decisions = []
    total = len(proposal_list)

    console.print(f"\n[bold]Reviewing {total} proposals[/bold]\n")

    for i, proposal in enumerate(proposal_list, 1):
        console.print(Panel(
            f"[bold]{proposal['label']}[/bold]\n\n"
            f"Definition: {proposal['definition']}\n\n"
            f"Parent class: {proposal.get('parent_label', 'N/A')}\n"
            f"Examples: {', '.join(proposal.get('examples', [])[:5])}\n"
            f"Frequency: {proposal.get('frequency', 0)} occurrences\n"
            f"Confidence: {proposal.get('confidence', 0):.2f}",
            title=f"Proposal {i}/{total}",
        ))

        # Show suggested properties
        if proposal.get("suggested_properties"):
            table = Table(title="Suggested Properties")
            table.add_column("Name")
            table.add_column("Type")
            table.add_column("Required")
            for prop in proposal["suggested_properties"]:
                table.add_row(prop["name"], prop["datatype"], str(prop.get("required", False)))
            console.print(table)

        # Show suggested relations
        if proposal.get("suggested_relations"):
            table = Table(title="Suggested Relations")
            table.add_column("Name")
            table.add_column("Domain")
            table.add_column("Range")
            for rel in proposal["suggested_relations"]:
                table.add_row(rel["name"], rel["domain"], rel["range"])
            console.print(table)

        decision = Prompt.ask(
            "Decision",
            choices=["accept", "reject", "revise", "skip"],
            default="skip",
        )

        rationale = ""
        if decision in ("reject", "revise"):
            rationale = Prompt.ask("Rationale")

        decisions.append({
            "proposal_id": proposal.get("id", f"prop_{i}"),
            "proposal_label": proposal["label"],
            "reviewer": reviewer,
            "decision": decision,
            "rationale": rationale,
        })

        console.print()

    # Summary
    accepted = sum(1 for d in decisions if d["decision"] == "accept")
    rejected = sum(1 for d in decisions if d["decision"] == "reject")
    console.print(f"\n[bold green]Accepted: {accepted}[/bold green]  "
                  f"[bold red]Rejected: {rejected}[/bold red]  "
                  f"Total: {total}\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(decisions, f, indent=2)

    logger.info("review_complete", accepted=accepted, rejected=rejected)


if __name__ == "__main__":
    app()

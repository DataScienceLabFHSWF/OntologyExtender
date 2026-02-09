"""C1.4.1 — CLI review tool using Typer + Rich."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(name="hitl-review", help="Human-in-the-Loop Ontology Review CLI")
console = Console()


@app.command()
def review(
    proposals: str = typer.Option(..., help="Path to proposals JSON"),
    output: str = typer.Option("decisions.json", help="Output decisions JSON"),
    reviewer: str = typer.Option("expert", help="Reviewer name"),
) -> None:
    """Interactive review session for proposed ontology classes."""
    console.print(f"[bold]Starting review session...[/bold]")
    console.print(f"  Proposals: {proposals}")
    console.print(f"  Reviewer:  {reviewer}")
    console.print(f"  Output:    {output}")
    console.print()
    console.print("[yellow]Review interface not yet implemented.[/yellow]")
    console.print("Run `python scripts/review_proposals.py` for the full review workflow.")


@app.command()
def status(
    decisions: str = typer.Option("decisions.json", help="Decisions JSON to summarize"),
) -> None:
    """Show summary of review decisions."""
    import json
    from pathlib import Path

    path = Path(decisions)
    if not path.exists():
        console.print(f"[red]Decisions file not found: {decisions}[/red]")
        raise typer.Exit(1)

    with open(path) as f:
        data = json.load(f)

    accepted = sum(1 for d in data if d.get("decision") == "accept")
    rejected = sum(1 for d in data if d.get("decision") == "reject")
    revised = sum(1 for d in data if d.get("decision") == "revise")
    total = len(data)

    console.print(f"\n[bold]Review Summary[/bold]")
    console.print(f"  Total:    {total}")
    console.print(f"  [green]Accepted: {accepted}[/green]")
    console.print(f"  [red]Rejected: {rejected}[/red]")
    console.print(f"  [yellow]Revised:  {revised}[/yellow]")


if __name__ == "__main__":
    app()

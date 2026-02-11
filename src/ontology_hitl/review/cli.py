"""C1.4.1 — CLI review tool using Typer + Rich.

Implementation Guide
--------------------
This module provides a terminal-based interactive review workflow.
The expert sees each proposed class one-at-a-time with Rich panels
and decides: accept / reject / revise.

Two commands:
  1. ``review``  — Interactive loop over proposals (implemented)
  2. ``status``  — Summary of decisions (done)

UI pattern per proposal (using Rich):
  ┌─ Proposed Class: BuildingPermit ──────────────────────┐
  │  Parent: AdministrativeProcess                        │
  │  Definition: A formal approval issued by a …          │
  │  Confidence: 0.87 │ Frequency: 14                     │
  │                                                       │
  │  Properties:                                          │
  │    • permit_number (xsd:string, required)             │
  │    • issue_date   (xsd:date, required)                │
  │                                                       │
  │  Relations:                                           │
  │    • issuedBy → Authority (0..1)                      │
  │    • appliesTo → Building (1..1)                      │
  ├───────────────────────────────────────────────────────┤
  │  [a] Accept  [r] Reject  [e] Edit (revise)  [s] Skip │
  └───────────────────────────────────────────────────────┘

Dependencies:
  - ``typer``    CLI framework
  - ``rich``     for Panel, Table, Prompt, Console
  - ``json``     for loading/saving proposals and decisions
  - ``datetime`` for timestamps
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

app = typer.Typer(name="hitl-review", help="Human-in-the-Loop Ontology Review CLI")
console = Console()


def _render_proposal(proposal: dict, index: int, total: int) -> Panel:
    from rich.table import Table
    table = Table(show_header=False, box=None)
    table.add_row("Parent:", proposal.get("parent_label", "—"))
    table.add_row("Definition:", proposal.get("definition", "—"))
    table.add_row("Confidence:", str(proposal.get("confidence", 0)))
    table.add_row("Frequency:", str(proposal.get("frequency", 0)))
    table.add_row("", "")
    table.add_row("[bold]Properties:[/bold]", "")
    for prop in proposal.get("suggested_properties", []):
        table.add_row("  •", f"{prop['name']} ({prop.get('datatype','?')}{', required' if prop.get('required') else ''})")
    if proposal.get("suggested_relations"):
        table.add_row("", "")
        table.add_row("[bold]Relations:[/bold]", "")
        for rel in proposal["suggested_relations"]:
            table.add_row("  •", f"{rel['name']} → {rel['range']} ({rel.get('cardinality','0..*')})")
    return Panel(table, title=f"[{index}/{total}] Proposed Class: {proposal.get('label', '?')}", border_style="cyan")


def _prompt_decision(proposal_id: str) -> dict:
    from rich.prompt import Prompt
    from datetime import datetime
    choice = Prompt.ask(
        "[a]ccept / [r]eject / [e]dit / [s]kip",
        choices=["a", "r", "e", "s"],
        default="s")
    if choice == "s":
        return None
    decision = {
        "a": "accepted",
        "r": "rejected",
        "e": "needs_revision"
    }[choice]
    rationale = Prompt.ask("Rationale (optional)", default="")
    changes = ""
    if decision == "needs_revision":
        changes = Prompt.ask("Suggested changes (optional)", default="")
    return {
        "proposal_id": proposal_id,
        "decision": decision,
        "rationale": rationale,
        "timestamp": datetime.now().isoformat(),
        "suggested_changes": changes if decision == "needs_revision" else ""
    }


@app.command()
def review(
    proposals: str = typer.Option(..., help="Path to proposals JSON"),
    output: str = typer.Option("decisions.json", help="Output decisions JSON"),
    reviewer: str = typer.Option("expert", help="Reviewer name"),
) -> None:
    """Interactive review session for proposed ontology classes."""
    data = json.loads(Path(proposals).read_text())
    existing = json.loads(Path(output).read_text()) if Path(output).exists() else []
    reviewed_ids = {d["proposal_id"] for d in existing}
    pending = [p for p in data if p["id"] not in reviewed_ids]
    console.print(f"[bold]Review session: {len(pending)} pending of {len(data)} total[/bold]")
    for idx, proposal in enumerate(pending, 1):
        panel = _render_proposal(proposal, idx, len(pending))
        console.print(panel)
        decision = _prompt_decision(proposal["id"])
        if decision is None:
            continue
        decision["reviewer"] = reviewer
        existing.append(decision)
        Path(output).write_text(json.dumps(existing, indent=2))
        console.print(f"[green]Recorded: {decision['decision']}[/green]")
    console.print(f"[bold]Review complete. Total decisions: {len(existing)}[/bold]")


@app.command()
def status(
    decisions: str = typer.Option("decisions.json", help="Decisions JSON to summarize"),
) -> None:
    """Show summary of review decisions."""
    path = Path(decisions)
    if not path.exists():
        console.print(f"[red]Decisions file not found: {decisions}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text())

    accepted = sum(1 for d in data if d.get("decision") == "accepted")
    rejected = sum(1 for d in data if d.get("decision") == "rejected")
    revised = sum(1 for d in data if d.get("decision") == "needs_revision")
    total = len(data)

    table = Table(title="Review Summary")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("[green]Accepted[/green]", str(accepted))
    table.add_row("[red]Rejected[/red]", str(rejected))
    table.add_row("[yellow]Needs Revision[/yellow]", str(revised))
    table.add_row("Total", str(total))
    console.print(table)


if __name__ == "__main__":
    app()

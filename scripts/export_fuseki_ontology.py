#!/usr/bin/env python3
"""Export ontology from Fuseki to JSON format.

Usage:
    python scripts/export_fuseki_ontology.py \
        --fuseki-url http://localhost:3030 \
        --dataset kgbuilder \
        --output ontology.json \
        --id ontology-demo-facility \
        --name "Facility Demo"
"""

import asyncio
import sys
from pathlib import Path

import typer

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ontology_hitl.export.fuseki_json_exporter import export_ontology_from_fuseki

app = typer.Typer()


@app.command()
def main(
    fuseki_url: str = typer.Option(
        "http://localhost:3030",
        "--fuseki-url",
        help="Base URL of Fuseki server",
    ),
    dataset: str = typer.Option(
        "kgbuilder",
        "--dataset",
        help="Fuseki dataset name",
    ),
    output: Path = typer.Option(
        "ontology.json",
        "--output",
        "-o",
        help="Output JSON file path",
    ),
    ontology_id: str = typer.Option(
        "ontology-export",
        "--id",
        help="Ontology identifier",
    ),
    ontology_name: str = typer.Option(
        "Exported Ontology",
        "--name",
        help="Ontology display name",
    ),
    version: str = typer.Option(
        "1.0.0",
        "--version",
        help="Ontology version",
    ),
) -> None:
    """Export ontology from Fuseki to structured JSON.

    Queries the Fuseki RDF triple store and produces a JSON document
    with classes and relations in the standard format.
    """
    typer.echo(f"📤 Exporting ontology from Fuseki...")
    typer.echo(f"   Fuseki URL: {fuseki_url}")
    typer.echo(f"   Dataset: {dataset}")

    try:
        data = asyncio.run(
            export_ontology_from_fuseki(
                output_path=output,
                fuseki_url=fuseki_url,
                dataset=dataset,
                ontology_id=ontology_id,
                ontology_name=ontology_name,
                version=version,
            )
        )

        typer.echo(f"✅ Export complete!")
        typer.echo(f"   Saved to: {output}")
        typer.echo(f"   Classes: {len(data['classes'])}")
        typer.echo(f"   Relations: {len(data['relations'])}")

    except Exception as e:
        typer.echo(f"❌ Export failed: {e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

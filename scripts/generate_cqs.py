#!/usr/bin/env python3
"""Generate competency questions from Qdrant documents.

Reads document chunks from the shared Qdrant vector store and uses the
LLM to propose competency questions that the ontology should answer.
Merges with any existing CQs (won't duplicate).

Usage:
    python scripts/generate_cqs.py

    python scripts/generate_cqs.py \
        --num-chunks 50 \
        --output data/evaluation/competency_questions.json
"""
from __future__ import annotations

import os
from pathlib import Path

import typer
import structlog

from ontology_hitl.core.config import Settings
from ontology_hitl.sources.qdrant_source import QdrantDocumentSource
from ontology_hitl.sources.cq_generator import CQGenerator

logger = structlog.get_logger(__name__)
app = typer.Typer()


@app.command()
def main(
    num_chunks: int = typer.Option(30, help="Number of doc chunks to sample"),
    batch_size: int = typer.Option(5, help="Chunks per LLM call"),
    output: Path = typer.Option(
        "data/evaluation/competency_questions.json",
        help="Output CQ JSON path",
    ),
) -> None:
    """Generate competency questions from Qdrant documents."""
    settings = Settings()

    source = QdrantDocumentSource(
        qdrant_url=settings.qdrant_url,
        collection=os.getenv("HITL_QDRANT_COLLECTION") or settings.qdrant_collection,
        ollama_url=settings.ollama_url,
        ollama_model=settings.ollama_model,
    )

    generator = CQGenerator(
        qdrant_source=source,
        ollama_url=settings.ollama_url,
        ollama_model=settings.ollama_model,
    )

    path = generator.generate_and_save(
        output_path=output,
        num_chunks=num_chunks,
        batch_size=batch_size,
    )

    logger.info("cq_generation_complete", output=str(path))


if __name__ == "__main__":
    app()

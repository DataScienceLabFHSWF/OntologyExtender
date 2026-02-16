#!/usr/bin/env python3
"""Index SAR text files into Qdrant using Ollama embeddings.

Usage:
    python scripts/index_sar_documents.py --source data/SAR_docs_text --collection documents

Behavior:
- Chunk size: 750 characters (no overlap) to match LLM4ACOE settings.
- Embeddings: Ollama `qwen3-embedding` (configured via Settings if available).
- Upserts points into the named Qdrant collection (default: `documents`).

This is idempotent for the typical small SAR dataset (uses stable chunk IDs).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Iterable, List

import httpx
import typer

app = typer.Typer()


def chunk_text(text: str, size: int = 750, overlap: int = 0) -> list[str]:
    if size <= 0:
        return [text]
    chunks: list[str] = []
    start = 0
    step = size - overlap if size > overlap else size
    while start < len(text):
        chunk = text[start : start + size]
        chunks.append(chunk.strip())
        start += step
    return chunks


def stable_chunk_id(document_name: str, idx: int) -> str:
    key = f"{document_name}::chunk::{idx}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def ollama_embed(texts: list[str], ollama_url: str = "http://localhost:18135", model: str = "qwen3-embedding") -> list[list[float]]:
    url = ollama_url.rstrip("/") + "/api/embed"
    resp = httpx.post(url, json={"model": model, "input": texts}, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    return data.get("embeddings", [])


def upsert_qdrant_points(points: list[dict], qdrant_url: str = "http://localhost:6333", collection: str = "documents") -> None:
    url = qdrant_url.rstrip("/") + f"/collections/{collection}/points/upsert"
    resp = httpx.put(url, json={"points": points}, timeout=60.0)
    resp.raise_for_status()


@app.command()
def main(
    source: Path = typer.Option(Path("data/SAR_docs_text"), help="Directory with SAR .txt files"),
    collection: str = typer.Option("documents", help="Qdrant collection name to upsert into"),
    chunk_size: int = typer.Option(750, help="Chunk size in characters"),
    overlap: int = typer.Option(0, help="Chunk overlap in characters"),
    batch_size: int = typer.Option(16, help="How many chunks to embed per Ollama request"),
    ollama_url: str = typer.Option("http://localhost:18135", help="Ollama endpoint"),
    qdrant_url: str = typer.Option("http://localhost:6333", help="Qdrant REST endpoint"),
):
    """Read all .txt files under `source`, chunk them and index into Qdrant.

    This will create payloads with keys: `text`, `document`, `source`.
    """
    source = source.expanduser()
    if not source.exists():
        typer.echo(f"Source directory not found: {source}")
        raise typer.Exit(code=1)

    txt_files = sorted(source.glob("*.txt"))
    if not txt_files:
        typer.echo(f"No .txt files found under {source}")
        raise typer.Exit(code=0)

    all_chunks: list[tuple[str, str]] = []  # (document_name, chunk_text)
    for p in txt_files:
        text = p.read_text(encoding="utf-8")
        chunks = chunk_text(text, size=chunk_size, overlap=overlap)
        for i, c in enumerate(chunks):
            all_chunks.append((p.name, c))

    typer.echo(f"Prepared {len(all_chunks)} chunks from {len(txt_files)} documents")

    # Embed + upsert in batches
    points_batch: list[dict] = []
    total = len(all_chunks)
    for i in range(0, total, batch_size):
        batch = all_chunks[i : i + batch_size]
        texts = [c for (_, c) in batch]
        try:
            embeddings = ollama_embed(texts, ollama_url=ollama_url)
        except Exception as e:
            typer.echo(f"Embedding request failed: {e}")
            raise

        for j, ((docname, chunk_text_val), emb) in enumerate(zip(batch, embeddings)):
            idx = i + j
            cid = stable_chunk_id(docname, idx)
            payload = {
                "text": chunk_text_val,
                "document": docname,
                "source": "LLM4ACOE_SAR",
            }
            points_batch.append({
                "id": cid,
                "vector": emb,
                "payload": payload,
            })

        # upsert in Qdrant in sub-batches (avoid huge payloads)
        try:
            upsert_qdrant_points(points_batch, qdrant_url=qdrant_url, collection=collection)
        except Exception as e:
            typer.echo(f"Qdrant upsert failed: {e}")
            raise
        points_batch = []
        typer.echo(f"Indexed chunks {i + 1}-{min(i + batch_size, total)} / {total}")
        time.sleep(0.2)

    # Final check: get collection info
    info = httpx.get(qdrant_url.rstrip("/") + f"/collections/{collection}").json()
    pts = info.get("result", {}).get("points_count")
    typer.echo(f"Done. Collection '{collection}' now has ~{pts} points")


if __name__ == "__main__":
    app()

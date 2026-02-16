#!/usr/bin/env python3
"""Index SAR text files into a dedicated Qdrant collection (sar_documents).

Behavior:
- Reads all .txt files under data/SAR_docs_text/
- Splits into fixed-size chunks (chars) matching LLM4ACOE: chunk_size=750, overlap=0
- Uses Ollama embedding endpoint (Settings.semantic_embedding_model) to get vectors
- Creates / recreates Qdrant collection `sar_documents` (COSINE)
- Upserts chunks with payload: {file, chunk_index, source: 'SAR'}

Usage:
    python scripts/index_sar_to_qdrant.py --collection sar_documents
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import time
import uuid
from pathlib import Path
from typing import List

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ontology_hitl.core.config import Settings

CHUNK_SIZE = 750
CHUNK_OVERLAP = 0
DEFAULT_COLLECTION = "sar_documents"


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    chunks = []
    start = 0
    n = len(text)
    step = size - overlap
    while start < n:
        end = min(start + size, n)
        chunks.append(text[start:end])
        start += step
    return chunks


def get_embedding(ollama_url: str, model: str, text: str) -> List[float] | None:
    try:
        resp = httpx.post(
            f"{ollama_url.rstrip('/')}/api/embed",
            json={"model": model, "input": [text]},
            timeout=60.0,
        )
        resp.raise_for_status()
        embs = resp.json().get("embeddings", [])
        if embs:
            return embs[0]
    except Exception as e:
        print("Embedding error:", e)
    return None


def index_files(collection: str, overwrite: bool = True, use_uuids: bool = False) -> None:
    settings = Settings()
    qdrant_url = settings.qdrant_url
    ollama_url = settings.ollama_url
    embed_model = os.getenv("HITL_SEMANTIC_EMBEDDING_MODEL", settings.semantic_embedding_model)

    files = sorted(glob.glob("data/SAR_docs_text/*.txt"))
    if not files:
        print("No SAR text files found in data/SAR_docs_text/")
        return

    # Probe one embedding to determine vector size
    sample_text = open(files[0], "r", encoding="utf-8").read()[:1024]
    sample_emb = get_embedding(ollama_url, embed_model, sample_text)
    if not sample_emb:
        raise RuntimeError("Failed to obtain embedding for sample text; check Ollama embedding endpoint.")
    dim = len(sample_emb)

    client = QdrantClient(url=qdrant_url)

    if overwrite:
        try:
            client.recreate_collection(
                collection_name=collection,
                vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
            )
            print(f"Recreated collection '{collection}' (dim={dim})")
        except Exception as e:
            print("Warning: could not recreate collection:", e)
    else:
        # create if not exists
        try:
            client.get_collection(collection_name=collection)
        except Exception:
            client.recreate_collection(
                collection_name=collection,
                vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
            )
            print(f"Created collection '{collection}' (dim={dim})")

    # ID management
    point_id = 1
    total_points = 0
    batch = []
    BATCH_SIZE = 64

    for fname in files:
        text = open(fname, "r", encoding="utf-8").read()
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            emb = get_embedding(ollama_url, embed_model, chunk)
            if emb is None:
                print(f"Skipping chunk {fname}:{i} (no embedding)")
                continue

            payload = {
                "file": Path(fname).name,
                "chunk_index": i,
                "source": "SAR",
            }

            # choose point id type (UUID string or positive integer)
            if use_uuids:
                pid = str(uuid.uuid4())
            else:
                pid = point_id

            batch.append(qmodels.PointStruct(id=pid, vector=emb, payload=payload))
            if not use_uuids:
                point_id += 1
            total_points += 1

            if len(batch) >= BATCH_SIZE:
                client.upsert(collection_name=collection, points=batch)
                print(f"Upserted {len(batch)} points (last: {fname}:{i})")
                batch = []

    if batch:
        client.upsert(collection_name=collection, points=batch)
        print(f"Upserted final {len(batch)} points")

    print(f"Indexing complete. Total points: {total_points}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index SAR docs into Qdrant collection")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Qdrant collection name")
    parser.add_argument("--no-overwrite", dest="overwrite", action="store_false", help="Don't recreate collection")
    parser.add_argument("--use-uuids", dest="use_uuids", action="store_true", help="Use UUIDs for Qdrant point IDs")
    args = parser.parse_args()

    index_files(args.collection, overwrite=args.overwrite, use_uuids=args.use_uuids)

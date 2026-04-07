"""LLM-based Competency Question generator from Qdrant documents.

Instead of manually defining CQs, this module reads representative
document chunks from Qdrant and asks the LLM to propose competency
questions that the ontology should be able to answer.

This is crucial for **standalone** operation — the OntologyExtender
can bootstrap its own evaluation criteria from the documents without
any prior KGB run.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import structlog

from ontology_hitl.sources.qdrant_source import DocumentChunk, QdrantDocumentSource

logger = structlog.get_logger(__name__)

# CQ difficulty heuristic: questions about single entities = 1-2,
# questions about relations = 3-4, questions requiring inference = 5
_SYSTEM_PROMPT_TEMPLATE = """You are an ontology engineer. Given document excerpts{domain_clause}, generate competency questions (CQs) that a
well-designed ontology should be able to answer.

Each CQ must include:
- id: sequential "CQ_NNN"
- question: a natural language question (German or English)
- cq_type: one of SCQ, VCQ, FCQ, RCQ, MpCQ (Keet & Khan 2024)
- expected_entity_types: list of OWL class names needed to answer it
- expected_relations: list of ObjectProperty names needed
- difficulty: 1-5 (1=simple lookup, 5=multi-hop inference)
- priority: 1 (high) or 2 (normal)

Return a JSON array of CQ objects. Generate 3-5 CQs per batch of text."""

# Backwards-compat alias (domain-agnostic)
SYSTEM_PROMPT = _SYSTEM_PROMPT_TEMPLATE.format(domain_clause="")


class CQGenerator:
    """Generate competency questions from Qdrant document chunks.

    Workflow
    -------
    1. Fetch diverse document chunks from Qdrant (sampling different docs).
    2. Send batches of chunks to the LLM with the CQ generation prompt.
    3. Deduplicate and merge with any existing CQs.
    4. Write to ``data/evaluation/competency_questions.json``.

    Parameters
    ----------
    qdrant_source:
        Initialized ``QdrantDocumentSource`` for fetching chunks.
    ollama_url:
        Ollama endpoint.
    ollama_model:
        Model for CQ generation.
    """

    def __init__(
        self,
        qdrant_source: QdrantDocumentSource | None = None,
        ollama_url: str = "http://localhost:18135",
        ollama_model: str = "gemma4:31b",
        domain_name: str = "",
    ) -> None:
        self.qdrant_source = qdrant_source or QdrantDocumentSource()
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self._domain_name = domain_name
        domain_clause = f" from the {domain_name} domain" if domain_name else ""
        self._system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(domain_clause=domain_clause)

    def generate(
        self,
        num_chunks: int = 30,
        batch_size: int = 5,
        existing_cq_path: str | Path | None = None,
    ) -> list[dict]:
        """Generate CQs from document chunks.

        Args:
            num_chunks: How many chunks to sample from Qdrant.
            batch_size: Chunks per LLM call.
            existing_cq_path: Path to existing CQs (will merge, not overwrite).

        Returns:
            Combined list of CQ dicts (existing + generated).
        """
        logger.info("cq_generation_start", num_chunks=num_chunks)

        # Load existing CQs
        existing: list[dict] = []
        if existing_cq_path:
            path = Path(existing_cq_path)
            if path.exists():
                with open(path) as f:
                    existing = json.load(f)

        existing_questions = {cq.get("question", "").lower() for cq in existing}
        max_id = max(
            (int(cq["id"].split("_")[1]) for cq in existing if "id" in cq),
            default=0,
        )

        # Fetch chunks from Qdrant
        chunks = self.qdrant_source.fetch_chunks(limit=num_chunks)
        if not chunks:
            logger.warning("no_chunks_from_qdrant")
            return existing

        # Sample diverse documents
        chunks = self._sample_diverse(chunks, num_chunks)

        # Generate CQs in batches
        generated: list[dict] = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            batch_cqs = self._generate_batch(batch)
            generated.extend(batch_cqs)

        # Deduplicate against existing
        new_cqs: list[dict] = []
        for cq in generated:
            q = cq.get("question", "").lower()
            if not q or q in existing_questions:
                continue

            # Ensure CQ type is valid; fallback to VCQ for unknown/missing
            if "cq_type" in cq:
                cq_type = str(cq.get("cq_type", "")).strip()
                if cq_type not in {"SCQ", "VCQ", "FCQ", "RCQ", "MpCQ"}:
                    cq_type = "VCQ"
            else:
                cq_type = "VCQ"
            cq["cq_type"] = cq_type

            max_id += 1
            cq["id"] = f"CQ_{max_id:03d}"
            cq["added_in_iteration"] = "auto-generated"
            new_cqs.append(cq)
            existing_questions.add(q)

        combined = existing + new_cqs
        logger.info("cq_generation_done",
                     existing=len(existing), generated=len(new_cqs),
                     total=len(combined))
        return combined

    def generate_and_save(
        self,
        output_path: str | Path = "data/evaluation/competency_questions.json",
        **kwargs,
    ) -> Path:
        """Generate CQs and write to JSON file.

        Args:
            output_path: Where to write the CQ JSON.
            **kwargs: Forwarded to ``generate()``.

        Returns:
            Resolved output path.
        """
        output_path = Path(output_path)
        existing_path = output_path if output_path.exists() else None

        cqs = self.generate(existing_cq_path=existing_path, **kwargs)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(cqs, f, indent=2, ensure_ascii=False)

        logger.info("cqs_saved", path=str(output_path), count=len(cqs))
        return output_path

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _generate_batch(self, chunks: list[DocumentChunk]) -> list[dict]:
        """Send a batch of chunks to the LLM for CQ generation."""
        texts = "\n\n---\n\n".join(
            f"[{c.document_name}]\n{c.text[:800]}" for c in chunks
        )
        prompt = (
            f"Based on these document excerpts, generate competency questions "
            f"that a{' ' + self._domain_name if self._domain_name else 'n'} ontology should answer.\n\n"
            f"{texts}\n\n"
            f"Return a JSON array of CQ objects with: id, question, "
            f"expected_entity_types, expected_relations, difficulty, priority."
        )

        try:
            resp = httpx.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {"role": "system", "content": self._system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.6, "num_predict": 2048},
                },
                timeout=300.0,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed
            return parsed.get("competency_questions", parsed.get("cqs", []))
        except Exception as e:
            logger.warning("cq_batch_failed", error=str(e))
            return []

    @staticmethod
    def _sample_diverse(
        chunks: list[DocumentChunk],
        target: int,
    ) -> list[DocumentChunk]:
        """Sample chunks from as many different documents as possible."""
        from collections import defaultdict
        by_doc: dict[str, list[DocumentChunk]] = defaultdict(list)
        for c in chunks:
            by_doc[c.document_name].append(c)

        sampled: list[DocumentChunk] = []
        # Round-robin across documents
        doc_iters = {doc: iter(cks) for doc, cks in by_doc.items()}
        while len(sampled) < target and doc_iters:
            exhausted = []
            for doc, it in doc_iters.items():
                if len(sampled) >= target:
                    break
                try:
                    sampled.append(next(it))
                except StopIteration:
                    exhausted.append(doc)
            for doc in exhausted:
                del doc_iters[doc]

        return sampled

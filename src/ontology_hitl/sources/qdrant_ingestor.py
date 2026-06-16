"""Per-ontology Qdrant collection manager and knowledge ingestor.

Each ontology extension run (identified by *experiment name* or derived from
the seed ontology path) gets its **own Qdrant collection**.  This ensures:

- The Wine benchmark agent only retrieves Wine-relevant evidence.
- The OEO agent only retrieves energy-domain evidence.
- Web-search snippets gathered during a run are persisted and available
  to later iterations and phases of the same run.

Collection naming
-----------------
Collection names are derived deterministically:

    ``hitl_{slug}``

where *slug* is the experiment name with non-alphanumeric characters
replaced by underscores, lowercased and truncated to 63 chars.  If no
experiment name is set, the seed ontology filename stem is used.

Embedding
---------
Text is embedded via the Ollama ``/api/embed`` endpoint using the
configured ``semantic_embedding_model`` (default ``qwen3-embedding``).
The vector dimension is auto-detected from the first embed call and
stored on the collection.

Usage
-----
Typically called from the loop orchestrator and DomainExpert:

>>> ingestor = QdrantKnowledgeIngestor(settings, experiment_name="wine_v1")
>>> ingestor.ensure_collection()          # idempotent
>>> ingestor.ingest_texts(["Chardonnay is a white-wine grape variety …"])
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Sequence

import httpx
import structlog

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)

_MAX_SLUG_LEN = 63
_PREFIX = "hitl_"


def collection_name_for(experiment_name: str = "", seed_path: str = "") -> str:
    """Return a deterministic Qdrant collection name for this run.

    Priority: *experiment_name* → *seed_path* stem → ``"hitl_default"``.
    """
    raw = experiment_name.strip() or _stem(seed_path) or "default"
    slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    slug = slug[:_MAX_SLUG_LEN - len(_PREFIX)]
    return _PREFIX + slug


def _stem(path: str) -> str:
    """Return the filename stem of *path* without extension."""
    if not path:
        return ""
    import pathlib
    return pathlib.Path(path).stem


class QdrantKnowledgeIngestor:
    """Create and populate a per-ontology Qdrant collection.

    Parameters
    ----------
    settings:
        Application settings (Qdrant URL, Ollama embedding URL/model).
    experiment_name:
        Run identifier (e.g. ``"repro_wine_e4b_no_reasoner"``).  Used to
        derive the collection name.
    seed_path:
        Fallback for collection naming when *experiment_name* is empty.
    timeout:
        Per-HTTP-request timeout in seconds.
    """

    def __init__(
        self,
        settings: Settings,
        experiment_name: str = "",
        seed_path: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.settings = settings
        self.collection = collection_name_for(experiment_name, seed_path or settings.seed_ontology_path)
        self._qdrant = settings.qdrant_url.rstrip("/")
        self._ollama = settings.ollama_url.rstrip("/")
        self._embed_model = settings.semantic_embedding_model
        self._timeout = timeout
        self._vector_size: int | None = None  # discovered on first embed
        self._collection_ready = False
        self.is_new_collection = False  # True when this run created the collection

    # ── Public API ────────────────────────────────────────────────────────────

    def ensure_collection(self) -> bool:
        """Create the Qdrant collection if it doesn't already exist.

        Returns ``True`` if the collection is ready, ``False`` on error.
        """
        if self._collection_ready:
            return True
        try:
            # Check if it already exists
            r = httpx.get(f"{self._qdrant}/collections/{self.collection}", timeout=self._timeout)
            if r.status_code == 200:
                logger.debug("qdrant_collection_exists", collection=self.collection)
                self._collection_ready = True
                # is_new_collection stays False — this collection pre-exists
                return True

            # Need to create — first learn the vector dimension
            size = self._get_vector_size()
            if size is None:
                logger.warning("qdrant_cannot_get_vector_size", collection=self.collection)
                return False

            payload = {
                "vectors": {
                    "size": size,
                    "distance": "Cosine",
                },
            }
            r = httpx.put(
                f"{self._qdrant}/collections/{self.collection}",
                json=payload,
                timeout=self._timeout,
            )
            r.raise_for_status()
            logger.info("qdrant_collection_created", collection=self.collection, vector_size=size)
            self._vector_size = size
            self._collection_ready = True
            self.is_new_collection = True  # freshly created — no docs yet
            return True
        except Exception as exc:
            logger.warning("qdrant_ensure_collection_failed", collection=self.collection, error=str(exc))
            return False

    def ingest_texts(
        self,
        texts: Sequence[str],
        source: str = "web_search",
        extra_payload: dict | None = None,
    ) -> int:
        """Embed *texts* and upsert them into the collection.

        Parameters
        ----------
        texts:
            Plain-text snippets to embed and store.
        source:
            Value stored in the ``source`` payload field (e.g.
            ``"web_search"``, ``"wikipedia"``, ``"pipeline_proposal"``).
        extra_payload:
            Additional key/value pairs merged into every point's payload.

        Returns
        -------
        int
            Number of points successfully upserted.
        """
        if not texts:
            return 0
        if not self.ensure_collection():
            return 0

        points = []
        for text in texts:
            if not text or not text.strip():
                continue
            vec = self._embed(text)
            if vec is None:
                continue
            point_id = str(uuid.UUID(hashlib.md5(text.encode()).hexdigest()))  # deterministic UUID from content
            payload: dict = {
                "text": text,
                "source": source,
                "collection": self.collection,
                **(extra_payload or {}),
            }
            points.append({"id": point_id, "vector": vec, "payload": payload})

        if not points:
            return 0

        try:
            r = httpx.put(
                f"{self._qdrant}/collections/{self.collection}/points",
                json={"points": points},
                timeout=self._timeout * 3,  # batch may take longer
            )
            r.raise_for_status()
            logger.info(
                "qdrant_ingested",
                collection=self.collection,
                source=source,
                count=len(points),
            )
            return len(points)
        except Exception as exc:
            logger.warning("qdrant_ingest_failed", collection=self.collection, error=str(exc))
            return 0

    def ingest_web_results(self, results: list) -> int:
        """Ingest a list of :class:`~ontology_hitl.tools.web_search.WebSearchResult`.

        Stores each snippet with ``source="web_search"`` and records the
        original URL and query in the payload for provenance.
        """
        count = 0
        for r in results:
            snippet = getattr(r, "snippet", "") or ""
            if not snippet:
                continue
            n = self.ingest_texts(
                [snippet],
                source="web_search",
                extra_payload={
                    "url": getattr(r, "source", ""),
                    "title": getattr(r, "title", ""),
                    "query": getattr(r, "query", ""),
                },
            )
            count += n
        return count

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> list[float] | None:
        """Embed *text* via Ollama /api/embed. Returns ``None`` on failure."""
        try:
            r = httpx.post(
                f"{self._ollama}/api/embed",
                json={"model": self._embed_model, "input": text},
                timeout=self._timeout,
            )
            r.raise_for_status()
            data = r.json()
            # Ollama returns {"embeddings": [[...]]} for a single input
            vecs = data.get("embeddings") or data.get("embedding")
            if isinstance(vecs, list) and vecs:
                vec = vecs[0] if isinstance(vecs[0], list) else vecs
                if self._vector_size is None:
                    self._vector_size = len(vec)
                return vec
        except Exception as exc:
            logger.debug("qdrant_embed_failed", error=str(exc))
        return None

    def _get_vector_size(self) -> int | None:
        """Probe the embedding model for its vector dimension."""
        vec = self._embed("dimension probe")
        return len(vec) if vec else None

"""A — Seed Protection Pattern: extension-by-inheritance graph management.

Inspired by Azure Digital Twins DTDL ontology extension pattern and best
practices from the literature (Microsoft, 2024):

- **Never modify the base ontology** — keep it read-only in a ``seed:`` graph.
- Create extension layers via ``rdfs:subClassOf`` inheritance.
- Enable upstream seed updates without breaking custom additions.

Named-graph layout in Fuseki
-----------------------------

.. list-table::
   :header-rows: 1

   * - Graph
     - Purpose
   * - ``urn:graph:seed``
     - Read-only base ontology (imported OWL file)
   * - ``urn:graph:ext-v{N}``
     - Extensions per iteration (all new classes inherit into seed)
   * - ``urn:graph:merged``
     - Union of seed + all accepted extensions (rebuilt on promote)
   * - ``urn:graph:snapshot-{date}``
     - Immutable point-in-time copies for reproducibility
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import structlog
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace, URIRef

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)

# Standard graph IRIs
SEED_GRAPH = "urn:graph:seed"
MERGED_GRAPH = "urn:graph:merged"


def ext_graph_iri(version: int) -> str:
    """Return the named-graph IRI for an extension layer."""
    return f"urn:graph:ext-v{version}"


def snapshot_graph_iri(label: str | None = None) -> str:
    """Return a snapshot graph IRI."""
    tag = label or datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"urn:graph:snapshot-{tag}"


class SeedProtectedOntology:
    """Manage a seed ontology that must never be directly modified.

    All extensions are stored in separate ``ext-v{N}`` named graphs.
    A ``merged`` graph is rebuilt as the union when extensions are
    promoted.

    Parameters
    ----------
    settings:
        Application configuration (Fuseki URL, seed path, etc.).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._seed: Graph = Graph()
        self._extensions: dict[int, Graph] = {}
        self._merged: Graph | None = None

    # ── Seed handling ───────────────────────────────────────────────

    def load_seed(self, path: str | Path | None = None) -> Graph:
        """Load the seed ontology from an OWL file (read-only after this).

        Args:
            path: OWL file path; defaults to ``settings.seed_ontology_path``.

        Returns:
            The loaded seed graph.
        """
        owl_path = Path(path or self.settings.seed_ontology_path)
        self._seed = Graph()
        self._seed.parse(str(owl_path))
        logger.info(
            "seed_loaded",
            path=str(owl_path),
            triples=len(self._seed),
        )
        return self._seed

    @property
    def seed(self) -> Graph:
        """Read-only reference to the seed graph."""
        return self._seed

    def seed_classes(self) -> list[str]:
        """Return URI strings for all OWL classes in the seed."""
        return [
            str(s)
            for s in self._seed.subjects(RDF.type, OWL.Class)
            if isinstance(s, URIRef)
        ]

    def seed_class_labels(self) -> dict[str, str]:
        """Map class URI → rdfs:label in the seed."""
        labels: dict[str, str] = {}
        for uri in self.seed_classes():
            for lbl in self._seed.objects(URIRef(uri), RDFS.label):
                labels[uri] = str(lbl)
                break
            else:
                labels[uri] = uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        return labels

    # ── Extension layers ────────────────────────────────────────────

    def create_extension(self, version: int) -> Graph:
        """Create a new (empty) extension graph for the given iteration.

        New classes should be added to this graph using
        :meth:`add_extension_class`.
        """
        g = Graph()
        self._extensions[version] = g
        logger.info("extension_created", version=version)
        return g

    def add_extension_class(
        self,
        version: int,
        class_uri: str,
        label: str,
        definition: str = "",
        parent_uri: str | None = None,
        disjoint_with: list[str] | None = None,
    ) -> None:
        """Add a new class to an extension layer.

        The class is declared as ``owl:Class`` with an ``rdfs:subClassOf``
        link into the seed (or another extension class).  The seed itself
        is never modified.

        Args:
            version: Extension layer version number.
            class_uri: Full URI for the new class.
            label: Human-readable label.
            definition: ``rdfs:comment`` text.
            parent_uri: Must exist in seed or a prior extension.
            disjoint_with: URIs of classes disjoint with this one.
        """
        g = self._extensions.get(version)
        if g is None:
            g = self.create_extension(version)

        cls = URIRef(class_uri)
        g.add((cls, RDF.type, OWL.Class))
        g.add((cls, RDFS.label, Literal(label)))
        if definition:
            g.add((cls, RDFS.comment, Literal(definition)))
        if parent_uri:
            g.add((cls, RDFS.subClassOf, URIRef(parent_uri)))
        for dw in disjoint_with or []:
            g.add((cls, OWL.disjointWith, URIRef(dw)))

        logger.debug(
            "extension_class_added",
            version=version,
            cls=class_uri,
            parent=parent_uri,
        )

    # ── Merge ───────────────────────────────────────────────────────

    def build_merged(self, up_to_version: int | None = None) -> Graph:
        """Rebuild the merged graph as seed + accepted extensions.

        Args:
            up_to_version: Include extensions up to (inclusive) this
                version.  ``None`` → include all.

        Returns:
            The merged graph.
        """
        merged = Graph()
        # Seed first
        for triple in self._seed:
            merged.add(triple)

        # Extensions in order
        for v in sorted(self._extensions):
            if up_to_version is not None and v > up_to_version:
                break
            for triple in self._extensions[v]:
                merged.add(triple)

        self._merged = merged
        logger.info(
            "merged_graph_built",
            seed_triples=len(self._seed),
            ext_versions=len(self._extensions),
            total_triples=len(merged),
        )
        return merged

    @property
    def merged(self) -> Graph:
        """The latest merged graph (seed + extensions)."""
        if self._merged is None:
            return self.build_merged()
        return self._merged

    # ── Export helpers ───────────────────────────────────────────────

    def export_merged(self, path: str | Path, fmt: str = "xml") -> Path:
        """Serialize the merged graph to a file.

        Args:
            path: Output file path.
            fmt: Serialization format (``xml``, ``turtle``, ``json-ld``).

        Returns:
            The written file path.
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.merged.serialize(str(out), format=fmt)
        logger.info("merged_exported", path=str(out), format=fmt)
        return out

    def export_extension(
        self,
        version: int,
        path: str | Path,
        fmt: str = "turtle",
    ) -> Path:
        """Serialize a single extension layer."""
        g = self._extensions.get(version)
        if g is None:
            raise KeyError(f"No extension layer for version {version}")
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        g.serialize(str(out), format=fmt)
        logger.info("extension_exported", version=version, path=str(out))
        return out

    # ── Validation helpers ──────────────────────────────────────────

    def validate_parent_exists(self, parent_uri: str) -> bool:
        """Check that `parent_uri` exists in seed or any extension."""
        uri = URIRef(parent_uri)
        if (uri, RDF.type, OWL.Class) in self._seed:
            return True
        for g in self._extensions.values():
            if (uri, RDF.type, OWL.Class) in g:
                return True
        return False

    def extension_count(self) -> int:
        """How many extension layers exist."""
        return len(self._extensions)

    def summary(self) -> dict:
        """Return a summary dict of seed + extensions state."""
        return {
            "seed_triples": len(self._seed),
            "seed_classes": len(self.seed_classes()),
            "extension_layers": len(self._extensions),
            "extension_classes": sum(
                sum(1 for _ in g.subjects(RDF.type, OWL.Class))
                for g in self._extensions.values()
            ),
            "merged_triples": len(self._merged) if self._merged else 0,
        }

"""C1.3.3 — OntologyVersionManager: staging/main/snapshot graph management.

Implementation Guide
--------------------
This module manages parallel named graphs in Apache Jena Fuseki:
  - ``kgbuilder``               : main (production) ontology graph
  - ``kgbuilder-staging-v{N}``  : graph under review
  - ``kgbuilder-snapshot-{ts}`` : historical point-in-time copies

All Fuseki graph operations use HTTP:
  - **GET/PUT graph content**: ``{fuseki_url}/{dataset}/data?graph={graph_uri}``
  - **SPARQL Query**: ``{fuseki_url}/{dataset}/sparql`` (POST, ``application/sparql-query``)
  - **SPARQL Update**: ``{fuseki_url}/{dataset}/update`` (POST, ``application/sparql-update``)

Four methods need implementation (marked with TODO):
  1. ``create_version()``             — Create named graph; copy main → staging
  2. ``compute_diff()``               — SPARQL MINUS queries to find diffs
  3. ``promote_staging_to_main()``    — SPARQL COPY graph into main
  4. ``create_snapshot()``            — SPARQL COPY main into dated snapshot

Dependencies:
  - ``httpx``  for HTTP calls to Fuseki

Reference: KGB ``FusekiOntologyService`` in ``src/kgbuilder/storage/ontology.py``
for Fuseki SPARQL patterns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import structlog

from ontology_hitl.core.models import OntologyDiff, OntologyVersion

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SPARQL templates
# ---------------------------------------------------------------------------

# Find all owl:Class subjects in a named graph
_SPARQL_CLASSES_IN_GRAPH = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?class ?label
FROM <{graph_uri}>
WHERE {{
    ?class a owl:Class .
    OPTIONAL {{ ?class rdfs:label ?label }}
}}
"""

# Find all owl:ObjectProperty subjects in a named graph
_SPARQL_RELATIONS_IN_GRAPH = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?prop ?label ?domain ?range
FROM <{graph_uri}>
WHERE {{
    ?prop a owl:ObjectProperty .
    OPTIONAL {{ ?prop rdfs:label ?label }}
    OPTIONAL {{ ?prop rdfs:domain ?domain }}
    OPTIONAL {{ ?prop rdfs:range  ?range  }}
}}
"""

# Classes in graph A but NOT in graph B  (set difference)
_SPARQL_DIFF_CLASSES = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?class
WHERE {{
    GRAPH <{graph_a}> {{ ?class a owl:Class }}
    MINUS {{ GRAPH <{graph_b}> {{ ?class a owl:Class }} }}
}}
"""

# Copy one named graph to another  (SPARQL Update 1.1)
_SPARQL_COPY_GRAPH = "COPY GRAPH <{source}> TO GRAPH <{target}>"


class OntologyVersionManager:
    """Track ontology versions across staging and main graphs.

    Manages parallel graphs in Fuseki:
    - kgbuilder-main: accepted seed + approved extensions
    - kgbuilder-staging-vN: under review
    - kgbuilder-snapshot-<date>: historical snapshots
    """

    def __init__(
        self,
        fuseki_url: str = "http://localhost:3031",
        main_dataset: str = "kgbuilder",
        staging_prefix: str = "kgbuilder-staging",
    ) -> None:
        self.fuseki_url = fuseki_url.rstrip("/")
        self.main_dataset = main_dataset
        self.staging_prefix = staging_prefix
        self._versions: list[OntologyVersion] = []

    # ── Helpers ──────────────────────────────────────────────────────

    def _graph_uri(self, name: str) -> str:
        """Build a named graph URI: ``urn:ontology:{name}``."""
        return f"urn:ontology:{name}"

    def _sparql_query(self, query: str) -> list[dict[str, Any]]:
        """Execute a SPARQL SELECT query and return bindings.

        TODO: Implement this helper.

        Steps:
            1. Build URL: ``f"{self.fuseki_url}/{self.main_dataset}/sparql"``
            2. POST with ``httpx.post(url, content=query,
               headers={"Content-Type": "application/sparql-query",
                         "Accept": "application/sparql-results+json"})``
            3. ``resp.raise_for_status()``
            4. Parse ``resp.json()["results"]["bindings"]``
            5. Return list of dicts: ``[{var: b[var]["value"]} for b in bindings for var in b]``
        """
        raise NotImplementedError("_sparql_query")

    def _sparql_update(self, update: str) -> None:
        """Execute a SPARQL UPDATE command.

        TODO: Implement this helper.

        Steps:
            1. Build URL: ``f"{self.fuseki_url}/{self.main_dataset}/update"``
            2. POST with ``httpx.post(url, content=update,
               headers={"Content-Type": "application/sparql-update"})``
            3. ``resp.raise_for_status()``
        """
        raise NotImplementedError("_sparql_update")

    # ── Public API ───────────────────────────────────────────────────

    def create_version(
        self,
        version_id: str,
        parent_version: str | None = None,
        notes: str = "",
    ) -> OntologyVersion:
        """Create a new ontology version record and staging graph.

        TODO: Implement Fuseki graph creation.

        Steps:
            1. Create ``OntologyVersion(version_id=..., parent_version=..., notes=...)``
            2. Determine staging graph name: ``f"{self.staging_prefix}-{version_id}"``
            3. Determine staging graph URI via ``self._graph_uri(staging_name)``
            4. Determine main graph URI via ``self._graph_uri(self.main_dataset)``
            5. Copy main graph → staging graph to create baseline:
               ``self._sparql_update(_SPARQL_COPY_GRAPH.format(
                   source=main_uri, target=staging_uri))``
               Wrap in try/except; if main graph does not exist yet, log warning and continue.
            6. Append version to ``self._versions``
            7. Log event ``"version_created"``
            8. Return the ``OntologyVersion`` object
        """
        version = OntologyVersion(
            version_id=version_id,
            parent_version=parent_version,
            notes=notes,
        )
        self._versions.append(version)
        logger.info("version_created", version=version_id)
        return version

    def compute_diff(
        self,
        from_version: str,
        to_version: str,
    ) -> OntologyDiff:
        """Compute differences between two ontology versions.

        TODO: Implement SPARQL-based diff.

        Steps:
            1. Build graph URIs for both versions:
               ``from_uri = self._graph_uri(f"{self.staging_prefix}-{from_version}")``
               ``to_uri = self._graph_uri(f"{self.staging_prefix}-{to_version}")``
               If a version equals ``"main"``, use ``self._graph_uri(self.main_dataset)``.
            2. Find added classes (in to but NOT in from):
               ``added = self._sparql_query(_SPARQL_DIFF_CLASSES.format(
                   graph_a=to_uri, graph_b=from_uri))``
               Extract: ``added_classes = [r["class"] for r in added]``
            3. Find removed classes (in from but NOT in to):
               ``removed = self._sparql_query(_SPARQL_DIFF_CLASSES.format(
                   graph_a=from_uri, graph_b=to_uri))``
            4. Build and return ``OntologyDiff(
                   from_version=from_version,
                   to_version=to_version,
                   added_classes=added_classes,
                   removed_classes=removed_classes,
               )``
        """
        logger.info("computing_diff", from_v=from_version, to_v=to_version)
        return OntologyDiff(from_version=from_version, to_version=to_version)

    def promote_staging_to_main(self, version_id: str) -> None:
        """Move a staging graph into the main dataset.

        TODO: Implement graph copy in Fuseki.

        Steps:
            1. Build staging graph URI:
               ``staging_uri = self._graph_uri(f"{self.staging_prefix}-{version_id}")``
            2. Build main graph URI:
               ``main_uri = self._graph_uri(self.main_dataset)``
            3. Create snapshot of current main **before** overwriting:
               ``self.create_snapshot(label=f"pre-promote-{version_id}")``
            4. Execute SPARQL COPY:
               ``self._sparql_update(_SPARQL_COPY_GRAPH.format(
                   source=staging_uri, target=main_uri))``
            5. Log event ``"staging_promoted"``
        """
        logger.info("promoting_to_main", version=version_id)
        raise NotImplementedError("Staging promotion not yet implemented")

    def create_snapshot(self, label: str | None = None) -> str:
        """Create a point-in-time snapshot of the main graph.

        TODO: Implement Fuseki graph snapshot.

        Steps:
            1. Generate snapshot name:
               ``name = label or f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}"``
            2. Build snapshot URI: ``snap_uri = self._graph_uri(name)``
            3. Build main URI: ``main_uri = self._graph_uri(self.main_dataset)``
            4. Execute SPARQL COPY:
               ``self._sparql_update(_SPARQL_COPY_GRAPH.format(
                   source=main_uri, target=snap_uri))``
            5. Log event ``"snapshot_created"``
            6. Return ``name``
        """
        snapshot_name = label or f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        logger.info("creating_snapshot", name=snapshot_name)
        return snapshot_name

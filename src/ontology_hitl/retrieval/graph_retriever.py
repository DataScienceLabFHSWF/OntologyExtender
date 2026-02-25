"""GraphRetriever — KG-only retrieval with entity-centric, subgraph, and path modes.

Adapted from GraphQAAgent ``GraphRetriever``.  Queries Neo4j for structured
evidence, serialises subgraphs as natural language for LLM consumption.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

import structlog

from ontology_hitl.connectors.neo4j import Neo4jConnector
from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import KGEntity, KGRelation
from ontology_hitl.retrieval.kg_entity_linker import KGEntityLinker

logger = structlog.get_logger(__name__)


class GraphMode(Enum):
    """Sub-strategy for graph retrieval."""

    ENTITY_CENTRIC = "entity_centric"
    SUBGRAPH = "subgraph"
    PATH = "path"
    PPR = "ppr"


class GraphRetriever:
    """KG-only retrieval: entity linking → subgraph expansion → serialisation.

    The serialised subgraph is injected into LLM prompts so that both the
    domain expert and the gap analyzer have transparent, auditable KG
    grounding.
    """

    def __init__(
        self,
        neo4j: Neo4jConnector,
        entity_linker: KGEntityLinker,
        settings: Settings,
    ) -> None:
        self._neo4j = neo4j
        self._linker = entity_linker
        self._settings = settings

    # -- public API ---------------------------------------------------------

    async def retrieve(
        self,
        terms: list[str],
        *,
        mode: GraphMode | None = None,
    ) -> dict[str, Any]:
        """Retrieve graph evidence for the given terms.

        Returns a dict with:
          - ``text``:      Natural-language subgraph serialisation
          - ``entities``:  List of :class:`KGEntity`
          - ``relations``: List of :class:`KGRelation`
          - ``mode``:      The retrieval mode used
          - ``latency_ms``: Retrieval latency
        """
        if mode is None:
            mode = GraphMode.SUBGRAPH if len(terms) <= 3 else GraphMode.PPR

        t0 = time.perf_counter()

        # 1. Entity-link terms to KG nodes
        linked = await self._linker.link(terms)
        if not linked:
            logger.warning("graph.no_entities_linked", terms=terms[:5])
            return {"text": "", "entities": [], "relations": [], "mode": mode.value, "latency_ms": 0}

        entity_ids = [e.id for e in linked]

        # 2. Dispatch to sub-strategy
        if mode == GraphMode.PATH and len(entity_ids) >= 2:
            entities, relations = await self._path_retrieve(entity_ids)
        elif mode == GraphMode.PPR:
            entities, relations = await self._ppr_retrieve(entity_ids)
        elif mode == GraphMode.SUBGRAPH:
            entities, relations = await self._subgraph_retrieve(entity_ids)
        else:
            entities, relations = await self._entity_centric_retrieve(entity_ids)

        text = self.serialise_subgraph(entities, relations)
        elapsed = (time.perf_counter() - t0) * 1000

        logger.info(
            "graph.retrieve", mode=mode.value,
            linked=len(linked), entities=len(entities),
            relations=len(relations), latency_ms=round(elapsed, 1),
        )
        return {
            "text": text,
            "entities": entities,
            "relations": relations,
            "mode": mode.value,
            "latency_ms": round(elapsed, 1),
        }

    # -- sub-strategies -----------------------------------------------------

    async def _entity_centric_retrieve(
        self, entity_ids: list[str],
    ) -> tuple[list[KGEntity], list[KGRelation]]:
        return await self._neo4j.get_neighbourhood(
            entity_ids, max_hops=1,
            max_nodes=self._settings.graph_max_nodes,
        )

    async def _subgraph_retrieve(
        self, entity_ids: list[str],
    ) -> tuple[list[KGEntity], list[KGRelation]]:
        return await self._neo4j.get_neighbourhood(
            entity_ids,
            max_hops=self._settings.graph_max_hops,
            max_nodes=self._settings.graph_max_nodes,
        )

    async def _path_retrieve(
        self, entity_ids: list[str],
    ) -> tuple[list[KGEntity], list[KGRelation]]:
        all_entities: dict[str, KGEntity] = {}
        all_relations: list[KGRelation] = []
        source_id = entity_ids[0]
        for target_id in entity_ids[1:]:
            paths = await self._neo4j.find_shortest_paths(
                source_id, target_id,
                max_hops=self._settings.graph_max_hops,
            )
            for path_ents, path_rels in paths:
                for e in path_ents:
                    all_entities[e.id] = e
                all_relations.extend(path_rels)
        return list(all_entities.values()), all_relations

    async def _ppr_retrieve(
        self, entity_ids: list[str],
    ) -> tuple[list[KGEntity], list[KGRelation]]:
        """PPR-based focused subgraph (HippoRAG-inspired)."""
        ppr_results = await self._neo4j.compute_ppr(
            entity_ids,
            damping=self._settings.ppr_damping,
            top_k=self._settings.ppr_top_k,
        )
        ppr_ids = [e.id for e, _ in ppr_results]
        if not ppr_ids:
            return [], []
        # Get the subgraph connecting the PPR-ranked nodes
        return await self._neo4j.get_subgraph_between(
            ppr_ids, max_hops=self._settings.graph_max_hops,
        )

    # -- serialisation ------------------------------------------------------

    @staticmethod
    def serialise_subgraph(
        entities: list[KGEntity],
        relations: list[KGRelation],
    ) -> str:
        """Render subgraph as structured natural-language text for LLM consumption."""
        if not entities and not relations:
            return ""
        lines: list[str] = ["=== Knowledge Graph Evidence ===", "", "Entities:"]
        for e in entities:
            desc = f" — {e.description}" if e.description else ""
            lines.append(f'  - "{e.label}" ({e.entity_type}, conf={e.confidence:.2f}){desc}')
        lines.append("")
        lines.append("Relations:")
        for r in relations:
            lines.append(
                f'  - "{r.source_id}" --[{r.relation_type}]--> "{r.target_id}" '
                f"(conf={r.confidence:.2f})"
            )
        lines.append("")
        return "\n".join(lines)

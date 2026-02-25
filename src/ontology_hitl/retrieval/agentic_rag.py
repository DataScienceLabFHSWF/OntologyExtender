"""AgenticGraphRAG — ReAct agent that orchestrates all retrieval tools.

Ported from GraphQAAgent.  Uses an LLM agent with tool-calling to
dynamically decide:
- When to search vectors (semantic similarity over document chunks)
- When to generate and run Cypher (structured graph queries)
- When to explore multi-hop neighborhoods (entity-centric traversal)
- When to find connections between entities (shortest-path fact chains)
- When to consult the ontology (what types/relations exist)
- When it has enough context to stop

The agent is ontology-informed: the full TBox schema is injected into its
system prompt so it understands what classes, properties, and hierarchies
exist in the knowledge graph.

Implements the same ``retrieve(query)`` protocol as the other retrievers.
"""

from __future__ import annotations

import json
import asyncio
import structlog
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from ontology_hitl.connectors.neo4j import Neo4jConnector
from ontology_hitl.connectors.ollama import OllamaConnector
from ontology_hitl.connectors.qdrant import QdrantConnector
from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import (
    KGEntity,
    KGRelation,
    Provenance,
    QAQuery,
    RetrievalSource,
    RetrievedContext,
)
from ontology_hitl.retrieval.ontology_context import OntologyContext

logger = structlog.get_logger(__name__)

_MAX_ITERATIONS = 8
_MAX_CONTEXTS = 25

# Default system prompt when no domain-specific template is available
_DEFAULT_SYSTEM_PROMPT = """\
You are an intelligent retrieval agent for a knowledge graph.
You have access to tools that let you search vectors, run Cypher queries,
explore entity neighborhoods, find connections between entities, and look
up ontology information.

Use these tools strategically to gather evidence that answers the user's
question.  When you have enough evidence, call collect_evidence.

ONTOLOGY SCHEMA:
{ontology_summary}

NEO4J SCHEMA:
{neo4j_schema}

Rules:
- Always try multiple retrieval strategies for complex questions.
- For questions about relationships, use find_connections.
- For general questions, start with search_vectors.
- Call collect_evidence when you have sufficient evidence.
"""


class AgenticGraphRAG:
    """ReAct agent combining all retrieval strategies with 6 tools.

    Tools:
    - ``search_vectors``: Semantic search over document chunks
    - ``query_graph``: Run Cypher queries against Neo4j
    - ``explore_entity``: Multi-hop neighborhood expansion
    - ``find_connections``: Shortest-path fact chains between entities
    - ``lookup_ontology``: Check available types, relations, hierarchy
    - ``collect_evidence``: Finalize collected evidence (signals done)
    """

    def __init__(
        self,
        neo4j: Neo4jConnector,
        qdrant: QdrantConnector,
        ollama: OllamaConnector,
        ontology_context: OntologyContext,
        settings: Settings,
    ) -> None:
        self._neo4j = neo4j
        self._qdrant = qdrant
        self._ollama = ollama
        self._ontology = ontology_context
        self._settings = settings
        self._neo4j_graph = None  # lazy-loaded Neo4jGraph for schema

    def _get_neo4j_schema(self) -> str:
        """Get the Neo4j schema string (lazy-loaded)."""
        if self._neo4j_graph is None:
            try:
                from langchain_neo4j import Neo4jGraph

                self._neo4j_graph = Neo4jGraph(
                    url=self._settings.neo4j_uri,
                    username=self._settings.neo4j_username,
                    password=self._settings.neo4j_password,
                    database=self._settings.neo4j_database,
                    enhanced_schema=False,
                )
            except Exception as exc:
                logger.warning("agentic.neo4j_schema_failed", error=str(exc))
                return "(schema unavailable)"
        return self._neo4j_graph.schema[:4000]

    # -- Retriever protocol -------------------------------------------------

    async def retrieve(self, query: QAQuery) -> list[RetrievedContext]:
        """Run the agentic retrieval loop."""
        llm = self._ollama.get_chat_model()

        tools = self._build_tools()
        tool_map = {t.name: t for t in tools}

        # Bind tools to LLM
        try:
            llm_with_tools = llm.bind_tools(tools)
        except Exception as exc:
            logger.warning("agentic.bind_tools_failed", error=str(exc))
            return await self._fallback_retrieve(query)

        # System prompt with ontology + schema
        neo4j_schema = self._get_neo4j_schema()
        system = SystemMessage(
            content=_DEFAULT_SYSTEM_PROMPT.format(
                ontology_summary=self._ontology.schema_summary[:3000],
                neo4j_schema=neo4j_schema,
            )
        )
        human = HumanMessage(content=query.raw_question)

        messages = [system, human]
        collected_contexts: list[RetrievedContext] = []
        collected_entities: list[KGEntity] = []
        collected_relations: list[KGRelation] = []
        fact_chains: list[dict[str, Any]] = []

        for iteration in range(1, _MAX_ITERATIONS + 1):
            logger.info("agentic.iteration", iteration=iteration)

            try:
                response = await llm_with_tools.ainvoke(messages)
            except Exception as exc:
                logger.warning(
                    "agentic.llm_error", error=str(exc), iteration=iteration
                )
                break

            messages.append(response)

            if not response.tool_calls:
                logger.info("agentic.no_tool_calls", iteration=iteration)
                break

            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id = tc.get("id", tool_name)

                logger.info(
                    "agentic.tool_call",
                    tool=tool_name,
                    args_keys=list(tool_args.keys()),
                )

                if tool_name == "collect_evidence":
                    summary = tool_args.get("summary", "")
                    logger.info(
                        "agentic.done",
                        summary=summary[:100],
                        contexts=len(collected_contexts),
                    )
                    messages.append(
                        ToolMessage(
                            content="Evidence collected.", tool_call_id=tool_id
                        )
                    )
                    return self._finalize(
                        collected_contexts,
                        collected_entities,
                        collected_relations,
                        fact_chains,
                    )

                if tool_name in tool_map:
                    try:
                        result = await tool_map[tool_name].ainvoke(tool_args)
                        result_str = (
                            result
                            if isinstance(result, str)
                            else json.dumps(result, default=str)
                        )

                        new_ctxs, new_ents, new_rels, new_chains = (
                            self._parse_tool_result(tool_name, tool_args, result_str)
                        )
                        collected_contexts.extend(new_ctxs)
                        collected_entities.extend(new_ents)
                        collected_relations.extend(new_rels)
                        fact_chains.extend(new_chains)

                        messages.append(
                            ToolMessage(
                                content=result_str[:3000], tool_call_id=tool_id
                            )
                        )
                    except Exception as exc:
                        logger.warning(
                            "agentic.tool_error",
                            tool=tool_name,
                            error=str(exc),
                        )
                        messages.append(
                            ToolMessage(
                                content=f"Error: {str(exc)[:200]}",
                                tool_call_id=tool_id,
                            )
                        )
                else:
                    messages.append(
                        ToolMessage(
                            content=f"Unknown tool: {tool_name}",
                            tool_call_id=tool_id,
                        )
                    )

            if len(collected_contexts) >= _MAX_CONTEXTS:
                logger.info(
                    "agentic.max_contexts_reached",
                    contexts=len(collected_contexts),
                )
                break

        return self._finalize(
            collected_contexts, collected_entities, collected_relations, fact_chains
        )

    # -- Tool definitions ---------------------------------------------------

    def _build_tools(self) -> list:
        """Build LangChain tools that close over this instance's connectors."""

        neo4j = self._neo4j
        qdrant = self._qdrant
        ollama = self._ollama
        ontology = self._ontology
        settings = self._settings

        @tool
        async def search_vectors(query: str) -> str:
            """Search document chunks by semantic similarity. Returns text snippets.
            Use this for general questions, finding relevant documents, or when
            you need background context. Input: the search query string."""
            try:
                embedding = await ollama.embed(query)
                if not embedding:
                    return "Embedding failed."
                results = await qdrant.search(query_vector=embedding, top_k=5)
                if not results:
                    return "No vector results found."
                lines = []
                for chunk, score in results:
                    lines.append(f"[score={score:.3f}] {chunk.content[:300]}")
                return "\n---\n".join(lines)
            except Exception as e:
                return f"Vector search error: {e}"

        @tool
        async def query_graph(cypher: str) -> str:
            """Execute a Cypher query against the Neo4j knowledge graph.
            Returns the query results as JSON. Write valid Cypher.
            Always LIMIT to at most 25 rows.
            Input: a valid Cypher query string."""
            try:
                from neo4j import AsyncGraphDatabase

                driver = AsyncGraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_username, settings.neo4j_password),
                )
                async with driver.session(database=settings.neo4j_database) as session:
                    result = await session.run(cypher)
                    records = [dict(r) async for r in result]
                await driver.close()

                if not records:
                    return "Query returned 0 rows."

                lines = []
                for rec in records[:25]:
                    row = {}
                    for k, v in rec.items():
                        if hasattr(v, "items"):
                            row[k] = dict(v)
                        else:
                            row[k] = v
                    lines.append(json.dumps(row, default=str, ensure_ascii=False))
                return f"{len(records)} rows:\n" + "\n".join(lines)
            except Exception as e:
                return f"Cypher error: {e}"

        @tool
        async def explore_entity(entity_id: str, max_hops: int = 1) -> str:
            """Explore the neighborhood of a specific entity in the knowledge graph.
            Returns connected entities and relationships as structured JSON.
            Input: entity_id, max_hops (1-3)."""
            try:
                hops = min(max(max_hops, 1), 3)
                entities, relations = await neo4j.get_neighbourhood(
                    [entity_id], max_hops=hops, max_nodes=30
                )
                if not entities and not relations:
                    found = await neo4j.find_entities_by_label(
                        [entity_id], limit=3
                    )
                    if found:
                        entities, relations = await neo4j.get_neighbourhood(
                            [f.id for f in found], max_hops=hops, max_nodes=30
                        )
                        if not entities:
                            entities = found

                if not entities and not relations:
                    return json.dumps(
                        {"error": f"No data found for '{entity_id}'."}
                    )

                result = {
                    "entity_id": entity_id,
                    "hops": hops,
                    "entities": [
                        {"id": e.id, "label": e.label[:80], "type": e.entity_type}
                        for e in entities[:20]
                    ],
                    "relations": [
                        {
                            "src": r.source_id,
                            "type": r.relation_type,
                            "tgt": r.target_id,
                        }
                        for r in relations[:30]
                    ],
                }
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"Explore error: {e}"})

        @tool
        async def find_connections(
            source_id: str, target_id: str, max_hops: int = 4
        ) -> str:
            """Find shortest paths between two entities in the knowledge graph.
            Returns fact chains: verifiable entity-relation-entity triples.
            Input: source_id and target_id (entity IDs), max_hops (1-6)."""
            try:
                hops = min(max(max_hops, 1), 6)
                paths = await neo4j.find_shortest_paths(
                    source_id, target_id, max_hops=hops
                )
                if not paths:
                    src_found = await neo4j.find_entities_by_label(
                        [source_id], limit=1
                    )
                    tgt_found = await neo4j.find_entities_by_label(
                        [target_id], limit=1
                    )
                    if src_found and tgt_found:
                        paths = await neo4j.find_shortest_paths(
                            src_found[0].id, tgt_found[0].id, max_hops=hops
                        )

                if not paths:
                    return json.dumps(
                        {
                            "source": source_id,
                            "target": target_id,
                            "paths": [],
                            "message": "No paths found between these entities.",
                        }
                    )

                result_paths = []
                for path_ents, path_rels in paths:
                    chain_steps = []
                    for rel in path_rels:
                        chain_steps.append(
                            f"{rel.source_id} -[{rel.relation_type}]-> {rel.target_id}"
                        )
                    result_paths.append(
                        {
                            "nodes": [e.id for e in path_ents],
                            "node_labels": {
                                e.id: e.label[:60] for e in path_ents
                            },
                            "edges": [
                                {
                                    "src": r.source_id,
                                    "type": r.relation_type,
                                    "tgt": r.target_id,
                                }
                                for r in path_rels
                            ],
                            "chain": " → ".join(chain_steps)
                            if chain_steps
                            else "direct",
                        }
                    )

                return json.dumps(
                    {"source": source_id, "target": target_id, "paths": result_paths},
                    ensure_ascii=False,
                )
            except Exception as e:
                return json.dumps({"error": f"Path finding error: {e}"})

        @tool
        async def lookup_ontology(
            class_name: str = "", relation_name: str = ""
        ) -> str:
            """Look up ontology information about classes and relations.
            Input: class_name and/or relation_name."""
            lines = []
            if class_name and class_name in ontology.classes:
                cls = ontology.classes[class_name]
                lines.append(f"Class: {cls.name}")
                if cls.parent:
                    lines.append(f"  Parent: {cls.parent}")
                if cls.children:
                    lines.append(
                        f"  Subclasses: {', '.join(cls.children)}"
                    )
                if cls.properties_as_domain:
                    lines.append(
                        f"  Outgoing relations: {', '.join(cls.properties_as_domain)}"
                    )
                if cls.properties_as_range:
                    lines.append(
                        f"  Incoming relations: {', '.join(cls.properties_as_range)}"
                    )
                related = ontology.get_related_types(class_name)
                if related:
                    lines.append(
                        f"  Connected types: {', '.join(related)}"
                    )
            elif class_name:
                lines.append(f"Class '{class_name}' not in ontology.")
                lines.append(
                    f"Available: {', '.join(sorted(ontology.classes.keys()))}"
                )

            if relation_name and relation_name in ontology.properties:
                prop = ontology.properties[relation_name]
                lines.append(f"Relation: {prop.name} ({prop.prop_type})")
                lines.append(f"  Domain: {prop.domain} -> Range: {prop.range}")
            elif relation_name:
                lines.append(f"Relation '{relation_name}' not in ontology.")
                lines.append(
                    f"Available: {', '.join(sorted(ontology.properties.keys()))}"
                )

            if not class_name and not relation_name:
                lines.append(
                    f"Classes ({len(ontology.classes)}): "
                    f"{', '.join(sorted(ontology.classes.keys()))}"
                )
                lines.append(
                    f"Relations ({len(ontology.properties)}): "
                    f"{', '.join(sorted(ontology.properties.keys()))}"
                )

            return "\n".join(lines) if lines else "No ontology info found."

        @tool
        async def collect_evidence(summary: str) -> str:
            """Call this when you have gathered enough evidence to answer.
            Input: a brief summary of what evidence was collected."""
            return "Evidence collection complete."

        return [
            search_vectors,
            query_graph,
            explore_entity,
            find_connections,
            lookup_ontology,
            collect_evidence,
        ]

    # -- Result parsing and finalization ------------------------------------

    def _parse_tool_result(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        result_str: str,
    ) -> tuple[
        list[RetrievedContext], list[KGEntity], list[KGRelation], list[dict[str, Any]]
    ]:
        if tool_name == "search_vectors":
            return self._parse_vector_result(result_str)
        elif tool_name == "query_graph":
            return self._parse_cypher_result(tool_args, result_str)
        elif tool_name == "explore_entity":
            return self._parse_explore_result(tool_args, result_str)
        elif tool_name == "find_connections":
            return self._parse_path_result(result_str)
        elif tool_name == "lookup_ontology":
            return self._parse_ontology_result(result_str)
        return [], [], [], []

    def _parse_vector_result(
        self,
        result_str: str,
    ) -> tuple[
        list[RetrievedContext], list[KGEntity], list[KGRelation], list[dict[str, Any]]
    ]:
        contexts: list[RetrievedContext] = []
        chunks = result_str.split("\n---\n")
        for i, chunk in enumerate(chunks):
            if chunk.startswith("No vector") or chunk.startswith("Vector search error"):
                continue
            contexts.append(
                RetrievedContext(
                    source=RetrievalSource.VECTOR,
                    text=chunk,
                    score=0.9 - (i * 0.05),
                    provenance=Provenance(
                        retrieval_strategy="agentic_vector",
                        retrieval_score=0.9 - (i * 0.05),
                    ),
                )
            )
        return contexts, [], [], []

    def _parse_cypher_result(
        self,
        tool_args: dict[str, Any],
        result_str: str,
    ) -> tuple[
        list[RetrievedContext], list[KGEntity], list[KGRelation], list[dict[str, Any]]
    ]:
        contexts: list[RetrievedContext] = []
        entities: list[KGEntity] = []

        if "rows:" not in result_str:
            return contexts, entities, [], []

        lines = result_str.split("\n")[1:]
        for i, line in enumerate(lines):
            try:
                row = json.loads(line)
                eid = row.get("id", row.get("n.id", row.get("e.id", "")))
                elabel = row.get(
                    "label", row.get("n.label", row.get("e.label", str(row)[:100]))
                )
                etype = row.get(
                    "type", row.get("n.node_type", row.get("node_type", ""))
                )

                if eid:
                    entities.append(
                        KGEntity(
                            id=str(eid),
                            label=str(elabel),
                            entity_type=str(etype),
                            confidence=1.0,
                        )
                    )

                contexts.append(
                    RetrievedContext(
                        source=RetrievalSource.GRAPH,
                        text=f"{elabel} [{etype}]" if elabel else line[:200],
                        score=1.0 - (i * 0.02),
                        provenance=Provenance(
                            entity_ids=[str(eid)] if eid else [],
                            retrieval_strategy="agentic_cypher",
                            retrieval_score=1.0 - (i * 0.02),
                        ),
                    )
                )
            except json.JSONDecodeError:
                contexts.append(
                    RetrievedContext(
                        source=RetrievalSource.GRAPH,
                        text=line[:300],
                        score=0.5,
                        provenance=Provenance(
                            retrieval_strategy="agentic_cypher",
                            retrieval_score=0.5,
                        ),
                    )
                )
        return contexts, entities, [], []

    def _parse_explore_result(
        self,
        tool_args: dict[str, Any],
        result_str: str,
    ) -> tuple[
        list[RetrievedContext], list[KGEntity], list[KGRelation], list[dict[str, Any]]
    ]:
        contexts: list[RetrievedContext] = []
        entities: list[KGEntity] = []
        relations: list[KGRelation] = []
        entity_id = tool_args.get("entity_id", "")

        try:
            data = json.loads(result_str)
        except json.JSONDecodeError:
            if "error" not in result_str.lower():
                contexts.append(
                    RetrievedContext(
                        source=RetrievalSource.GRAPH,
                        text=result_str[:500],
                        score=0.6,
                        provenance=Provenance(
                            entity_ids=[entity_id] if entity_id else [],
                            retrieval_strategy="agentic_explore",
                            retrieval_score=0.6,
                        ),
                    )
                )
            return contexts, entities, relations, []

        if "error" in data:
            return contexts, entities, relations, []

        for ent_dict in data.get("entities", []):
            eid = ent_dict.get("id", "")
            if eid:
                entities.append(
                    KGEntity(
                        id=eid,
                        label=ent_dict.get("label", ""),
                        entity_type=ent_dict.get("type", ""),
                        confidence=0.9,
                    )
                )

        for rel_dict in data.get("relations", []):
            src = rel_dict.get("src", "")
            tgt = rel_dict.get("tgt", "")
            rtype = rel_dict.get("type", "")
            if src and tgt and rtype:
                relations.append(
                    KGRelation(
                        source_id=src,
                        target_id=tgt,
                        relation_type=rtype,
                        confidence=0.9,
                    )
                )

        text_lines = [
            f"Neighborhood of '{entity_id}' ({data.get('hops', 1)}-hop):"
        ]
        text_lines.append(f"Entities ({len(entities)}):")
        for e in entities[:15]:
            text_lines.append(f"  [{e.entity_type}] {e.id}: {e.label}")
        text_lines.append(f"Relations ({len(relations)}):")
        for r in relations[:20]:
            text_lines.append(
                f"  {r.source_id} -[{r.relation_type}]-> {r.target_id}"
            )

        contexts.append(
            RetrievedContext(
                source=RetrievalSource.GRAPH,
                text="\n".join(text_lines),
                score=0.85,
                subgraph=[*entities[:30], *relations[:50]],
                provenance=Provenance(
                    entity_ids=[entity_id] + [e.id for e in entities[:10]],
                    retrieval_strategy="agentic_explore",
                    retrieval_score=0.85,
                ),
            )
        )

        return contexts, entities, relations, []

    def _parse_path_result(
        self,
        result_str: str,
    ) -> tuple[
        list[RetrievedContext], list[KGEntity], list[KGRelation], list[dict[str, Any]]
    ]:
        contexts: list[RetrievedContext] = []
        entities: list[KGEntity] = []
        relations: list[KGRelation] = []
        chains: list[dict[str, Any]] = []

        try:
            data = json.loads(result_str)
        except json.JSONDecodeError:
            return contexts, entities, relations, chains

        if "error" in data:
            return contexts, entities, relations, chains

        source = data.get("source", "")
        target = data.get("target", "")
        paths = data.get("paths", [])

        if not paths:
            return contexts, entities, relations, chains

        for path_idx, path in enumerate(paths):
            node_ids = path.get("nodes", [])
            node_labels = path.get("node_labels", {})
            edges = path.get("edges", [])
            chain_str = path.get("chain", "")

            for nid in node_ids:
                lbl = node_labels.get(nid, nid)
                entities.append(
                    KGEntity(id=nid, label=lbl, entity_type="", confidence=0.95)
                )

            for edge in edges:
                src = edge.get("src", "")
                tgt = edge.get("tgt", "")
                rtype = edge.get("type", "")
                if src and tgt and rtype:
                    relations.append(
                        KGRelation(
                            source_id=src,
                            target_id=tgt,
                            relation_type=rtype,
                            confidence=0.95,
                        )
                    )

            chain = {
                "source": source,
                "target": target,
                "path_index": path_idx,
                "node_ids": node_ids,
                "node_labels": node_labels,
                "edges": edges,
                "chain_text": chain_str,
            }
            chains.append(chain)

            chain_text = f"FACT CHAIN ({source} -> {target}, path {path_idx + 1}):\n"
            chain_text += f"  {chain_str}\n"
            chain_text += f"  Nodes: {', '.join(f'{nid} ({node_labels.get(nid, nid)})' for nid in node_ids)}\n"
            for edge in edges:
                chain_text += f"  TRIPLE: [{edge.get('src')}] -[{edge.get('type')}]-> [{edge.get('tgt')}]\n"

            contexts.append(
                RetrievedContext(
                    source=RetrievalSource.GRAPH,
                    text=chain_text,
                    score=0.95 - (path_idx * 0.02),
                    subgraph=[*entities, *relations],
                    provenance=Provenance(
                        entity_ids=node_ids,
                        retrieval_strategy="agentic_fact_chain",
                        retrieval_score=0.95,
                    ),
                )
            )

        return contexts, entities, relations, chains

    def _parse_ontology_result(
        self,
        result_str: str,
    ) -> tuple[
        list[RetrievedContext], list[KGEntity], list[KGRelation], list[dict[str, Any]]
    ]:
        contexts: list[RetrievedContext] = []
        if not result_str.startswith("No ontology"):
            contexts.append(
                RetrievedContext(
                    source=RetrievalSource.ONTOLOGY,
                    text=result_str,
                    score=0.3,
                    provenance=Provenance(
                        retrieval_strategy="agentic_ontology",
                        retrieval_score=0.3,
                    ),
                )
            )
        return contexts, [], [], []

    def _finalize(
        self,
        contexts: list[RetrievedContext],
        entities: list[KGEntity],
        relations: list[KGRelation],
        fact_chains: list[dict[str, Any]] | None = None,
    ) -> list[RetrievedContext]:
        """Deduplicate, sort, and attach subgraph + fact chains to contexts."""
        fact_chains = fact_chains or []

        # Inject a graph reasoning summary if we have fact chains
        if fact_chains:
            summary_lines = [
                "GRAPH REASONING — Verified fact chains from knowledge graph:"
            ]
            for i, chain in enumerate(fact_chains, 1):
                summary_lines.append(
                    f"\n  Chain {i}: {chain.get('source', '?')} -> {chain.get('target', '?')}"
                )
                summary_lines.append(
                    f"    Path: {chain.get('chain_text', 'n/a')}"
                )
                for edge in chain.get("edges", []):
                    summary_lines.append(
                        f"    GROUNDED TRIPLE: [{edge.get('src')}] "
                        f"-[{edge.get('type')}]-> [{edge.get('tgt')}]"
                    )
                node_labels = chain.get("node_labels", {})
                if node_labels:
                    label_parts = [f"{k}={v}" for k, v in node_labels.items()]
                    summary_lines.append(
                        f"    Labels: {', '.join(label_parts)}"
                    )

            all_chain_ids: list[str] = []
            for c in fact_chains:
                all_chain_ids.extend(c.get("node_ids", []))

            contexts.append(
                RetrievedContext(
                    source=RetrievalSource.GRAPH,
                    text="\n".join(summary_lines),
                    score=0.98,
                    provenance=Provenance(
                        entity_ids=list(set(all_chain_ids)),
                        retrieval_strategy="agentic_graph_reasoning",
                        retrieval_score=0.98,
                    ),
                )
            )

        # Deduplicate by text prefix
        seen: set[str] = set()
        unique: list[RetrievedContext] = []
        for ctx in contexts:
            key = ctx.text[:150]
            if key not in seen:
                seen.add(key)
                unique.append(ctx)

        unique.sort(key=lambda c: c.score, reverse=True)

        # Deduplicate entities
        seen_ids: set[str] = set()
        unique_ents: list[KGEntity] = []
        for e in entities:
            if e.id and e.id not in seen_ids:
                seen_ids.add(e.id)
                unique_ents.append(e)

        # Attach full subgraph to top context
        if unique and (unique_ents or relations):
            unique[0].subgraph = [*unique_ents[:50], *relations[:80]]

        for ctx in unique:
            ctx.source = RetrievalSource.HYBRID

        logger.info(
            "agentic.finalized",
            total_contexts=len(unique),
            entities=len(unique_ents),
            relations=len(relations),
            fact_chains=len(fact_chains),
        )
        return unique[:_MAX_CONTEXTS]

    # -- Fallback -----------------------------------------------------------

    async def _fallback_retrieve(
        self, query: QAQuery
    ) -> list[RetrievedContext]:
        """Simple parallel vector+cypher fallback when agent can't bind tools."""
        from ontology_hitl.retrieval.vector import VectorRetriever
        from ontology_hitl.retrieval.cypher import CypherRetriever

        logger.info("agentic.fallback", reason="tool binding failed")

        vector = VectorRetriever(self._qdrant, self._ollama, self._settings)
        cypher_r = CypherRetriever(self._settings, self._ollama)

        vector_task = asyncio.create_task(vector.retrieve(query))
        cypher_task = asyncio.create_task(cypher_r.retrieve(query))

        vector_ctx = await vector_task
        cypher_ctx = await cypher_task

        combined = cypher_ctx + vector_ctx
        for ctx in combined:
            ctx.source = RetrievalSource.HYBRID
        return combined[:_MAX_CONTEXTS]

"""Cypher-based retriever — LLM-to-Cypher via LangChain GraphCypherQAChain.

Ported from GraphQAAgent.  Translates natural-language questions into Cypher
via an LLM, executes them against Neo4j, and converts the rows back into
:class:`RetrievedContext` objects.
"""

from __future__ import annotations

import json
import structlog
from typing import Any

from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.prompts import PromptTemplate

from ontology_hitl.connectors.ollama import OllamaConnector
from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import (
    KGEntity,
    KGRelation,
    Provenance,
    QAQuery,
    RetrievalSource,
    RetrievedContext,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Default prompt templates
# ---------------------------------------------------------------------------

_DEFAULT_CYPHER_GENERATION_TEMPLATE = """\
You are a Neo4j Cypher expert for a knowledge graph.
Generate ONLY valid Cypher. No explanation, no markdown fences.

Schema:
{schema}

{ontology_section}

Rules:
- Always LIMIT results to at most 25 rows.
- Prefer returning id, label, and properties over returning full nodes.

Question: {question}

Cypher:"""

_DEFAULT_QA_GENERATION_TEMPLATE = """\
You are a helpful assistant.
Use ONLY the following context from a Neo4j knowledge graph to answer.
If the context is empty or insufficient, say you don't have enough information.
Answer in the same language as the question.

Context from knowledge graph:
{context}

Question: {question}

Answer:"""


class CypherRetriever:
    """LLM-to-Cypher retriever using LangChain ``GraphCypherQAChain``.

    Lazily initialises the chain on first use.
    """

    def __init__(
        self,
        settings: Settings,
        ollama: OllamaConnector,
        *,
        ontology_context: Any | None = None,
    ) -> None:
        self._settings = settings
        self._ollama = ollama
        self._ontology = ontology_context
        self._graph: Neo4jGraph | None = None
        self._chain: GraphCypherQAChain | None = None

    # -- lazy init ----------------------------------------------------------

    def _ensure_chain(self) -> GraphCypherQAChain:
        if self._chain is not None:
            return self._chain

        self._graph = Neo4jGraph(
            url=self._settings.neo4j_uri,
            username=self._settings.neo4j_username,
            password=self._settings.neo4j_password,
            database=self._settings.neo4j_database,
            enhanced_schema=False,
        )

        llm = self._ollama.get_chat_model()

        cypher_prompt = PromptTemplate(
            input_variables=["schema", "question", "ontology_section"],
            template=_DEFAULT_CYPHER_GENERATION_TEMPLATE,
            partial_variables={"ontology_section": ""},
        )
        qa_prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=_DEFAULT_QA_GENERATION_TEMPLATE,
        )

        # Inject ontology schema if available
        if self._ontology and hasattr(self._ontology, "schema_summary"):
            ontology_block = (
                "ONTOLOGY (class hierarchy & typed properties):\n"
                + self._ontology.schema_summary[:2000]
            )
            cypher_prompt = cypher_prompt.partial(ontology_section=ontology_block)

        self._chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self._graph,
            verbose=False,
            allow_dangerous_requests=True,
            return_intermediate_steps=True,
            cypher_prompt=cypher_prompt,
            qa_prompt=qa_prompt,
            validate_cypher=True,
        )
        logger.info("cypher_retriever.chain_ready")
        return self._chain

    # -- Retriever protocol -------------------------------------------------

    async def retrieve(self, query: QAQuery) -> list[RetrievedContext]:
        """Generate Cypher, execute, and wrap results as RetrievedContext."""
        chain = self._ensure_chain()

        try:
            result = await chain.ainvoke({"query": query.raw_question})
        except Exception as exc:
            logger.warning("cypher_retriever.chain_error", error=str(exc))
            return []

        steps = result.get("intermediate_steps", [])
        cypher_query = steps[0].get("query", "") if steps else ""
        context_rows: list[dict[str, Any]] = (
            steps[1].get("context", []) if len(steps) > 1 else []
        )
        answer_text = result.get("result", "")

        logger.info(
            "cypher_retriever.executed",
            cypher=cypher_query[:200],
            rows=len(context_rows),
            answer_len=len(answer_text),
        )

        if not context_rows:
            return []

        contexts: list[RetrievedContext] = []
        entities: list[KGEntity] = []

        for i, row in enumerate(context_rows):
            text_parts = []
            entity_id = row.get("id", row.get("n.id", ""))
            entity_label = row.get("label", row.get("n.label", ""))
            entity_type = row.get("type", row.get("n.node_type", ""))
            props_raw = row.get("properties", row.get("n.properties", ""))

            description = ""
            if isinstance(props_raw, str) and props_raw:
                try:
                    props = json.loads(props_raw)
                    description = props.get("description", "")
                except (json.JSONDecodeError, TypeError):
                    description = props_raw[:200]

            if entity_label:
                text_parts.append(f"{entity_label}")
            if entity_type:
                text_parts.append(f"[{entity_type}]")
            if description:
                text_parts.append(f"— {description}")
            if not text_parts:
                text_parts.append(str(row))

            text = " ".join(text_parts)

            if entity_id:
                entities.append(KGEntity(
                    id=entity_id,
                    label=entity_label or entity_id,
                    entity_type=entity_type or "Unknown",
                    description=description,
                    confidence=1.0,
                ))

            ctx = RetrievedContext(
                source=RetrievalSource.GRAPH,
                text=text,
                score=1.0 - (i * 0.02),
                provenance=Provenance(
                    entity_ids=[entity_id] if entity_id else [],
                    retrieval_strategy="cypher",
                    retrieval_score=1.0 - (i * 0.02),
                ),
            )
            contexts.append(ctx)

        # Append the LLM's synthesised answer
        if answer_text and answer_text.lower() not in ("i don't know the answer.", ""):
            summary_ctx = RetrievedContext(
                source=RetrievalSource.GRAPH,
                text=f"[Graph QA Summary] {answer_text}",
                score=1.0,
                provenance=Provenance(
                    retrieval_strategy="cypher_qa",
                    retrieval_score=1.0,
                    entity_ids=[e.id for e in entities[:10]],
                ),
            )
            contexts.insert(0, summary_ctx)

        logger.info(
            "cypher_retriever.done",
            contexts=len(contexts),
            entities=len(entities),
            cypher_preview=cypher_query[:120],
        )
        return contexts

    # -- direct Cypher execution --------------------------------------------

    async def run_cypher(self, question: str) -> dict[str, Any]:
        """Run the full chain and return raw result + intermediate steps."""
        chain = self._ensure_chain()
        try:
            result = await chain.ainvoke({"query": question})
            steps = result.get("intermediate_steps", [])
            return {
                "answer": result.get("result", ""),
                "cypher": steps[0].get("query", "") if steps else "",
                "context": steps[1].get("context", []) if len(steps) > 1 else [],
            }
        except Exception as exc:
            logger.error("cypher_retriever.run_cypher_error", error=str(exc))
            return {"answer": "", "cypher": "", "context": [], "error": str(exc)}

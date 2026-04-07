"""Tests for the full hybrid agentic GraphRAG pipeline.

Covers:
- New core models (DocumentChunk, QAQuery, Provenance, RetrievedContext, etc.)
- OllamaConnector
- QdrantConnector
- VectorRetriever
- OntologyContext
- OntologyRetriever
- PathRanker
- CrossEncoderReranker
- CypherRetriever
- HybridRetriever + RRF
- AgenticGraphRAG
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import (
    DocumentChunk,
    GraphExplorationState,
    KGEntity,
    KGRelation,
    Provenance,
    QAQuery,
    QuestionType,
    RetrievalSource,
    RetrievedContext,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings():
    return Settings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="changeme",
        fuseki_url="http://localhost:3030",
        fuseki_dataset="kgbuilder",
        qdrant_url="http://localhost:6333",
        qdrant_collection="kgbuilder",
        ollama_url="http://localhost:18135",
        ollama_model="gemma4:e2b",
        ollama_embedding_model="nomic-embed-text",
        vector_top_k=5,
        fusion_weight_vector=0.4,
        fusion_weight_graph=0.4,
        wandb_enabled=False,
    )


@pytest.fixture
def sample_query():
    return QAQuery(
        raw_question="What facilities require permits?",
        question_type=QuestionType.LIST,
        detected_entities=["Facility", "Permit"],
        detected_types=["Facility"],
        expected_relations=["requiresPermit"],
    )


@pytest.fixture
def sample_contexts():
    return [
        RetrievedContext(
            source=RetrievalSource.VECTOR,
            text="Nuclear facilities require special permits.",
            score=0.9,
            provenance=Provenance(
                retrieval_strategy="vector_only",
                retrieval_score=0.9,
            ),
        ),
        RetrievedContext(
            source=RetrievalSource.GRAPH,
            text="Facility X -[requiresPermit]-> Permit Y",
            score=0.85,
            subgraph=[
                KGRelation(
                    source_id="fac_x",
                    target_id="perm_y",
                    relation_type="requiresPermit",
                    confidence=0.9,
                )
            ],
            provenance=Provenance(
                entity_ids=["fac_x", "perm_y"],
                retrieval_strategy="graph",
                retrieval_score=0.85,
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Test new core models
# ---------------------------------------------------------------------------


class TestNewCoreModels:
    def test_document_chunk(self):
        chunk = DocumentChunk(
            id="chunk_001", doc_id="doc_001", content="Some text", strategy="fixed"
        )
        assert chunk.id == "chunk_001"
        assert chunk.doc_id == "doc_001"
        assert chunk.embedding is None

    def test_question_type_enum(self):
        assert QuestionType.FACTOID.value == "factoid"
        assert QuestionType.CAUSAL.value == "causal"
        assert QuestionType.AGGREGATION.value == "aggregation"

    def test_retrieval_source_enum(self):
        assert RetrievalSource.VECTOR.value == "vector"
        assert RetrievalSource.HYBRID.value == "hybrid"
        assert RetrievalSource.ONTOLOGY.value == "ontology"

    def test_qa_query(self):
        q = QAQuery(
            raw_question="test?",
            question_type=QuestionType.BOOLEAN,
            detected_entities=["A"],
        )
        assert q.raw_question == "test?"
        assert q.question_type == QuestionType.BOOLEAN
        assert q.language == "de"

    def test_provenance(self):
        p = Provenance(
            entity_ids=["e1", "e2"],
            retrieval_strategy="hybrid",
            retrieval_score=0.95,
        )
        assert len(p.entity_ids) == 2
        assert p.retrieval_strategy == "hybrid"

    def test_retrieved_context(self):
        ctx = RetrievedContext(
            source=RetrievalSource.GRAPH,
            text="some evidence",
            score=0.88,
        )
        assert ctx.source == RetrievalSource.GRAPH
        assert ctx.chunk is None
        assert ctx.subgraph is None

    def test_graph_exploration_state(self):
        state = GraphExplorationState()
        assert state.iterations == 0
        assert state.sufficient_evidence is False
        state.visited_entity_ids.add("e1")
        assert "e1" in state.visited_entity_ids


# ---------------------------------------------------------------------------
# Test OllamaConnector
# ---------------------------------------------------------------------------


class TestOllamaConnector:
    def test_init(self, settings):
        from ontology_hitl.connectors.ollama import OllamaConnector

        conn = OllamaConnector(settings)
        assert conn.chat_model is not None
        assert conn.embeddings is not None

    def test_get_chat_model(self, settings):
        from ontology_hitl.connectors.ollama import OllamaConnector

        conn = OllamaConnector(settings)
        model = conn.get_chat_model()
        assert model is not None
        assert model is conn.chat_model

    def test_get_embeddings(self, settings):
        from ontology_hitl.connectors.ollama import OllamaConnector

        conn = OllamaConnector(settings)
        emb = conn.get_embeddings()
        assert emb is not None
        assert emb is conn.embeddings


# ---------------------------------------------------------------------------
# Test QdrantConnector
# ---------------------------------------------------------------------------


class TestQdrantConnector:
    def test_init(self, settings):
        from ontology_hitl.connectors.qdrant import QdrantConnector

        conn = QdrantConnector(settings)
        assert conn._client is None

    def test_client_raises_before_connect(self, settings):
        from ontology_hitl.connectors.qdrant import QdrantConnector

        conn = QdrantConnector(settings)
        with pytest.raises(RuntimeError, match="not initialised"):
            _ = conn.client

    def test_point_to_chunk(self):
        from ontology_hitl.connectors.qdrant import QdrantConnector

        mock_point = MagicMock()
        mock_point.id = 42
        mock_point.payload = {
            "id": "chunk_1",
            "doc_id": "doc_1",
            "content": "Hello world",
            "strategy": "fixed",
        }
        chunk = QdrantConnector._point_to_chunk(mock_point)
        assert chunk.id == "chunk_1"
        assert chunk.doc_id == "doc_1"
        assert chunk.content == "Hello world"


# ---------------------------------------------------------------------------
# Test VectorRetriever
# ---------------------------------------------------------------------------


class TestVectorRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_empty_embedding(self, settings):
        from ontology_hitl.retrieval.vector import VectorRetriever

        mock_ollama = AsyncMock()
        mock_ollama.embed = AsyncMock(return_value=[])
        mock_qdrant = AsyncMock()

        vr = VectorRetriever(mock_qdrant, mock_ollama, settings)
        q = QAQuery(raw_question="test")
        result = await vr.retrieve(q)
        assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_with_results(self, settings):
        from ontology_hitl.retrieval.vector import VectorRetriever

        mock_ollama = AsyncMock()
        mock_ollama.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

        chunk = DocumentChunk(id="c1", doc_id="d1", content="Test content")
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=[(chunk, 0.95)])

        vr = VectorRetriever(mock_qdrant, mock_ollama, settings)
        q = QAQuery(raw_question="test")
        result = await vr.retrieve(q)
        assert len(result) == 1
        assert result[0].source == RetrievalSource.VECTOR
        assert result[0].text == "Test content"
        assert result[0].score == 0.95


# ---------------------------------------------------------------------------
# Test OntologyContext
# ---------------------------------------------------------------------------


class TestOntologyContext:
    def test_init(self):
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        mock_fuseki = MagicMock()
        ctx = OntologyContext(mock_fuseki)
        assert not ctx.loaded
        assert ctx.schema_summary == ""
        assert ctx.classes == {}

    def test_local_name(self):
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        assert OntologyContext._local_name("http://ex.org/ont#Facility") == "Facility"
        assert OntologyContext._local_name("http://ex.org/ont/Action") == "Action"
        assert OntologyContext._local_name("") == ""

    def test_fallback_summary(self):
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        mock_fuseki = MagicMock()
        ctx = OntologyContext(mock_fuseki)
        assert "no ontology" in ctx._fallback_summary().lower()

    def test_get_relations_for_unknown_type(self):
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        mock_fuseki = MagicMock()
        ctx = OntologyContext(mock_fuseki)
        assert ctx.get_relations_for_type("NonExistent") == []

    def test_get_subclass_names_empty(self):
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        mock_fuseki = MagicMock()
        ctx = OntologyContext(mock_fuseki)
        assert ctx.get_subclass_names("Unknown") == []


# ---------------------------------------------------------------------------
# Test OntologyRetriever
# ---------------------------------------------------------------------------


class TestOntologyRetriever:
    @pytest.mark.asyncio
    async def test_expand_query_no_types(self):
        from ontology_hitl.retrieval.ontology_retriever import OntologyRetriever

        mock_fuseki = MagicMock()
        retriever = OntologyRetriever(mock_fuseki)
        q = QAQuery(raw_question="test", detected_types=[])
        result = await retriever.expand_query(q)
        assert result is q  # Mutated in place

    @pytest.mark.asyncio
    async def test_get_answer_template(self):
        from ontology_hitl.retrieval.ontology_retriever import OntologyRetriever

        mock_fuseki = MagicMock()
        retriever = OntologyRetriever(mock_fuseki)
        template = await retriever.get_answer_template(
            QuestionType.BOOLEAN, ["Facility"]
        )
        assert "Yes or No" in template


# ---------------------------------------------------------------------------
# Test PathRanker
# ---------------------------------------------------------------------------


class TestPathRanker:
    def test_rank_paths_empty(self, sample_query):
        from ontology_hitl.retrieval.path_ranker import PathRanker

        ranker = PathRanker()
        result = ranker.rank_paths([], sample_query)
        assert result == []

    def test_rank_paths_with_subgraph(self, sample_query):
        from ontology_hitl.retrieval.path_ranker import PathRanker

        ranker = PathRanker()
        ctx = RetrievedContext(
            source=RetrievalSource.GRAPH,
            text="path context",
            score=0.5,
            subgraph=[
                KGRelation(
                    source_id="a",
                    target_id="b",
                    relation_type="requiresPermit",
                    confidence=0.9,
                )
            ],
        )
        ranked = ranker.rank_paths([ctx], sample_query)
        assert len(ranked) == 1
        # Score should be boosted because relation matches expected
        assert ranked[0].score > 0.0

    def test_score_path_empty(self):
        from ontology_hitl.retrieval.path_ranker import PathRanker

        ranker = PathRanker()
        assert ranker._score_path([], set()) == 0.0

    def test_explain_score(self):
        from ontology_hitl.retrieval.path_ranker import PathRanker

        relations = [
            KGRelation(
                source_id="a",
                target_id="b",
                relation_type="requiresPermit",
                confidence=0.8,
            )
        ]
        result = PathRanker.explain_score(relations, {"requirespermit"})
        assert result["avg_confidence"] == 0.8
        assert result["path_length"] == 1
        assert len(result["matched_relations"]) == 1


# ---------------------------------------------------------------------------
# Test CrossEncoderReranker
# ---------------------------------------------------------------------------


class TestCrossEncoderReranker:
    def test_rerank_empty(self):
        from ontology_hitl.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()
        assert reranker.rerank("test", []) == []

    def test_rerank_with_mock(self):
        from ontology_hitl.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()
        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=[0.9, 0.3])
        reranker._model = mock_model

        ctxs = [
            RetrievedContext(
                source=RetrievalSource.VECTOR, text="relevant text", score=0.5
            ),
            RetrievedContext(
                source=RetrievalSource.VECTOR, text="irrelevant text", score=0.8
            ),
        ]
        ranked = reranker.rerank("query", ctxs, top_k=2)
        assert len(ranked) == 2
        assert ranked[0].score == 0.9  # Higher cross-encoder score first
        assert ranked[1].score == 0.3


# ---------------------------------------------------------------------------
# Test HybridRetriever + RRF
# ---------------------------------------------------------------------------


class TestHybridRetriever:
    def test_reciprocal_rank_fusion_basic(self):
        from ontology_hitl.retrieval.hybrid import reciprocal_rank_fusion

        ctx_a = RetrievedContext(
            source=RetrievalSource.VECTOR, text="context A text here", score=0.9
        )
        ctx_b = RetrievedContext(
            source=RetrievalSource.GRAPH, text="context B text here", score=0.8
        )

        ranked_lists = {
            "vector": [ctx_a, ctx_b],
            "graph": [ctx_b, ctx_a],
        }
        weights = {"vector": 0.5, "graph": 0.5}

        fused = reciprocal_rank_fusion(ranked_lists, weights)
        assert len(fused) == 2
        # Both appear in both lists, scores should be positive
        assert all(ctx.score > 0 for ctx in fused)

    def test_reciprocal_rank_fusion_weighted(self):
        from ontology_hitl.retrieval.hybrid import reciprocal_rank_fusion

        ctx_v = RetrievedContext(
            source=RetrievalSource.VECTOR, text="vector only context", score=0.9
        )
        ctx_g = RetrievedContext(
            source=RetrievalSource.GRAPH, text="graph only context", score=0.8
        )

        ranked_lists = {
            "vector": [ctx_v],
            "graph": [ctx_g],
        }
        # Heavily weight graph
        weights = {"vector": 0.1, "graph": 0.9}

        fused = reciprocal_rank_fusion(ranked_lists, weights)
        assert len(fused) == 2
        # Graph context should rank higher due to higher weight
        assert fused[0].text.startswith("graph")

    def test_rrf_empty(self):
        from ontology_hitl.retrieval.hybrid import reciprocal_rank_fusion

        fused = reciprocal_rank_fusion({}, {})
        assert fused == []


# ---------------------------------------------------------------------------
# Test AgenticGraphRAG
# ---------------------------------------------------------------------------


class TestAgenticGraphRAG:
    def test_init(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        mock_neo4j = MagicMock()
        mock_qdrant = MagicMock()
        mock_ollama = MagicMock()
        mock_ontology = OntologyContext(MagicMock())

        agent = AgenticGraphRAG(
            neo4j=mock_neo4j,
            qdrant=mock_qdrant,
            ollama=mock_ollama,
            ontology_context=mock_ontology,
            settings=settings,
        )
        assert agent._neo4j is mock_neo4j
        assert agent._qdrant is mock_qdrant
        assert agent._settings is settings

    def test_build_tools(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        mock_neo4j = MagicMock()
        mock_qdrant = MagicMock()
        mock_ollama = MagicMock()
        mock_ontology = OntologyContext(MagicMock())

        agent = AgenticGraphRAG(
            neo4j=mock_neo4j,
            qdrant=mock_qdrant,
            ollama=mock_ollama,
            ontology_context=mock_ontology,
            settings=settings,
        )
        tools = agent._build_tools()
        assert len(tools) == 6
        tool_names = {t.name for t in tools}
        assert "search_vectors" in tool_names
        assert "query_graph" in tool_names
        assert "explore_entity" in tool_names
        assert "find_connections" in tool_names
        assert "lookup_ontology" in tool_names
        assert "collect_evidence" in tool_names

    def test_parse_vector_result(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        agent = AgenticGraphRAG(
            neo4j=MagicMock(),
            qdrant=MagicMock(),
            ollama=MagicMock(),
            ontology_context=OntologyContext(MagicMock()),
            settings=settings,
        )

        result_str = "[score=0.950] Some relevant text\n---\n[score=0.800] Another chunk"
        ctxs, ents, rels, chains = agent._parse_vector_result(result_str)
        assert len(ctxs) == 2
        assert ctxs[0].source == RetrievalSource.VECTOR
        assert len(ents) == 0

    def test_parse_vector_result_error(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        agent = AgenticGraphRAG(
            neo4j=MagicMock(),
            qdrant=MagicMock(),
            ollama=MagicMock(),
            ontology_context=OntologyContext(MagicMock()),
            settings=settings,
        )

        ctxs, _, _, _ = agent._parse_vector_result("No vector results found.")
        assert len(ctxs) == 0

    def test_parse_explore_result(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        agent = AgenticGraphRAG(
            neo4j=MagicMock(),
            qdrant=MagicMock(),
            ollama=MagicMock(),
            ontology_context=OntologyContext(MagicMock()),
            settings=settings,
        )

        result_str = json.dumps({
            "entity_id": "fac_001",
            "hops": 1,
            "entities": [
                {"id": "fac_001", "label": "Reactor A", "type": "Facility"},
                {"id": "perm_001", "label": "License X", "type": "Permit"},
            ],
            "relations": [
                {"src": "fac_001", "type": "requiresPermit", "tgt": "perm_001"},
            ],
        })

        ctxs, ents, rels, chains = agent._parse_explore_result(
            {"entity_id": "fac_001"}, result_str
        )
        assert len(ctxs) == 1
        assert len(ents) == 2
        assert len(rels) == 1
        assert rels[0].relation_type == "requiresPermit"

    def test_parse_path_result(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        agent = AgenticGraphRAG(
            neo4j=MagicMock(),
            qdrant=MagicMock(),
            ollama=MagicMock(),
            ontology_context=OntologyContext(MagicMock()),
            settings=settings,
        )

        result_str = json.dumps({
            "source": "fac_001",
            "target": "law_001",
            "paths": [
                {
                    "nodes": ["fac_001", "perm_001", "law_001"],
                    "node_labels": {
                        "fac_001": "Reactor A",
                        "perm_001": "License X",
                        "law_001": "AtG",
                    },
                    "edges": [
                        {"src": "fac_001", "type": "requiresPermit", "tgt": "perm_001"},
                        {"src": "perm_001", "type": "basedOn", "tgt": "law_001"},
                    ],
                    "chain": "fac_001 -[requiresPermit]-> perm_001 → perm_001 -[basedOn]-> law_001",
                }
            ],
        })

        ctxs, ents, rels, chains = agent._parse_path_result(result_str)
        assert len(ctxs) == 1
        assert len(ents) == 3
        assert len(rels) == 2
        assert len(chains) == 1
        assert chains[0]["source"] == "fac_001"
        assert "FACT CHAIN" in ctxs[0].text

    def test_parse_ontology_result(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        agent = AgenticGraphRAG(
            neo4j=MagicMock(),
            qdrant=MagicMock(),
            ollama=MagicMock(),
            ontology_context=OntologyContext(MagicMock()),
            settings=settings,
        )

        ctxs, _, _, _ = agent._parse_ontology_result(
            "Class: Facility\n  Parent: Thing"
        )
        assert len(ctxs) == 1
        assert ctxs[0].source == RetrievalSource.ONTOLOGY

        ctxs2, _, _, _ = agent._parse_ontology_result("No ontology info found.")
        assert len(ctxs2) == 0

    def test_finalize_dedup(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        agent = AgenticGraphRAG(
            neo4j=MagicMock(),
            qdrant=MagicMock(),
            ollama=MagicMock(),
            ontology_context=OntologyContext(MagicMock()),
            settings=settings,
        )

        ctx1 = RetrievedContext(
            source=RetrievalSource.VECTOR, text="duplicate text", score=0.9
        )
        ctx2 = RetrievedContext(
            source=RetrievalSource.GRAPH, text="duplicate text", score=0.8
        )
        ctx3 = RetrievedContext(
            source=RetrievalSource.GRAPH, text="unique text", score=0.7
        )

        result = agent._finalize([ctx1, ctx2, ctx3], [], [])
        # duplicate text should be deduped
        assert len(result) == 2
        # All marked as HYBRID
        assert all(ctx.source == RetrievalSource.HYBRID for ctx in result)

    def test_finalize_with_fact_chains(self, settings):
        from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
        from ontology_hitl.retrieval.ontology_context import OntologyContext

        agent = AgenticGraphRAG(
            neo4j=MagicMock(),
            qdrant=MagicMock(),
            ollama=MagicMock(),
            ontology_context=OntologyContext(MagicMock()),
            settings=settings,
        )

        chains = [
            {
                "source": "A",
                "target": "B",
                "node_ids": ["A", "B"],
                "node_labels": {"A": "Entity A", "B": "Entity B"},
                "edges": [{"src": "A", "type": "relates", "tgt": "B"}],
                "chain_text": "A -[relates]-> B",
            }
        ]
        result = agent._finalize([], [], [], chains)
        # Should have a graph reasoning summary context
        assert len(result) >= 1
        assert "GRAPH REASONING" in result[0].text


# ---------------------------------------------------------------------------
# Test CypherRetriever (init only — chain requires live Neo4j)
# ---------------------------------------------------------------------------


class TestCypherRetriever:
    def test_init(self, settings):
        from ontology_hitl.retrieval.cypher import CypherRetriever

        mock_ollama = MagicMock()
        cr = CypherRetriever(settings, mock_ollama)
        assert cr._chain is None
        assert cr._graph is None


# ---------------------------------------------------------------------------
# Test config additions
# ---------------------------------------------------------------------------


class TestNewConfigFields:
    def test_retrieval_config_fields(self, settings):
        assert settings.vector_top_k == 5
        assert settings.fusion_weight_vector == 0.4
        assert settings.fusion_weight_graph == 0.4
        assert settings.ollama_embedding_model == "nomic-embed-text"
        assert settings.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"

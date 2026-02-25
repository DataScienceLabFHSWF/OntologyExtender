"""Tests for the GraphRAG connectors, entity linker, graph retriever, and gap analyzer."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from ontology_hitl.core.config import Settings
from ontology_hitl.core.models import (
    KGEntity,
    KGRelation,
    OntologyClass,
    OntologyProperty,
)

# Auto mode so @pytest.mark.asyncio is not required on every test
pytestmark = pytest.mark.asyncio


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def settings():
    """Default test settings."""
    return Settings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="changeme",
        neo4j_database="neo4j",
        fuseki_url="http://localhost:3030",
        fuseki_dataset="kgbuilder",
        ollama_url="http://localhost:18135",
        semantic_embedding_model="qwen3-embedding",
        graph_max_hops=2,
        graph_max_nodes=50,
        ppr_damping=0.85,
        ppr_top_k=20,
        min_entity_frequency=2,
        semantic_similarity_threshold=0.65,
    )


@pytest.fixture
def sample_entities():
    return [
        KGEntity(id="e1", label="Reactor Building", entity_type="Facility", confidence=0.9),
        KGEntity(id="e2", label="Decommissioning Plan", entity_type="Document", confidence=0.85),
        KGEntity(id="e3", label="Radiation Shield", entity_type="Component", confidence=0.88),
    ]


@pytest.fixture
def sample_relations():
    return [
        KGRelation(source_id="e1", target_id="e3", relation_type="CONTAINS", confidence=0.9),
        KGRelation(source_id="e2", target_id="e1", relation_type="COVERS", confidence=0.85),
    ]


@pytest.fixture
def sample_tbox_classes():
    return [
        OntologyClass(uri="http://ex.org/onto#Facility", label="Facility"),
        OntologyClass(uri="http://ex.org/onto#Document", label="Document"),
        OntologyClass(uri="http://ex.org/onto#Process", label="Process"),
    ]


# ── Model tests ───────────────────────────────────────────────────────


class TestKGModels:
    def test_kg_entity_creation(self):
        e = KGEntity(id="e1", label="Test", entity_type="Thing", confidence=0.5)
        assert e.id == "e1"
        assert e.label == "Test"
        assert e.entity_type == "Thing"
        assert e.confidence == 0.5

    def test_kg_relation_creation(self):
        r = KGRelation(source_id="e1", target_id="e2", relation_type="REL", confidence=0.9)
        assert r.source_id == "e1"
        assert r.target_id == "e2"
        assert r.relation_type == "REL"

    def test_ontology_class(self):
        c = OntologyClass(uri="http://example.org/Foo", label="Foo")
        assert c.label == "Foo"

    def test_ontology_property(self):
        p = OntologyProperty(uri="http://ex.org/p", label="hasPart", domain_uri="A", range_uri="B")
        assert p.label == "hasPart"
        assert p.domain_uri == "A"


# ── Neo4jConnector tests (mocked driver) ─────────────────────────────


class TestNeo4jConnector:
    def test_label_clause_default(self, settings):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        conn = Neo4jConnector(settings)
        # Default "Entity" should produce empty label clause
        assert conn._lbl == ""

    def test_label_clause_custom(self, settings):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        settings.neo4j_node_label = "Facility"
        conn = Neo4jConnector(settings)
        assert conn._lbl == ":Facility"

    def test_record_to_entity_basic(self):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        node = {"id": "e1", "label": "Reactor", "entity_type": "Facility", "confidence": 0.9}
        entity = Neo4jConnector._record_to_entity(node)
        assert entity.id == "e1"
        assert entity.label == "Reactor"
        assert entity.entity_type == "Facility"

    def test_record_to_entity_json_properties(self):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        node = {
            "id": "e2",
            "label": "Shield",
            "properties": '{"description": "Radiation shielding", "aliases": ["screen"]}',
        }
        entity = Neo4jConnector._record_to_entity(node, neo4j_labels=["Component"])
        assert entity.id == "e2"
        assert entity.description == "Radiation shielding"
        assert entity.entity_type == "Component"

    def test_record_to_entity_fallback_label(self):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        node = {"id": "e3"}
        entity = Neo4jConnector._record_to_entity(node, neo4j_labels=["Activity"])
        assert entity.entity_type == "Activity"
        assert entity.label == "e3"  # Falls back to id


# ── FusekiConnector tests (mocked HTTP) ──────────────────────────────


class TestFusekiConnector:
    @pytest.mark.asyncio
    async def test_get_all_classes(self, settings):
        from ontology_hitl.connectors.fuseki import FusekiConnector
        conn = FusekiConnector(settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": {
                "bindings": [
                    {"class": {"value": "http://ex.org/Facility"}, "label": {"value": "Facility"}},
                    {"class": {"value": "http://ex.org/Document"}, "label": {"value": "Document"}},
                ]
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        conn._client = mock_client

        classes = await conn.get_all_classes()
        assert len(classes) == 2
        assert classes[0].label == "Facility"
        assert classes[1].label == "Document"


# ── EntityLinker tests ────────────────────────────────────────────────


class TestKGEntityLinker:
    @pytest.mark.asyncio
    async def test_link_exact_id(self, settings, sample_entities):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        from ontology_hitl.retrieval.kg_entity_linker import KGEntityLinker

        mock_neo4j = AsyncMock(spec=Neo4jConnector)
        mock_neo4j.find_entities_by_ids = AsyncMock(return_value=[sample_entities[0]])
        mock_neo4j.find_entities_by_label = AsyncMock(return_value=[])

        linker = KGEntityLinker(mock_neo4j)
        linked = await linker.link(["e1"])
        assert len(linked) >= 1
        assert linked[0].id == "e1"

    @pytest.mark.asyncio
    async def test_link_empty_terms(self, settings):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        from ontology_hitl.retrieval.kg_entity_linker import KGEntityLinker

        mock_neo4j = AsyncMock(spec=Neo4jConnector)
        linker = KGEntityLinker(mock_neo4j)
        linked = await linker.link([])
        assert linked == []


# ── GraphRetriever tests ─────────────────────────────────────────────


class TestGraphRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_subgraph(self, settings, sample_entities, sample_relations):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        from ontology_hitl.retrieval.kg_entity_linker import KGEntityLinker
        from ontology_hitl.retrieval.graph_retriever import GraphRetriever, GraphMode

        mock_neo4j = AsyncMock(spec=Neo4jConnector)
        mock_neo4j.get_neighbourhood = AsyncMock(
            return_value=(sample_entities, sample_relations)
        )

        mock_linker = AsyncMock(spec=KGEntityLinker)
        mock_linker.link = AsyncMock(return_value=sample_entities[:1])

        retriever = GraphRetriever(mock_neo4j, mock_linker, settings)
        result = await retriever.retrieve(["Reactor Building"], mode=GraphMode.SUBGRAPH)

        assert result["mode"] == "subgraph"
        assert len(result["entities"]) == 3
        assert len(result["relations"]) == 2
        assert "Reactor Building" in result["text"]

    @pytest.mark.asyncio
    async def test_retrieve_no_linked_entities(self, settings):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        from ontology_hitl.retrieval.kg_entity_linker import KGEntityLinker
        from ontology_hitl.retrieval.graph_retriever import GraphRetriever, GraphMode

        mock_neo4j = AsyncMock(spec=Neo4jConnector)
        mock_linker = AsyncMock(spec=KGEntityLinker)
        mock_linker.link = AsyncMock(return_value=[])

        retriever = GraphRetriever(mock_neo4j, mock_linker, settings)
        result = await retriever.retrieve(["nonexistent"])

        assert result["text"] == ""
        assert result["entities"] == []

    def test_serialise_subgraph(self, sample_entities, sample_relations):
        from ontology_hitl.retrieval.graph_retriever import GraphRetriever

        text = GraphRetriever.serialise_subgraph(sample_entities, sample_relations)
        assert "Reactor Building" in text
        assert "CONTAINS" in text
        assert "COVERS" in text
        assert "Knowledge Graph Evidence" in text


# ── GraphRAGGapAnalyzer tests ────────────────────────────────────────


class TestGraphRAGGapAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_basic(self, settings, sample_entities, sample_tbox_classes):
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        from ontology_hitl.connectors.fuseki import FusekiConnector
        from ontology_hitl.retrieval.graphrag_gap_analyzer import GraphRAGGapAnalyzer

        mock_neo4j = AsyncMock(spec=Neo4jConnector)
        mock_fuseki = AsyncMock(spec=FusekiConnector)

        abox_entities = [
            KGEntity(id="e1", label="Reactor", entity_type="Facility", confidence=0.9),
            KGEntity(id="e2", label="Plan", entity_type="Document", confidence=0.85),
            KGEntity(id="e3", label="Shield", entity_type="Component", confidence=0.88),
            KGEntity(id="e4", label="Shield2", entity_type="Component", confidence=0.7),
        ]

        # Mock TBox query
        mock_fuseki.get_all_classes = AsyncMock(return_value=sample_tbox_classes)

        # Mock neighbour queries (structural score)
        mock_neo4j.get_entity_neighbours = AsyncMock(return_value=[])

        analyzer = GraphRAGGapAnalyzer(settings, mock_neo4j, mock_fuseki)

        # Patch _fetch_all_entities to return our test entities directly
        import numpy as np
        zero_embed = np.zeros(1)
        with patch.object(analyzer, '_fetch_all_entities', new_callable=AsyncMock) as mock_fetch, \
             patch.object(analyzer, '_get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_fetch.return_value = abox_entities
            mock_embed.return_value = zero_embed
            report = await analyzer.analyze()

        assert report.total_extracted_entities == 4
        # Facility and Document should be covered (exact match in tbox_classes)
        assert report.covered_entities >= 2

    @pytest.mark.asyncio
    async def test_classify_exact_match(self, settings):
        """Entities whose entity_type exactly matches a TBox label are covered."""
        from ontology_hitl.connectors.neo4j import Neo4jConnector
        from ontology_hitl.connectors.fuseki import FusekiConnector
        from ontology_hitl.retrieval.graphrag_gap_analyzer import GraphRAGGapAnalyzer

        mock_neo4j = AsyncMock(spec=Neo4jConnector)
        mock_fuseki = AsyncMock(spec=FusekiConnector)

        analyzer = GraphRAGGapAnalyzer(settings, mock_neo4j, mock_fuseki)

        entities = [
            KGEntity(id="e1", label="Reactor X", entity_type="Facility", confidence=0.9),
            KGEntity(id="e2", label="Unknown Thing", entity_type="Widget", confidence=0.5),
        ]
        tbox = [OntologyClass(uri="http://ex.org/Facility", label="Facility")]

        import numpy as np
        with patch.object(analyzer, '_get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = np.zeros(1)
            covered, uncovered = await analyzer._classify_entities(entities, tbox)

        assert len(covered) == 1
        assert covered[0].id == "e1"
        assert len(uncovered) == 1
        assert uncovered[0].id == "e2"


# ── Config tests ──────────────────────────────────────────────────────


class TestGraphRAGConfig:
    def test_new_config_fields(self, settings):
        assert settings.neo4j_database == "neo4j"
        assert settings.neo4j_node_label == "Entity"
        assert settings.graph_max_hops == 2
        assert settings.graph_max_nodes == 50
        assert settings.ppr_damping == 0.85
        assert settings.ppr_top_k == 20

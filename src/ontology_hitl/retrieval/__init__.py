"""Retrieval modules — full hybrid agentic GraphRAG pipeline.

Ported from GraphQAAgent:
- Entity linking (4-tier fuzzy + embedding)
- Graph retriever (entity-centric, subgraph, path, PPR modes)
- Vector retriever (embed → Qdrant search)
- Cypher retriever (LLM → Cypher → Neo4j)
- Ontology context (TBox knowledge cache)
- Ontology retriever (query expansion)
- Path ranker (relation-aware scoring)
- Cross-encoder reranker
- Hybrid retriever (RRF fusion)
- Agentic GraphRAG (ReAct 6-tool agent)
- Gap analyzer (live Neo4j+Fuseki gap detection)
"""

from ontology_hitl.retrieval.kg_entity_linker import KGEntityLinker
from ontology_hitl.retrieval.graph_retriever import GraphRetriever, GraphMode
from ontology_hitl.retrieval.vector import VectorRetriever
from ontology_hitl.retrieval.cypher import CypherRetriever
from ontology_hitl.retrieval.ontology_context import OntologyContext
from ontology_hitl.retrieval.ontology_retriever import OntologyRetriever
from ontology_hitl.retrieval.path_ranker import PathRanker
from ontology_hitl.retrieval.reranker import CrossEncoderReranker
from ontology_hitl.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from ontology_hitl.retrieval.agentic_rag import AgenticGraphRAG
from ontology_hitl.retrieval.graphrag_gap_analyzer import GraphRAGGapAnalyzer

__all__ = [
    "KGEntityLinker",
    "GraphRetriever",
    "GraphMode",
    "VectorRetriever",
    "CypherRetriever",
    "OntologyContext",
    "OntologyRetriever",
    "PathRanker",
    "CrossEncoderReranker",
    "HybridRetriever",
    "reciprocal_rank_fusion",
    "AgenticGraphRAG",
    "GraphRAGGapAnalyzer",
]

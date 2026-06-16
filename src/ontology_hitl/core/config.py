"""Configuration for ontology-hitl."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment.

    Environment variables use HITL_ prefix (e.g., HITL_FUSEKI_URL).
    Defaults follow INTERFACE_CONTRACT.md for compatibility with
    KnowledgeGraphBuilder and GraphQAAgent.
    """

    model_config = SettingsConfigDict(
        env_prefix="HITL_",
        env_file=".env",
        extra="ignore",
    )

    # Neo4j (async driver for GraphRAG)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_http_url: str = "http://localhost:7474"  # HTTP API (legacy LawGraphSource)
    neo4j_username: str = "neo4j"
    neo4j_password: str = "changeme"
    neo4j_database: str = "neo4j"
    neo4j_node_label: str = "Entity"  # Cypher label filter; "Entity" → match all

    # GraphRAG retrieval parameters
    graph_max_hops: int = 2
    graph_max_nodes: int = 50
    ppr_damping: float = 0.85
    ppr_top_k: int = 20

    # Fuseki (per INTERFACE_CONTRACT.md §3)
    fuseki_url: str = "http://localhost:3030"
    fuseki_dataset: str = "kgbuilder"
    fuseki_staging_dataset: str = "kgbuilder-staging"
    fuseki_user: str = "admin"
    fuseki_password: str = ""

    # Qdrant (document vector store — shared with KGB, per INTERFACE_CONTRACT.md §2)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "kgbuilder"

    # LLM (for definition generation)
    ollama_url: str = "http://localhost:18135"
    ollama_model: str = "llama3.2:3b"  # Using smaller model for faster testing
    # Embedding model used as a fallback for semantic matching when
    # `sentence-transformers` is not available. Exposed via
    # `HITL_SEMANTIC_EMBEDDING_MODEL` environment variable.
    semantic_embedding_model: str = "qwen3-embedding"

    llm_temperature: float = 0.5
    llm_timeout_seconds: int = 300  # Reduced for smaller model

    @property
    def effective_llm_timeout_seconds(self) -> int:
        """Get timeout based on model size - large models need more time."""
        model = self.ollama_model.lower()
        if "qwen" in model or "79b" in model or "72b" in model or "70b" in model:
            return 1200  # 20 minutes for large models
        elif "3b" in model or "1.5b" in model:
            return 600   # 10 minutes for small models
        else:
            return 900   # 15 minutes for medium models

    # Gap Analysis
    min_entity_frequency: int = 3
    semantic_similarity_threshold: float = 0.65
    gap_confidence_threshold: float = 0.6

    # Review
    min_reviewers_per_class: int = 1
    require_min_expert_agreement: float = 0.75

    # Evaluation targets
    cq_answerability_target: float = 0.80
    entity_coverage_target: float = 0.80

    # Weights & Biases
    wandb_enabled: bool = True  # Enable by default for experiments
    wandb_entity: str = ""
    wandb_project: str = "ontology-hitl"
    wandb_api_key: str = ""

    # Entity Linking (module B)
    entity_linking_enabled: bool = True
    entity_linking_threshold: float = 0.75

    # Embedding Advisor (module C)
    embedding_advisor_enabled: bool = True

    # Ensemble Strategy (module E)
    ensemble_enabled: bool = True
    ensemble_weight_llm: float = 0.5
    ensemble_weight_embedding: float = 0.3
    ensemble_weight_cooccurrence: float = 0.2

    # Feedback Learner (module F)
    feedback_learning_enabled: bool = True
    feedback_memory_path: str = "data/feedback_memory.json"
    feedback_max_few_shot: int = 5

    # Provenance (module D)
    provenance_enabled: bool = True

    # Legal enrichment (LawGraph / lawgraph Qdrant collection)
    # OFF by default — only enable for legal/regulatory use cases.
    # Set HITL_LEGAL_ENRICHMENT_ENABLED=true in .env or environment.
    legal_enrichment_enabled: bool = False

    # Reasoner agent (logical consistency checking during debate)
    reasoner_enabled: bool = True
    reasoner_llm_explanations: bool = True

    # DomainExpert web search (Wikipedia + DDG Lite, allowlisted, rate-limited)
    # When enabled, the expert fetches short Wikipedia/DDG snippets for proposed
    # concepts it cannot ground from the local corpus. Disabled by default to
    # keep behaviour deterministic; enable for richer CQ generation.
    web_search_enabled: bool = False
    web_search_max_queries: int = 3   # per review call
    web_search_max_chars: int = 500   # per snippet
    web_search_timeout: float = 5.0   # seconds per HTTP request

    # Ollama embeddings
    ollama_embedding_model: str = "nomic-embed-text"

    # Retrieval pipeline (HybridRetriever / AgenticGraphRAG)
    vector_top_k: int = 10
    fusion_weight_vector: float = 0.4
    fusion_weight_graph: float = 0.4
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Domain configuration
    # Used in fallback definitions, CQ generation, and entity extraction
    # prompts. Set to empty string for domain-agnostic operation (e.g.
    # OntoURL benchmark).  Examples: "nuclear decommissioning",
    # "pizza", "music".
    domain_name: str = ""

    # Paths
    seed_ontology_path: str = "data/seed_ontology/plan-ontology-v1.0.owl"
    iterations_dir: str = "data/iterations"
    exports_dir: str = "data/exports"

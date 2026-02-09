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

    # Neo4j (optional — for future GraphQAAgent integration)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = ""
    neo4j_password: str = ""

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
    ollama_model: str = "qwen3-next"
    llm_temperature: float = 0.5

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
    wandb_enabled: bool = False
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

    # Paths
    seed_ontology_path: str = "data/seed_ontology/plan-ontology-v1.0.owl"
    iterations_dir: str = "data/iterations"
    exports_dir: str = "data/exports"

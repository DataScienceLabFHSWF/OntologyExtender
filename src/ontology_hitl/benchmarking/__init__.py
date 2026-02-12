"""Benchmarking framework for CogAgent vs. baseline ontology systems.

Compares CogAgent (multi-agent debate + HITL) against three baselines:
  - Agent-OM  (Qiang et al., VLDB 2024) — 2-agent ontology matching
  - LLM4ACOE  (Soularidis et al., KER 2025) — 3-agent autonomous extension
  - NLP-W2V   (Behr et al., 2023) — Word2Vec + ontology rules

Extended evaluation frameworks integrated from recent literature:
  - TamingHallucinations (Fathallah et al., 2025) — semantic matching
  - OntoURL (Zhang et al., 2025) — 15-task capability profiling
  - OWLUnit (Asprino, 2024) — ontology unit testing

Submodules
----------
models          Pydantic data models for benchmark configs, results, metrics
test_cases      Ontology decomposition into difficulty-graded test cases
baselines       Adapter wrappers for each baseline system
metrics         Six-dimension + extended evaluation scorer
aggregator      Cross-system results collection and comparison tables
statistics      Significance testing (paired t-test, bootstrap CI)
reporting       Publication-ready tables, charts, and LaTeX fragments
runner          Orchestrator that executes a full benchmark suite
datasets        External benchmark dataset registry and loader
"""

from .models import (
    BenchmarkConfig,
    BenchmarkDataset,
    BenchmarkResult,
    MetricScores,
    OntoURLCapability,
    OntoURLCapabilityProfile,
    OntoURLTask,
    OntoURLTaskScore,
    OWLUnitTestResult,
    OWLUnitTestSuite,
    OWLUnitTestType,
    SemanticMatchLevel,
    SemanticMatchResult,
    TestCase,
    BaselineSystemConfig,
)

__all__ = [
    "BenchmarkConfig",
    "BenchmarkDataset",
    "BenchmarkResult",
    "MetricScores",
    "OntoURLCapability",
    "OntoURLCapabilityProfile",
    "OntoURLTask",
    "OntoURLTaskScore",
    "OWLUnitTestResult",
    "OWLUnitTestSuite",
    "OWLUnitTestType",
    "SemanticMatchLevel",
    "SemanticMatchResult",
    "TestCase",
    "BaselineSystemConfig",
]

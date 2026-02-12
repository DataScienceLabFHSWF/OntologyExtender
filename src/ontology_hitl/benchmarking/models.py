"""Pydantic data models for the benchmarking framework.

Defines the canonical schemas for:
  - Test case specifications (ontology reduction levels)
  - Baseline system configurations (repo paths, commands, env)
  - Six-dimension + extended metric scores
  - OntoURL 15-task capability taxonomy (Understanding / Reasoning / Learning)
  - TamingHallucinations semantic matching scores (concept + triple level)
  - OWLUnit ontology unit test integration (4 test types)
  - Per-system benchmark results
  - External benchmark dataset references
  - Full benchmark suite configuration

All models are serialisable to/from JSON for reproducibility and
integration with W&B artifact logging.

References
----------
- BENCHMARKING_STRATEGY.md §Metrics Table
- BENCHMARKING_EXECUTIVE_SUMMARY.md §Master Comparison Table
- BASELINE_POSITIONING_SUMMARY.md §Benchmark Plan
- Zhang et al. (2025) "OntoURL: A Benchmark for Evaluating LLMs on
  Symbolic Ontological Understanding, Reasoning and Learning"
  https://arxiv.org/abs/2505.11031
- Fathallah, Staab & Algergawy (2025) "Taming Hallucinations: A Semantic
  Matching Evaluation Framework for LLM-Generated Ontologies"
  https://github.com/NadeenAhmad/TamingHallucinations
- Asprino (2024) "OWLUnit: Ontology Unit Testing Framework"
  https://github.com/luigi-asprino/owl-unit
- Plu et al. (2024) "A Comprehensive Benchmark for Evaluating LLM-Generated
  Ontologies" ISWC 2024.  https://github.com/jplu/ontology-benchmark
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReductionLevel(str, Enum):
    """Percentage of classes removed from the gold-standard ontology.

    Each level produces a progressively harder extension task:
      PCT_50 — 50 % of classes removed  (easy, warm-up)
      PCT_75 — 75 % removed             (moderate, primary benchmark)
      PCT_90 — 90 % removed             (hard, stress test)
      PCT_95 — 95 % removed             (extreme, near from-scratch)
    """
    PCT_50 = "50pct"
    PCT_75 = "75pct"
    PCT_90 = "90pct"
    PCT_95 = "95pct"


class BaselineSystem(str, Enum):
    """Identifier for each system under comparison.

    COGAGENT    — Our system (multi-agent debate + HITL)
    AGENT_OM    — Qiang et al. VLDB 2024 (ontology matching)
    LLM4ACOE    — Soularidis et al. KER 2025 (autonomous extension)
    NLP_W2V     — Behr et al. 2023 (Word2Vec + rules)
    """
    COGAGENT = "cogagent"
    AGENT_OM = "agent_om"
    LLM4ACOE = "llm4acoe"
    NLP_W2V = "nlp_w2v"


class OntoURLCapability(str, Enum):
    """Capability levels from OntoURL's Bloom-inspired taxonomy.

    Zhang et al. (2025) define three hierarchical capability levels
    with five tasks each, totalling 15 evaluation dimensions.

    See: https://arxiv.org/abs/2505.11031 §3.1 Taxonomy
    """
    UNDERSTANDING = "understanding"
    REASONING = "reasoning"
    LEARNING = "learning"


class OntoURLTask(str, Enum):
    """All 15 OntoURL tasks across three capability levels.

    Understanding (U1–U5):
      U1 — Class Definition: identify/select correct class definitions
      U2 — Class Relation: identify taxonomic relations between classes
      U3 — Property Domain: determine property domain/range
      U4 — Instance Class: classify instances to correct classes
      U5 — Instance Definition: identify/select instance descriptions

    Reasoning (R1–R5):
      R1 — Inferred Relation: deduce implicit taxonomic relations
      R2 — Constraint: reason about OWL constraints (cardinality, disjointness)
      R3 — Instance Class (Inferred): classify instances using reasoning
      R4 — SWRL-Based: apply SWRL rules for logical inference
      R5 — Description Logic: reason with DL axioms

    Learning (L1–L5):
      L1 — Class Definition Generation: generate class definitions from context
      L2 — Class Hierarchy Construction: build taxonomic tree from classes
      L3 — Property Relation Construction: create property domain/range triples
      L4 — Constraint Construction: generate OWL constraints
      L5 — Ontology Alignment: align concepts across ontologies
    """
    # Understanding
    U1_CLASS_DEFINITION = "U1_class_definition"
    U2_CLASS_RELATION = "U2_class_relation"
    U3_PROPERTY_DOMAIN = "U3_property_domain"
    U4_INSTANCE_CLASS = "U4_instance_class"
    U5_INSTANCE_DEFINITION = "U5_instance_definition"
    # Reasoning
    R1_INFERRED_RELATION = "R1_inferred_relation"
    R2_CONSTRAINT = "R2_constraint"
    R3_INSTANCE_CLASS_INFERRED = "R3_instance_class_inferred"
    R4_SWRL_BASED = "R4_swrl_based"
    R5_DESCRIPTION_LOGIC = "R5_description_logic"
    # Learning
    L1_CLASS_DEF_GENERATION = "L1_class_def_generation"
    L2_HIERARCHY_CONSTRUCTION = "L2_hierarchy_construction"
    L3_PROPERTY_CONSTRUCTION = "L3_property_construction"
    L4_CONSTRAINT_CONSTRUCTION = "L4_constraint_construction"
    L5_ONTOLOGY_ALIGNMENT = "L5_ontology_alignment"


class OWLUnitTestType(str, Enum):
    """OWLUnit test types for systematic ontology unit testing.

    Asprino (2024) defines four complementary verification strategies:

    ANNOTATION     — Verify SHACL-based annotation constraints on entities
    COMPETENCY_Q   — Verify CQ → SPARQL answerability (IRI defs + result iso.)
    INFERENCE      — Check ontology consistency + reasoner-based inference (ASK)
    ERROR_PROVOKE  — Inject inconsistent data and verify detection by reasoner
    """
    ANNOTATION = "annotation_verification"
    COMPETENCY_Q = "competency_question_verification"
    INFERENCE = "inference_verification"
    ERROR_PROVOKE = "error_provocation"


class SemanticMatchLevel(str, Enum):
    """Granularity levels for TamingHallucinations semantic matching.

    Fathallah et al. (2025) evaluate at two complementary levels:

    CONCEPT — Match LLM-generated concept labels against reference ontology
              concept labels using sentence-transformer embeddings + cosine sim.
    TRIPLE  — Match generated SPO triples against reference triples by
              converting each triple to a sentence and computing embeddings.
    """
    CONCEPT = "concept_level"
    TRIPLE = "triple_level"


# ---------------------------------------------------------------------------
# Test Case
# ---------------------------------------------------------------------------

class TestCase(BaseModel):
    """A single benchmark test case produced by ontology decomposition.

    The test case is defined by a *reduced* seed ontology (with classes
    deliberately removed) and the gold-standard reference for evaluation.
    Competency questions that target the *removed* classes quantify
    whether a system can rediscover what was taken away.

    Attributes
    ----------
    id : str
        Human-readable identifier, e.g. ``"plan-ontology-75pct"``.
    reduction_level : ReductionLevel
        How aggressively the gold-standard was reduced.
    seed_ontology_path : Path
        Path to the *reduced* OWL file used as input seed.
    gold_standard_path : Path
        Path to the *full* gold-standard OWL file.
    removed_classes : list[str]
        URIs of the classes that were deliberately removed.
    removed_properties : list[str]
        URIs of the properties that were deliberately removed.
    competency_questions : list[CompetencyQuestion]
        CQs that should become answerable after a successful extension.
    num_original_classes : int
        Total classes in the gold-standard.
    num_remaining_classes : int
        Classes left in the reduced seed.
    metadata : dict[str, Any]
        Free-form extra info (creation date, random seed, etc.).
    """

    id: str
    reduction_level: ReductionLevel
    seed_ontology_path: Path
    gold_standard_path: Path
    removed_classes: list[str] = Field(default_factory=list)
    removed_properties: list[str] = Field(default_factory=list)
    competency_questions: list[CompetencyQuestion] = Field(default_factory=list)
    num_original_classes: int = 0
    num_remaining_classes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompetencyQuestion(BaseModel):
    """A competency question targeting removed ontology elements.

    CQs serve as the *functional* specification: if a system correctly
    extends the ontology, these questions should become answerable.

    Attributes
    ----------
    id : str
        Short identifier, e.g. ``"CQ-07"``.
    question : str
        Natural-language question text.
    target_classes : list[str]
        Class URIs whose presence is required to answer the CQ.
    target_properties : list[str]
        Property URIs whose presence is required.
    sparql_template : str | None
        Optional SPARQL query that should return non-empty results
        when the ontology covers the CQ.
    difficulty : str
        One of ``"easy"``, ``"medium"``, ``"hard"`` — based on how many
        classes/relations are needed simultaneously.
    """

    id: str
    question: str
    target_classes: list[str] = Field(default_factory=list)
    target_properties: list[str] = Field(default_factory=list)
    sparql_template: str | None = None
    difficulty: str = "medium"


# -- fix forward reference in TestCase --
TestCase.model_rebuild()


# ---------------------------------------------------------------------------
# TamingHallucinations: Semantic Matching Scores
# ---------------------------------------------------------------------------

class SemanticMatchResult(BaseModel):
    """Result of semantic matching at concept or triple level.

    Models the evaluation approach of Fathallah et al. (2025) which
    compares LLM-generated ontologies against reference domain ontologies
    using sentence-transformer embeddings and cosine similarity.

    The framework operates at two levels:
      - **Concept matching**: Embed concept labels + definitions, find
        best cosine match in reference ontology (threshold ≥ 0.55).
      - **Triple matching**: Convert SPO triples to sentences, embed,
        find best match in reference triples (threshold ≥ 0.50).

    Unmatched items are flagged as potential hallucinations.

    Attributes
    ----------
    level : SemanticMatchLevel
        CONCEPT or TRIPLE level matching.
    total_generated : int
        Total elements in the LLM-generated ontology.
    total_matched : int
        Elements matched to at least one reference ontology.
    total_hallucinated : int
        Elements with no match in any reference ontology.
    match_percentage : float
        ``total_matched / total_generated * 100``.
    hallucination_percentage : float
        ``total_hallucinated / total_generated * 100``.
    similarity_threshold : float
        Cosine similarity threshold used for matching.
    embedding_model : str
        Sentence-transformer model used (default: all-MiniLM-L6-v2).
    reference_ontologies : list[str]
        Names of reference ontologies compared against.
    per_reference_matches : dict[str, float]
        Cumulative match % after each reference ontology.
    matched_pairs : list[dict[str, str]]
        Sample of matched (generated → reference) pairs for inspection.

    References
    ----------
    Fathallah, Staab & Algergawy (2025). "Taming Hallucinations."
    https://github.com/NadeenAhmad/TamingHallucinations
    """

    level: SemanticMatchLevel
    total_generated: int = 0
    total_matched: int = 0
    total_hallucinated: int = 0
    match_percentage: float = 0.0
    hallucination_percentage: float = 0.0
    similarity_threshold: float = 0.55
    embedding_model: str = "all-MiniLM-L6-v2"
    reference_ontologies: list[str] = Field(default_factory=list)
    per_reference_matches: dict[str, float] = Field(default_factory=dict)
    matched_pairs: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# OntoURL: Task-Level Capability Scores
# ---------------------------------------------------------------------------

class OntoURLTaskScore(BaseModel):
    """Score for a single OntoURL task (one of 15 tasks).

    OntoURL (Zhang et al., 2025) evaluates LLMs across 15 tasks in
    three capability levels, using task-appropriate metrics:

    - Understanding/Reasoning MCQ tasks: **Accuracy**
    - Learning generation tasks: **ROUGE-L**, **Triple-F1**, **Tuple-F1**

    Attributes
    ----------
    task : OntoURLTask
        Which of the 15 tasks this score represents.
    capability : OntoURLCapability
        The parent capability level (Understanding/Reasoning/Learning).
    accuracy : float | None
        MCQ accuracy for understanding/reasoning tasks [0, 1].
    rouge_l : float | None
        ROUGE-L for generation tasks [0, 1].
    triple_f1 : float | None
        Triple-F1 for structured output tasks [0, 1].
    tuple_f1 : float | None
        Tuple-F1 for structured output tasks [0, 1].
    num_questions : int
        Number of questions evaluated for this task.
    shot_setting : str
        Evaluation setting: "zero-shot", "two-shot", "four-shot".
    """

    task: OntoURLTask
    capability: OntoURLCapability
    accuracy: float | None = None
    rouge_l: float | None = None
    triple_f1: float | None = None
    tuple_f1: float | None = None
    num_questions: int = 0
    shot_setting: str = "zero-shot"


class OntoURLCapabilityProfile(BaseModel):
    """Aggregated capability profile across OntoURL's three levels.

    Summarises a system's performance across Understanding, Reasoning,
    and Learning — exposing strengths and weaknesses that our
    six-dimension metrics may miss.

    Attributes
    ----------
    understanding_avg : float
        Average accuracy across U1–U5 tasks.
    reasoning_avg : float
        Average accuracy across R1–R5 tasks.
    learning_avg : float
        Average metric across L1–L5 tasks (ROUGE-L or Triple-F1).
    task_scores : list[OntoURLTaskScore]
        Per-task scores for all 15 tasks.
    overall_avg : float
        Grand average across all 15 tasks.
    model_name : str
        LLM model evaluated.

    References
    ----------
    Zhang et al. (2025). "OntoURL" §5 Experimental Results.
    Dataset: huggingface.co/datasets/XiaoZhang98/OntoURL
    """

    understanding_avg: float = 0.0
    reasoning_avg: float = 0.0
    learning_avg: float = 0.0
    task_scores: list[OntoURLTaskScore] = Field(default_factory=list)
    overall_avg: float = 0.0
    model_name: str = ""


# ---------------------------------------------------------------------------
# OWLUnit: Ontology Unit Test Results
# ---------------------------------------------------------------------------

class OWLUnitTestResult(BaseModel):
    """Result of a single OWLUnit test case execution.

    OWLUnit (Asprino, 2024) provides four test types for systematic
    ontology quality verification:

    1. **Annotation Verification** — SHACL shapes for entity annotations
    2. **CQ Verification** — CQ → SPARQL, check IRI defs + result isomorphism
    3. **Inference Verification** — Consistency + SPARQL ASK on inferred model
    4. **Error Provocation** — Inject inconsistent data, verify detection

    Attributes
    ----------
    test_type : OWLUnitTestType
        Which of the four test types was executed.
    test_id : str
        Human-readable identifier, e.g. "CQ-07-inference".
    passed : bool
        Whether the test passed.
    description : str
        What the test verifies.
    sparql_query : str | None
        The SPARQL query used (for CQ and Inference types).
    expected_result : str | None
        Expected outcome (e.g., "non-empty results", "inconsistency detected").
    actual_result : str | None
        What actually happened.
    error_message : str | None
        Error details if the test failed.

    References
    ----------
    Asprino (2024). "OWLUnit" https://github.com/luigi-asprino/owl-unit
    """

    test_type: OWLUnitTestType
    test_id: str
    passed: bool = False
    description: str = ""
    sparql_query: str | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    error_message: str | None = None


class OWLUnitTestSuite(BaseModel):
    """Aggregated results across multiple OWLUnit test cases.

    Attributes
    ----------
    suite_name : str
        Name of the test suite, e.g. "plan-ontology-75pct-tests".
    ontology_path : str
        Path to the ontology under test.
    results : list[OWLUnitTestResult]
        Individual test results.
    total_tests : int
        Number of tests executed.
    passed_tests : int
        Number of passing tests.
    failed_tests : int
        Number of failing tests.
    pass_rate : float
        ``passed_tests / total_tests``.
    by_type : dict[str, float]
        Pass rate broken down by OWLUnitTestType.
    """

    suite_name: str = ""
    ontology_path: str = ""
    results: list[OWLUnitTestResult] = Field(default_factory=list)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0

    @property
    def pass_rate(self) -> float:
        """Overall pass rate."""
        if self.total_tests == 0:
            return 0.0
        return self.passed_tests / self.total_tests

    @property
    def by_type(self) -> dict[str, float]:
        """Pass rate per test type."""
        from collections import defaultdict
        counts: dict[str, list[bool]] = defaultdict(list)
        for r in self.results:
            counts[r.test_type.value].append(r.passed)
        return {
            tt: (sum(vals) / len(vals)) if vals else 0.0
            for tt, vals in counts.items()
        }


# ---------------------------------------------------------------------------
# External Benchmark Datasets
# ---------------------------------------------------------------------------

class BenchmarkDataset(BaseModel):
    """Reference to an external benchmark dataset for evaluation.

    Attributes
    ----------
    name : str
        Short name, e.g. "OntoURL", "OAEI-LLM", "TamingHallucinations".
    source : str
        Where to obtain it (URL or HuggingFace ID).
    description : str
        What the dataset contains and how it's used.
    license : str
        License identifier (e.g. "CC BY 4.0", "MIT").
    num_samples : int | None
        Number of questions / test items.
    domains : list[str]
        Covered domains (e.g. ["biomedical", "geoscience", ...]).
    paper_reference : str
        APA-style citation.
    tasks : list[str]
        Which evaluation tasks this dataset supports.
    local_path : Path | None
        Local cache path once downloaded.
    """

    name: str
    source: str = ""
    description: str = ""
    license: str = ""
    num_samples: int | None = None
    domains: list[str] = Field(default_factory=list)
    paper_reference: str = ""
    tasks: list[str] = Field(default_factory=list)
    local_path: Path | None = None


# ---------------------------------------------------------------------------
# Metric Scores  (6 dimensions + extended evaluations)
# ---------------------------------------------------------------------------

class MetricScores(BaseModel):
    """Six-dimension evaluation scores for a single system on a single test case.

    Each dimension is normalised to [0, 1] (higher = better), except
    ``hallucination_rate`` where *lower* is better.

    Dimensions
    ----------
    semantic_correctness : float
        Proportion of generated classes/properties that are semantically
        correct w.r.t. the gold standard (embedding cosine ≥ 0.85 OR
        exact label match).  Target: ≥ 0.92.
    hallucination_rate : float
        Proportion of generated elements that have *no* correspondence
        in the gold standard or domain literature.  Target: < 0.05.
    cq_coverage : float
        Fraction of competency questions that become answerable after
        extension (structural + SPARQL check).  Target: > 0.85.
    hierarchy_quality : float
        Normalised depth of the generated class hierarchy, where
        1.0 = gold-standard depth.  Measured as
        ``min(generated_depth, gold_depth) / gold_depth``.  Target: 4–5
        levels → score ≈ 0.8–1.0.
    domain_compliance : float
        Fraction of generated terms/relations that align with domain
        vocabulary (regulatory documents, seed ontology namespace).
        Target: ≥ 0.95.
    expert_acceptance : float
        Fraction of proposals accepted by a human domain expert
        (or simulated expert using LLM rubric).  Target: ≥ 0.87.

    Derived
    -------
    composite_score : float (computed property)
        Weighted average across all six dimensions for a single
        summary number.
    """

    semantic_correctness: float = 0.0
    hallucination_rate: float = 0.0
    cq_coverage: float = 0.0
    hierarchy_quality: float = 0.0
    domain_compliance: float = 0.0
    expert_acceptance: float = 0.0

    # --- Extended evaluations (from integrated frameworks) ---
    semantic_match_concept: SemanticMatchResult | None = None
    semantic_match_triple: SemanticMatchResult | None = None
    ontourl_profile: OntoURLCapabilityProfile | None = None
    owlunit_suite: OWLUnitTestSuite | None = None

    @property
    def composite_score(self) -> float:
        """Weighted composite of all six metrics.

        Weights reflect relative importance for safety-critical
        ontology extension:
          - semantic_correctness  0.25
          - hallucination_rate    0.20  (inverted: 1 − rate)
          - cq_coverage           0.20
          - hierarchy_quality     0.10
          - domain_compliance     0.15
          - expert_acceptance     0.10
        """
        return (
            0.25 * self.semantic_correctness
            + 0.20 * (1.0 - self.hallucination_rate)
            + 0.20 * self.cq_coverage
            + 0.10 * self.hierarchy_quality
            + 0.15 * self.domain_compliance
            + 0.10 * self.expert_acceptance
        )


# ---------------------------------------------------------------------------
# System Configuration
# ---------------------------------------------------------------------------

class BaselineSystemConfig(BaseModel):
    """Configuration for running a baseline system.

    Encapsulates everything needed to invoke a baseline in a
    reproducible way: repo location, entry-point command, Python
    environment, and system-specific parameters.

    Attributes
    ----------
    system : BaselineSystem
        Which baseline this config describes.
    repo_path : Path | None
        Local path to the cloned repository.  ``None`` if the system
        is our own CogAgent (runs in-process).
    repo_url : str
        Git clone URL for reproducibility metadata.
    entry_command : str
        Shell command to execute the baseline, with ``{seed}`` and
        ``{output}`` placeholders for test-case paths.
    python_executable : str
        Path to the Python interpreter inside the baseline's venv.
    env_vars : dict[str, str]
        Extra environment variables the baseline needs.
    timeout_seconds : int
        Maximum wall-clock time before killing the run.
    setup_commands : list[str]
        One-time commands to install / prepare the baseline.
    output_format : str
        Expected output format: ``"owl"``, ``"ttl"``, ``"csv"``, ``"json"``.
    """

    system: BaselineSystem
    repo_path: Path | None = None
    repo_url: str = ""
    entry_command: str = ""
    python_executable: str = "python"
    env_vars: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 3600
    setup_commands: list[str] = Field(default_factory=list)
    output_format: str = "owl"


# ---------------------------------------------------------------------------
# Benchmark Result (per system × per test case)
# ---------------------------------------------------------------------------

class BenchmarkResult(BaseModel):
    """Result of running one system on one test case.

    Captures timing, output artifacts, metric scores, and any errors.

    Attributes
    ----------
    system : BaselineSystem
        Which system produced this result.
    test_case_id : str
        Which test case was evaluated.
    reduction_level : ReductionLevel
        Convenience copy of the test case's reduction level.
    metrics : MetricScores
        The six-dimension evaluation scores.
    wall_clock_seconds : float
        Total execution time in seconds.
    output_ontology_path : Path | None
        Path to the OWL/TTL file produced by the system.
    classes_generated : int
        Number of new classes the system added.
    properties_generated : int
        Number of new properties the system added.
    error : str | None
        Error message if the run failed.
    run_timestamp : datetime
        When the run started.
    raw_output : dict[str, Any]
        System-specific raw output for debugging.
    """

    system: BaselineSystem
    test_case_id: str
    reduction_level: ReductionLevel
    metrics: MetricScores = Field(default_factory=MetricScores)
    wall_clock_seconds: float = 0.0
    output_ontology_path: Path | None = None
    classes_generated: int = 0
    properties_generated: int = 0
    error: str | None = None
    run_timestamp: datetime = Field(default_factory=datetime.now)
    raw_output: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Expert Review (for manual scoring)
# ---------------------------------------------------------------------------

class ProposalReview(BaseModel):
    """Single expert review of one generated proposal.

    Used for the ``expert_acceptance`` metric dimension.

    Attributes
    ----------
    proposal_id : str
        Identifier of the proposal being reviewed.
    proposed_element : str
        The class or property name that was proposed.
    decision : str
        One of ``"accept"``, ``"reject"``, ``"revise"``.
    semantic_score : float
        0.0–1.0 — how semantically correct is the proposal?
    hierarchy_score : float
        0.0–1.0 — is it placed at the right level?
    domain_score : float
        0.0–1.0 — does it align with domain terminology?
    notes : str
        Free-text reviewer notes.
    """

    proposal_id: str
    proposed_element: str
    decision: str = "accept"
    semantic_score: float = 1.0
    hierarchy_score: float = 1.0
    domain_score: float = 1.0
    notes: str = ""


class ExpertReviewSession(BaseModel):
    """A complete expert review session for one system on one test case.

    Attributes
    ----------
    system : BaselineSystem
    test_case_id : str
    reviewer : str
        Name or identifier of the domain expert.
    review_date : str
        ISO-8601 date string.
    reviews : list[ProposalReview]
    acceptance_rate : float
        Computed: accepted / total.
    """

    system: BaselineSystem
    test_case_id: str
    reviewer: str = ""
    review_date: str = ""
    reviews: list[ProposalReview] = Field(default_factory=list)

    @property
    def acceptance_rate(self) -> float:
        """Fraction of proposals accepted."""
        if not self.reviews:
            return 0.0
        accepted = sum(1 for r in self.reviews if r.decision == "accept")
        return accepted / len(self.reviews)


# ---------------------------------------------------------------------------
# Full Benchmark Suite Configuration
# ---------------------------------------------------------------------------

class BenchmarkConfig(BaseModel):
    """Top-level configuration for a complete benchmark suite.

    Ties together: which test cases to run, which systems to compare,
    output directories, and evaluation parameters.

    Attributes
    ----------
    name : str
        Human-readable benchmark name, e.g. ``"plan-ontology-benchmark-v1"``.
    gold_standard_path : Path
        Path to the full reference ontology (plan-ontology-v1.0.owl).
    test_cases : list[TestCase]
        The reduced-ontology test cases to evaluate on.
    systems : list[BaselineSystemConfig]
        Configuration for each system to benchmark.
    output_dir : Path
        Where to write results, charts, and reports.
    embedding_model : str
        Ollama model name for computing semantic similarity embeddings.
    embedding_url : str
        URL of the embedding service (Ollama).
    similarity_threshold : float
        Cosine similarity threshold for semantic correctness matching.
    wandb_enabled : bool
        Whether to log results to Weights & Biases.
    wandb_project : str
        W&B project name for benchmark runs.
    random_seed : int
        For reproducible ontology decomposition.
    """

    name: str = "plan-ontology-benchmark-v1"
    gold_standard_path: Path = Path("data/seed_ontology/plan-ontology-v1.0.owl")
    test_cases: list[TestCase] = Field(default_factory=list)
    systems: list[BaselineSystemConfig] = Field(default_factory=list)
    output_dir: Path = Path("results/benchmarking")
    embedding_model: str = "llama3.2:3b"
    embedding_url: str = "http://localhost:18135"
    similarity_threshold: float = 0.85
    wandb_enabled: bool = True
    wandb_project: str = "ontology-hitl-benchmark"
    random_seed: int = 42

    # --- Extended evaluation settings ---
    external_datasets: list[BenchmarkDataset] = Field(default_factory=list)
    enable_semantic_matching: bool = True
    semantic_match_model: str = "all-MiniLM-L6-v2"
    concept_match_threshold: float = 0.55
    triple_match_threshold: float = 0.50
    enable_ontourl_eval: bool = False
    ontourl_dataset_path: Path | None = None
    enable_owlunit: bool = False
    owlunit_jar_path: Path | None = None
    reference_ontology_paths: list[Path] = Field(default_factory=list)

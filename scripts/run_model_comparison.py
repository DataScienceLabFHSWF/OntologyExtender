#!/usr/bin/env python3
"""Run model comparison experiments across small and large LLMs.

This script extends the base experiment runner to support model-aware
experiments. It runs the full pipeline (7-phase debate + export + evaluation)
with different LLM models, allowing direct comparison of:

- Small non-reasoning models (e.g., llama3.2:3b, 3.2B params)
- Large reasoning models (e.g., qwen3-next, 79.7B params)

Each experiment combination (model × strategy) gets:
- Its own iteration directory:  data/iterations/{model}_{strategy}/
- Its own export directory:     data/exports/{model}_{strategy}/
- A distinct wandb run name:    standalone_{model}_{strategy}_{timestamp}
- Structural metrics computed post-hoc for comparison

Design Rationale
----------------
The key research question is whether reasoning capability in the LLM
changes the effectiveness of different debate strategies. Specifically:

1. Does a reasoning model benefit less from dialectical debate?
   (Hypothesis: reasoning models may self-correct, reducing the value
   of external epistemic pressure.)

2. Does a small model benefit MORE from structured debate strategies?
   (Hypothesis: debate strategies compensate for model limitations,
   acting as "scaffolding" for weaker models.)

3. Which combination produces the best ontology quality?
   (Measured via hierarchy depth, relation density, CQ coverage, and
   structural metrics from the evaluation suite.)

Implementation Plan
-------------------
The implementor should:

1. Extend ExperimentConfig to include a `model` field
2. Extend ExperimentRunner to set HITL_OLLAMA_MODEL env var per experiment
3. Extend ExperimentRunner to also set HITL_LLM_TIMEOUT_SECONDS (larger
   models need more time per LLM call)
4. Compute structural metrics after each experiment via OntologyStructuralMetrics
5. Save per-experiment results with model info to the results JSON
6. Generate a comparison report at the end

Usage
-----
    # Run small model experiments
    python scripts/run_model_comparison.py \\
        --experiments experiments/small_model_experiments.json \\
        --output results/small_model_results.json

    # Run large model experiments
    python scripts/run_model_comparison.py \\
        --experiments experiments/large_model_experiments.json \\
        --output results/large_model_results.json

    # Run all experiments (both models) and generate comparison report
    python scripts/run_model_comparison.py \\
        --run-all \\
        --output results/full_comparison.json \\
        --report results/comparison_report.md

Environment
-----------
The script overrides HITL_OLLAMA_MODEL for each experiment via subprocess
environment. The base .env is NOT modified. This means experiments are
fully isolated and reproducible.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Dict, List, Optional, Set, Tuple

import structlog
from pydantic import BaseModel
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.namespace import XSD

logger = structlog.get_logger(__name__)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ModelExperimentConfig(BaseModel):
    """Configuration for a single model comparison experiment.

    Extends the base ExperimentConfig with model selection and timeout settings.

    Attributes
    ----------
    name : str
        Unique experiment name. Used as directory name for results.
        Convention: {model_short}_{strategy}, e.g. "small_dialectical"
    model : str
        Ollama model identifier, e.g. "llama3.2:3b" or "qwen3-next:latest"
    strategy_overrides : dict
        Phase → strategy mapping. Empty dict = use defaults.
    description : str
        Human-readable explanation of what this experiment tests.
    timeout_seconds : int
        LLM call timeout. Larger models need more time.
        Default 300s for small models, 600s for large.
    temperature : float
        LLM temperature. Lower = more deterministic.
    max_iterations : int
        How many feedback loop iterations to run.
    method : str
        Extension method: "multi_agent" (default) or "llm_only" (bypass debate)
    """

    name: str
    model: str
    ollama_url: str = ""  # Override Ollama endpoint (e.g. gemma4 container on :18134)
    reasoner_enabled: Optional[bool] = None  # None = config default; toggle Reasoner ablation
    seed_ontology_path: str = ""  # Override seed ontology for reproduction benchmarks
    strategy: str = "naive"  # For llm_only method: naive, modular, iterative, adaptive
    strategy_overrides: Dict[str, str] = {}
    description: str = ""
    timeout_seconds: int = 300
    temperature: float = 0.5
    max_iterations: int = 1
    method: str = "multi_agent"


class ModelExperimentResult(BaseModel):
    """Results from a single model comparison experiment.

    Captures both pipeline success/failure and structural ontology metrics.

    Attributes
    ----------
    experiment_name : str
        Matches ModelExperimentConfig.name
    model : str
        Which model was used (for results aggregation)
    model_size_category : str
        "small" or "large" — derived from model name for easy grouping
    strategy_overrides : dict
        What strategy overrides were applied
    success : bool
        Whether the full pipeline completed without error
    error_message : str or None
        Error details if success=False
    execution_time_seconds : float
        Wall-clock time for the full pipeline run
    pipeline_metrics : dict
        Metrics from convergence_report.json (entity_coverage, cq_coverage, etc.)
    structural_metrics : dict
        Post-hoc structural analysis of the generated ontology.
        Keys: class_count, property_count, hierarchy_depth_min/max/median/mean,
              branching_factor_mean, leaf_to_internal_ratio, orphan_classes,
              property_connectivity, axiom_richness
    """

    experiment_name: str
    model: str
    model_size_category: str = ""
    strategy_overrides: Dict[str, str] = {}
    success: bool = False
    error_message: Optional[str] = None
    execution_time_seconds: float = 0.0
    pipeline_metrics: Dict = {}
    structural_metrics: Dict = {}


class ModelComparisonReport(BaseModel):
    """Aggregated comparison report across model sizes.

    Generated after all experiments complete. Contains per-experiment results
    plus cross-model statistical comparisons.

    Attributes
    ----------
    timestamp : str
        ISO format timestamp of report generation
    experiments : list
        All individual experiment results
    small_model_summary : dict
        Aggregated metrics for small model experiments
    large_model_summary : dict
        Aggregated metrics for large model experiments
    comparison : dict
        Head-to-head comparison of key metrics between model sizes
    """

    timestamp: str = ""
    experiments: List[ModelExperimentResult] = []
    small_model_summary: Dict = {}
    large_model_summary: Dict = {}
    comparison: Dict = {}


# ---------------------------------------------------------------------------
# Structural metrics (post-hoc ontology analysis)
# ---------------------------------------------------------------------------

class OntologyStructuralMetrics:
    """Compute structural quality metrics for a generated OWL ontology.

    These metrics directly address the evaluation gaps identified in the
    literature (see docs/EXPERIMENT_PLAN.md):

    - Zhao et al. (ESWC 2025): Triple alignment — we measure relation density
    - Plu et al. (2025): Hierarchy flatness — we measure depth distribution

    The implementor should use rdflib to parse the OWL file and compute
    all metrics. See the method docstrings for exact specifications.

    Usage
    -----
        metrics = OntologyStructuralMetrics("data/exports/small_baseline/ontology_latest.owl")
        results = metrics.compute_all()
        print(results)
        # {'class_count': 25, 'hierarchy_depth_max': 4, ...}
    """

    def __init__(self, owl_path: str, seed_owl_path: str = "data/seed_ontology/plan-ontology-v1.0.owl"):
        """Initialize with path to generated OWL and seed OWL for delta computation.

        Parameters
        ----------
        owl_path : str
            Path to the generated (extended) OWL file.
        seed_owl_path : str
            Path to the original seed ontology for computing deltas.
        """
        self.owl_path = Path(owl_path)
        self.seed_owl_path = Path(seed_owl_path)

    def compute_all(self) -> Dict:
        """Compute all structural metrics and return as a flat dictionary.

        Returns
        -------
        dict
            Keys:
            - class_count: int — total OWL classes in extended ontology
            - class_count_delta: int — new classes added beyond seed
            - property_count: int — total object + datatype properties
            - property_count_delta: int — new properties added beyond seed
            - hierarchy_depth_min: int — shallowest class depth from owl:Thing
            - hierarchy_depth_max: int — deepest class depth from owl:Thing
            - hierarchy_depth_mean: float — average class depth
            - hierarchy_depth_median: float — median class depth
            - hierarchy_depth_stdev: float — standard deviation of depths
            - branching_factor_mean: float — average children per non-leaf class
            - branching_factor_max: int — max children for any class
            - leaf_to_internal_ratio: float — leaf_classes / total_classes
            - orphan_class_count: int — classes with no parent and no children
            - property_connectivity: float — properties / classes ratio
            - classes_with_zero_properties: int — classes that have no properties
            - axiom_count: int — total axioms (disjointness, equivalence, cardinality)
            - disjointness_axioms: int — owl:disjointWith declarations
            - domain_range_completeness: float — properties with both domain and range / total
            - owl_profile: str — detected OWL profile (EL/QL/RL/DL)

        Raises
        ------
        FileNotFoundError
            If the OWL file does not exist.
        """
        if not self.owl_path.exists():
            raise FileNotFoundError(f"OWL file not found: {self.owl_path}")

        # Load both ontologies
        extended_graph = Graph()
        seed_graph = Graph()
        extended_graph.parse(str(self.owl_path), format="xml")
        seed_graph.parse(str(self.seed_owl_path), format="xml")

        # Compute all metrics
        class_metrics = self.compute_class_metrics()
        hierarchy_metrics = self.compute_hierarchy_metrics()
        property_metrics = self.compute_property_metrics()
        axiom_metrics = self.compute_axiom_metrics()

        # Combine into flat dict
        result = {}
        result.update(class_metrics)
        result.update(hierarchy_metrics)
        result.update(property_metrics)
        result.update(axiom_metrics)

        # Add OWL profile detection
        result["owl_profile"] = self._detect_owl_profile(extended_graph)

        return result

    def compute_class_metrics(self) -> Dict:
        """Compute class-level metrics (count, delta from seed).

        Uses rdflib to compare the extended and seed OWL graphs.
        Counts ``owl:Class`` and ``rdfs:Class`` instances, filtering out
        blank nodes and OWL built-in classes.
        """
        extended_graph = Graph()
        seed_graph = Graph()
        extended_graph.parse(str(self.owl_path), format="xml")
        seed_graph.parse(str(self.seed_owl_path), format="xml")

        def get_classes(graph: Graph) -> Set[str]:
            """Get all class URIs from an ontology, filtering out built-ins."""
            classes = set()
            for s in graph.subjects(RDF.type, OWL.Class):
                if isinstance(s, URIRef) and not str(s).startswith("http://www.w3.org/2002/07/owl#"):
                    classes.add(str(s))
            for s in graph.subjects(RDF.type, RDFS.Class):
                if isinstance(s, URIRef) and not str(s).startswith("http://www.w3.org/"):
                    classes.add(str(s))
            return classes

        extended_classes = get_classes(extended_graph)
        seed_classes = get_classes(seed_graph)

        return {
            "class_count": len(extended_classes),
            "class_count_delta": len(extended_classes) - len(seed_classes),
        }

    def compute_hierarchy_metrics(self) -> Dict:
        """Compute hierarchy depth and branching factor metrics.

        Builds a tree from ``rdfs:subClassOf`` edges and runs BFS from
        ``owl:Thing`` to measure depth distribution, branching factors,
        leaf-to-internal ratio, and orphan classes.

        These metrics directly address Plu et al. (2025) finding that
        LLM ontologies are too flat. A good ontology should have:
        - depth_max >= 3 (not flat)
        - branching_factor_mean between 2-5 (not too wide/narrow)
        - leaf_to_internal_ratio < 0.8 (enough intermediate abstractions)
        """
        extended_graph = Graph()
        extended_graph.parse(str(self.owl_path), format="xml")

        # Build class hierarchy: parent -> children
        hierarchy = defaultdict(set)
        children = defaultdict(set)

        for subj, pred, obj in extended_graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(subj, URIRef) and isinstance(obj, URIRef):
                # Skip built-in classes
                if str(subj).startswith("http://www.w3.org/2002/07/owl#"):
                    continue
                if str(obj).startswith("http://www.w3.org/2002/07/owl#"):
                    continue
                hierarchy[str(obj)].add(str(subj))
                children[str(subj)].add(str(obj))

        # Get all classes
        all_classes = set()
        for s in extended_graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef) and not str(s).startswith("http://www.w3.org/2002/07/owl#"):
                all_classes.add(str(s))
        for s in extended_graph.subjects(RDF.type, RDFS.Class):
            if isinstance(s, URIRef) and not str(s).startswith("http://www.w3.org/"):
                all_classes.add(str(s))

        # Compute depths via BFS from owl:Thing
        depths = {}
        visited = set()
        queue = deque([("http://www.w3.org/2002/07/owl#Thing", 0)])

        while queue:
            class_uri, depth = queue.popleft()
            if class_uri in visited:
                continue
            visited.add(class_uri)
            depths[class_uri] = depth

            # Add children
            for child in hierarchy[class_uri]:
                if child not in visited:
                    queue.append((child, depth + 1))

        # Compute depth statistics
        class_depths = [depths[c] for c in all_classes if c in depths]
        if not class_depths:
            class_depths = [0]

        # Compute branching factors
        branching_factors = []
        max_branching = 0
        for parent, childs in hierarchy.items():
            if parent in all_classes:  # Only count for classes in our ontology
                bf = len(childs)
                branching_factors.append(bf)
                max_branching = max(max_branching, bf)

        if not branching_factors:
            branching_factors = [0]

        # Identify leaves and orphans
        leaves = set()
        orphans = set()
        for cls in all_classes:
            if cls not in hierarchy:  # No children
                leaves.add(cls)
            if cls not in children and cls != "http://www.w3.org/2002/07/owl#Thing":  # No parents
                orphans.add(cls)

        return {
            "hierarchy_depth_min": min(class_depths),
            "hierarchy_depth_max": max(class_depths),
            "hierarchy_depth_mean": mean(class_depths),
            "hierarchy_depth_median": median(class_depths),
            "hierarchy_depth_stdev": stdev(class_depths) if len(class_depths) > 1 else 0.0,
            "branching_factor_mean": mean(branching_factors),
            "branching_factor_max": max_branching,
            "leaf_to_internal_ratio": len(leaves) / len(all_classes) if all_classes else 0.0,
            "orphan_class_count": len(orphans),
        }

    def compute_property_metrics(self) -> Dict:
        """Compute property-level metrics (count, connectivity, completeness).

        Counts object and datatype properties, measures property-to-class
        connectivity ratio, domain/range completeness, and identifies classes
        with zero properties.

        These metrics address Zhao et al. (ESWC 2025) finding about
        weak relational modeling in LLM ontologies.
        """
        extended_graph = Graph()
        seed_graph = Graph()
        extended_graph.parse(str(self.owl_path), format="xml")
        seed_graph.parse(str(self.seed_owl_path), format="xml")

        def get_properties(graph: Graph) -> Set[str]:
            """Get all property URIs from an ontology."""
            properties = set()
            for s in graph.subjects(RDF.type, OWL.ObjectProperty):
                if isinstance(s, URIRef):
                    properties.add(str(s))
            for s in graph.subjects(RDF.type, OWL.DatatypeProperty):
                if isinstance(s, URIRef):
                    properties.add(str(s))
            return properties

        extended_props = get_properties(extended_graph)
        seed_props = get_properties(seed_graph)

        # Get all classes for connectivity calculation
        def get_classes(graph: Graph) -> Set[str]:
            classes = set()
            for s in graph.subjects(RDF.type, OWL.Class):
                if isinstance(s, URIRef) and not str(s).startswith("http://www.w3.org/2002/07/owl#"):
                    classes.add(str(s))
            for s in graph.subjects(RDF.type, RDFS.Class):
                if isinstance(s, URIRef) and not str(s).startswith("http://www.w3.org/"):
                    classes.add(str(s))
            return classes

        extended_classes = get_classes(extended_graph)

        # Compute domain/range completeness
        properties_with_domain = set()
        properties_with_range = set()
        properties_with_both = set()

        for prop in extended_props:
            prop_uri = URIRef(prop)
            has_domain = any(extended_graph.triples((prop_uri, RDFS.domain, None)))
            has_range = any(extended_graph.triples((prop_uri, RDFS.range, None)))

            if has_domain:
                properties_with_domain.add(prop)
            if has_range:
                properties_with_range.add(prop)
            if has_domain and has_range:
                properties_with_both.add(prop)

        domain_range_completeness = len(properties_with_both) / len(extended_props) if extended_props else 0.0

        # Find classes with zero properties
        classes_with_properties = set()
        for prop in extended_props:
            prop_uri = URIRef(prop)
            for _, _, domain in extended_graph.triples((prop_uri, RDFS.domain, None)):
                if isinstance(domain, URIRef):
                    classes_with_properties.add(str(domain))

        classes_with_zero_properties = len(extended_classes - classes_with_properties)

        return {
            "property_count": len(extended_props),
            "property_count_delta": len(extended_props) - len(seed_props),
            "property_connectivity": len(extended_props) / len(extended_classes) if extended_classes else 0.0,
            "classes_with_zero_properties": classes_with_zero_properties,
            "domain_range_completeness": domain_range_completeness,
        }

    def compute_axiom_metrics(self) -> Dict:
        """Compute axiom-level metrics (disjointness, equivalence, cardinality).

        Counts ``owl:disjointWith``, ``owl:equivalentClass``, cardinality
        restrictions (``minCardinality``, ``maxCardinality``, etc.), and
        value restrictions (``allValuesFrom``, ``someValuesFrom``).
        """
        extended_graph = Graph()
        extended_graph.parse(str(self.owl_path), format="xml")

        # Count disjointness axioms
        disjointness_count = 0
        for _ in extended_graph.triples((None, OWL.disjointWith, None)):
            disjointness_count += 1

        # Count equivalence axioms
        equivalence_count = 0
        for _ in extended_graph.triples((None, OWL.equivalentClass, None)):
            equivalence_count += 1

        # Count cardinality restrictions
        cardinality_count = 0
        for _ in extended_graph.triples((None, OWL.minCardinality, None)):
            cardinality_count += 1
        for _ in extended_graph.triples((None, OWL.maxCardinality, None)):
            cardinality_count += 1
        for _ in extended_graph.triples((None, OWL.cardinality, None)):
            cardinality_count += 1
        for _ in extended_graph.triples((None, OWL.qualifiedCardinality, None)):
            cardinality_count += 1

        # Count other restrictions
        restriction_count = 0
        for _ in extended_graph.triples((None, OWL.allValuesFrom, None)):
            restriction_count += 1
        for _ in extended_graph.triples((None, OWL.someValuesFrom, None)):
            restriction_count += 1

        total_axioms = disjointness_count + equivalence_count + cardinality_count + restriction_count

        return {
            "axiom_count": total_axioms,
            "disjointness_axioms": disjointness_count,
        }

    def _detect_owl_profile(self, graph: Graph) -> str:
        """Detect the OWL profile (EL/QL/RL/DL) based on constructs used."""
        # Check for OWL DL features (most expressive)
        has_inverse = any(graph.triples((None, OWL.inverseOf, None)))
        has_transitive = any(graph.triples((None, RDF.type, OWL.TransitiveProperty)))
        has_functional = any(graph.triples((None, RDF.type, OWL.FunctionalProperty)))
        has_inverse_functional = any(graph.triples((None, RDF.type, OWL.InverseFunctionalProperty)))
        has_symmetric = any(graph.triples((None, RDF.type, OWL.SymmetricProperty)))

        if has_inverse or has_transitive or has_functional or has_inverse_functional or has_symmetric:
            return "DL"  # OWL Description Logic

        # Check for OWL EL features
        has_existential = any(graph.triples((None, OWL.someValuesFrom, None)))
        has_el_disjoint = any(graph.triples((None, OWL.disjointWith, None)))

        if has_existential or has_el_disjoint:
            return "EL"  # OWL EL

        # Check for OWL QL features
        has_universal = any(graph.triples((None, OWL.allValuesFrom, None)))
        has_cardinality = any(graph.triples((None, OWL.cardinality, None)))

        if has_universal or has_cardinality:
            return "QL"  # OWL QL

        # Default to RL (most restrictive)
        return "RL"  # OWL RL


# ---------------------------------------------------------------------------
# Model-aware experiment runner
# ---------------------------------------------------------------------------

class ModelExperimentRunner:
    """Run experiments with different LLM models and debate strategies.

    This extends the base ExperimentRunner with:
    1. Model override via HITL_OLLAMA_MODEL environment variable
    2. Timeout adjustment for larger models
    3. Post-hoc structural metrics computation
    4. Cross-model comparison report generation

    The runner does NOT modify .env or any source files permanently.
    Model selection happens purely via subprocess environment variables.

    Implementation Plan for the Implementor
    ----------------------------------------
    1. __init__: Set up base_dir, results_dir, create directories
    2. run_single_experiment: The main method. Steps:
       a. Log experiment start
       b. Build environment dict with HITL_OLLAMA_MODEL override
       c. Set HITL_LLM_TIMEOUT_SECONDS based on model size
       d. Call run_full_pipeline.py with the experiment name
       e. On success, compute structural metrics on the output OWL
       f. Return ModelExperimentResult
    3. run_experiment_suite: Loop over configs, call run_single_experiment
    4. generate_comparison_report: Aggregate results, compute summaries
    5. save_results: Write JSON + optional markdown report

    Key Environment Variables Set Per Experiment
    ---------------------------------------------
    HITL_OLLAMA_MODEL — overrides Settings.ollama_model
    HITL_LLM_TIMEOUT_SECONDS — overrides Settings.llm_timeout_seconds
    HITL_LLM_TEMPERATURE — overrides Settings.llm_temperature
    ONTOLOGY_EXPERIMENT_NAME — sets the output directory name
    """

    def __init__(self, base_dir: Path, results_dir: Path):
        """Initialize the model experiment runner.

        Parameters
        ----------
        base_dir : Path
            Root directory of the OntologyExtender project.
        results_dir : Path
            Directory to save experiment results and reports.
        """
        self.base_dir = base_dir
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def run_single_experiment(self, config: ModelExperimentConfig) -> ModelExperimentResult:
        """Run a single experiment with the specified model and strategy.

        This is the core method. It:
        1. Sets up environment variables for model override
        2. Calls the appropriate extension method (multi_agent or llm_only)
        3. Computes structural metrics on the output ontology
        4. Returns a ModelExperimentResult with all data

        Parameters
        ----------
        config : ModelExperimentConfig
            The experiment configuration to run.

        Returns
        -------
        ModelExperimentResult
            Complete results including success/failure, pipeline metrics,
            and structural ontology metrics.

        Implementation Notes
        --------------------
        For multi_agent method:
        - Uses the full pipeline (feedback loop + export + evaluation)
        - Sets HITL_OLLAMA_MODEL, HITL_LLM_TIMEOUT_SECONDS, etc.

        For llm_only method:
        - Bypasses multi-agent debate entirely
        - Calls scripts/llm_only_baseline.py directly
        - Still computes the same structural metrics for comparison
        """
        start_time = time.time()
        logger.info("starting_experiment", experiment=config.name, model=config.model, method=config.method)

        # Determine model size category
        model_size_category = "small" if any(size in config.model.lower() for size in ["3b", "1b", "7b"]) else "large"

        # Initialize result
        experiment_result = ModelExperimentResult(
            experiment_name=config.name,
            model=config.model,
            model_size_category=model_size_category,
            strategy_overrides=config.strategy_overrides,
        )

        try:
            if config.method == "llm_only":
                # Use LLM-only baseline
                success = self._run_llm_only_experiment(config, experiment_result)
            else:
                # Use multi-agent pipeline
                success = self._run_multi_agent_experiment(config, experiment_result)

            experiment_result.success = success

        except Exception as e:
            logger.error("experiment_failed", experiment=config.name, error=str(e))
            experiment_result.success = False
            experiment_result.error_message = str(e)

        execution_time = time.time() - start_time
        experiment_result.execution_time_seconds = execution_time

        logger.info("experiment_completed",
                   experiment=config.name,
                   success=experiment_result.success,
                   execution_time=f"{execution_time:.1f}s")

        return experiment_result

    def _run_multi_agent_experiment(self, config: ModelExperimentConfig, experiment_result: ModelExperimentResult) -> bool:
        """Run a multi-agent experiment using the full pipeline.

        Parameters
        ----------
        config : ModelExperimentConfig
            The experiment configuration.
        experiment_result : ModelExperimentResult
            The result object to populate.

        Returns
        -------
        bool
            True if the experiment succeeded.
        """
        # Build environment variables
        env = os.environ.copy()
        env["HITL_OLLAMA_MODEL"] = config.model
        if config.ollama_url:
            env["HITL_OLLAMA_URL"] = config.ollama_url
        if config.reasoner_enabled is not None:
            env["HITL_REASONER_ENABLED"] = str(config.reasoner_enabled).lower()
        if config.seed_ontology_path:
            env["HITL_SEED_ONTOLOGY_PATH"] = config.seed_ontology_path
        env["HITL_LLM_TIMEOUT_SECONDS"] = str(config.timeout_seconds)
        env["HITL_LLM_TEMPERATURE"] = str(config.temperature)
        env["ONTOLOGY_EXPERIMENT_NAME"] = config.name

        # Run the full pipeline
        try:
            cmd = [sys.executable, "scripts/run_full_pipeline.py", "--experiment-name", config.name]
            result = subprocess.run(
                cmd,
                env=env,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds * 10  # Allow 10x the LLM timeout for the whole pipeline
            )

            success = result.returncode == 0
            error_message = result.stderr if not success else None

        except subprocess.TimeoutExpired:
            success = False
            error_message = f"Pipeline timed out after {config.timeout_seconds * 10}s"
        except Exception as e:
            success = False
            error_message = str(e)

        if success:
            try:
                # Read convergence report for pipeline metrics
                report_path = self.base_dir / "data" / "exports" / config.name / "convergence_report.json"
                if report_path.exists():
                    with open(report_path, 'r') as f:
                        convergence_data = json.load(f)
                        experiment_result.pipeline_metrics = convergence_data

                # Compute structural metrics
                owl_path = self.base_dir / "data" / "exports" / config.name / "ontology_latest.owl"
                if owl_path.exists():
                    structural_metrics = OntologyStructuralMetrics(owl_path).compute_all()
                    experiment_result.structural_metrics = structural_metrics

            except Exception as e:
                logger.warning("failed_to_compute_metrics", experiment=config.name, error=str(e))
                experiment_result.error_message = f"Success but metrics failed: {str(e)}"
        else:
            experiment_result.error_message = error_message

        return success

    def _run_llm_only_experiment(self, config: ModelExperimentConfig, experiment_result: ModelExperimentResult) -> bool:
        """Run an LLM-only experiment using the baseline script.

        Parameters
        ----------
        config : ModelExperimentConfig
            The experiment configuration.
        experiment_result : ModelExperimentResult
            The result object to populate.

        Returns
        -------
        bool
            True if the experiment succeeded.
        """
        # Build environment variables
        env = os.environ.copy()
        env["HITL_OLLAMA_MODEL"] = config.model
        if config.ollama_url:
            env["HITL_OLLAMA_URL"] = config.ollama_url
        if config.reasoner_enabled is not None:
            env["HITL_REASONER_ENABLED"] = str(config.reasoner_enabled).lower()
        if config.seed_ontology_path:
            env["HITL_SEED_ONTOLOGY_PATH"] = config.seed_ontology_path
        env["HITL_LLM_TIMEOUT_SECONDS"] = str(config.timeout_seconds)
        env["HITL_LLM_TEMPERATURE"] = str(config.temperature)

        # Create output directory
        output_dir = self.base_dir / "data" / "exports" / config.name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run the LLM-only baseline script
        try:
            cmd = [
                sys.executable,
                "scripts/llm_only_baseline.py",
                "--model", config.model,
                "--strategy", config.strategy,
                "--output", str(output_dir / "ontology_latest.owl"),
                "--timeout", str(config.timeout_seconds),
                "--temperature", str(config.temperature)
            ]
            result = subprocess.run(
                cmd,
                env=env,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds * 2  # Allow 2x the LLM timeout for the baseline
            )

            success = result.returncode == 0
            error_message = result.stderr if not success else None

        except subprocess.TimeoutExpired:
            success = False
            error_message = f"LLM-only baseline timed out after {config.timeout_seconds * 2}s"
        except Exception as e:
            success = False
            error_message = str(e)

        if success:
            try:
                # Compute structural metrics
                owl_path = output_dir / "ontology_latest.owl"
                if owl_path.exists():
                    structural_metrics = OntologyStructuralMetrics(owl_path).compute_all()
                    experiment_result.structural_metrics = structural_metrics
                else:
                    success = False
                    error_message = "OWL file was not generated"

            except Exception as e:
                logger.warning("failed_to_compute_metrics", experiment=config.name, error=str(e))
                experiment_result.error_message = f"Success but metrics failed: {str(e)}"
        else:
            experiment_result.error_message = error_message

        return success

    def run_experiment_suite(
        self,
        configs: List[ModelExperimentConfig],
    ) -> List[ModelExperimentResult]:
        """Run a suite of experiments sequentially.

        Parameters
        ----------
        configs : list of ModelExperimentConfig
            All experiments to run. Will be executed in order.

        Returns
        -------
        list of ModelExperimentResult
            Results for all experiments (including failed ones).

        Implementation Notes
        --------------------
        - Run experiments sequentially (not parallel) — only one LLM
          server, and large models need all the GPU memory
        - Save intermediate results after each experiment completes
        - Log progress: "Running experiment 3/8: large_dialectical"
        - Handle exceptions gracefully — one failed experiment should
          not abort the entire suite
        """
        results = []
        total_experiments = len(configs)

        for i, config in enumerate(configs, 1):
            logger.info("experiment_progress",
                       current=i,
                       total=total_experiments,
                       experiment=config.name,
                       model=config.model)

            try:
                result = self.run_single_experiment(config)
                results.append(result)

                # Save intermediate results
                intermediate_path = self.results_dir / f"intermediate_results_{i}.json"
                with open(intermediate_path, 'w') as f:
                    json.dump([r.model_dump() for r in results], f, indent=2)

            except Exception as e:
                logger.error("experiment_failed_critical",
                           experiment=config.name,
                           error=str(e))
                # Create a failed result
                failed_result = ModelExperimentResult(
                    experiment_name=config.name,
                    model=config.model,
                    success=False,
                    error_message=f"Critical failure: {str(e)}",
                    execution_time_seconds=0.0,
                )
                results.append(failed_result)

        logger.info("experiment_suite_completed",
                   total_experiments=total_experiments,
                   successful_experiments=sum(1 for r in results if r.success))

        return results

    def generate_comparison_report(
        self,
        results: List[ModelExperimentResult],
    ) -> ModelComparisonReport:
        """Generate a cross-model comparison report from experiment results.

        Groups results by model_size_category ("small" vs "large") and
        computes aggregated statistics for each group.

        Parameters
        ----------
        results : list of ModelExperimentResult
            All completed experiment results.

        Returns
        -------
        ModelComparisonReport
            Aggregated report with per-group summaries and comparison.

        Implementation Notes
        --------------------
        The comparison dict should contain:
        - "class_count_delta": large_avg - small_avg
        - "hierarchy_depth_max_delta": large_avg - small_avg
        - "property_connectivity_delta": large_avg - small_avg
        - "execution_time_ratio": large_avg / small_avg
        - "strategy_impact_small": best_strategy - baseline for small model
        - "strategy_impact_large": best_strategy - baseline for large model

        Per-group summary should contain:
        - avg/min/max of each structural metric
        - best_strategy (highest class_count + hierarch_depth_max)
        - success_rate
        """
        # Separate results by model size
        small_results = [r for r in results if r.model_size_category == "small" and r.success]
        large_results = [r for r in results if r.model_size_category == "large" and r.success]

        def compute_group_summary(group_results: List[ModelExperimentResult]) -> Dict:
            """Compute summary statistics for a group of results."""
            if not group_results:
                return {}

            # Extract structural metrics
            class_counts = [r.structural_metrics.get("class_count_delta", 0) for r in group_results]
            hierarchy_depths = [r.structural_metrics.get("hierarchy_depth_max", 0) for r in group_results]
            property_connectivities = [r.structural_metrics.get("property_connectivity", 0) for r in group_results]
            execution_times = [r.execution_time_seconds for r in group_results]

            # Find best strategy (highest combined score)
            strategy_scores = {}
            for r in group_results:
                score = r.structural_metrics.get("class_count_delta", 0) + r.structural_metrics.get("hierarchy_depth_max", 0)
                strategy = list(r.strategy_overrides.values())[0] if r.strategy_overrides else "baseline"
                strategy_scores[strategy] = max(strategy_scores.get(strategy, 0), score)

            best_strategy = max(strategy_scores.items(), key=lambda x: x[1])[0] if strategy_scores else "none"

            return {
                "count": len(group_results),
                "success_rate": len(group_results) / len([r for r in results if r.model_size_category == group_results[0].model_size_category]),
                "class_count_delta_avg": mean(class_counts) if class_counts else 0,
                "class_count_delta_min": min(class_counts) if class_counts else 0,
                "class_count_delta_max": max(class_counts) if class_counts else 0,
                "hierarchy_depth_max_avg": mean(hierarchy_depths) if hierarchy_depths else 0,
                "hierarchy_depth_max_min": min(hierarchy_depths) if hierarchy_depths else 0,
                "hierarchy_depth_max_max": max(hierarchy_depths) if hierarchy_depths else 0,
                "property_connectivity_avg": mean(property_connectivities) if property_connectivities else 0,
                "execution_time_avg": mean(execution_times) if execution_times else 0,
                "best_strategy": best_strategy,
            }

        small_summary = compute_group_summary(small_results)
        large_summary = compute_group_summary(large_results)

        # Compute comparison metrics
        comparison = {}
        if small_summary and large_summary:
            comparison["class_count_delta_delta"] = large_summary.get("class_count_delta_avg", 0) - small_summary.get("class_count_delta_avg", 0)
            comparison["hierarchy_depth_max_delta"] = large_summary.get("hierarchy_depth_max_avg", 0) - small_summary.get("hierarchy_depth_max_avg", 0)
            comparison["property_connectivity_delta"] = large_summary.get("property_connectivity_avg", 0) - small_summary.get("property_connectivity_avg", 0)
            comparison["execution_time_ratio"] = large_summary.get("execution_time_avg", 0) / small_summary.get("execution_time_avg", 0) if small_summary.get("execution_time_avg", 0) > 0 else 0

            # Strategy impact (best - baseline)
            small_baseline = next((r.structural_metrics.get("class_count_delta", 0) for r in small_results if not r.strategy_overrides), 0)
            large_baseline = next((r.structural_metrics.get("class_count_delta", 0) for r in large_results if not r.strategy_overrides), 0)

            small_best = max((r.structural_metrics.get("class_count_delta", 0) for r in small_results), default=0)
            large_best = max((r.structural_metrics.get("class_count_delta", 0) for r in large_results), default=0)

            comparison["strategy_impact_small"] = small_best - small_baseline
            comparison["strategy_impact_large"] = large_best - large_baseline

        return ModelComparisonReport(
            timestamp=datetime.now().isoformat(),
            experiments=results,
            small_model_summary=small_summary,
            large_model_summary=large_summary,
            comparison=comparison,
        )

    def save_results(
        self,
        results: List[ModelExperimentResult],
        output_path: Path,
        report_path: Optional[Path] = None,
    ) -> None:
        """Save experiment results as JSON and optionally as a markdown report.

        Parameters
        ----------
        results : list of ModelExperimentResult
            All experiment results.
        output_path : Path
            Where to save the JSON results file.
        report_path : Path, optional
            Where to save a human-readable markdown comparison report.

        Implementation Notes
        --------------------
        JSON format: List of ModelExperimentResult.model_dump()
        Markdown format should include:
        - Table of all experiments with key metrics
        - Small vs Large model comparison summary
        - Winner per metric
        - Strategy effectiveness ranking per model size
        """
        # Save JSON results
        json_data = [result.model_dump() for result in results]
        with open(output_path, 'w') as f:
            json.dump(json_data, f, indent=2)

        logger.info("saved_json_results", path=str(output_path))

        if report_path:
            # Generate and save markdown report
            comparison_report = self.generate_comparison_report(results)
            markdown_content = self._generate_markdown_report(comparison_report)
            with open(report_path, 'w') as f:
                f.write(markdown_content)

            logger.info("saved_markdown_report", path=str(report_path))

    def _generate_markdown_report(self, report: ModelComparisonReport) -> str:
        """Generate a human-readable markdown comparison report."""
        lines = []
        lines.append("# Model Comparison Experiment Report")
        lines.append(f"**Generated:** {report.timestamp}")
        lines.append("")

        # Summary table
        lines.append("## Experiment Summary")
        lines.append("")
        lines.append("| Experiment | Model | Size | Strategy | Success | Classes Added | Max Depth | Time (s) |")
        lines.append("|------------|-------|------|----------|---------|---------------|-----------|----------|")

        for exp in report.experiments:
            strategy = list(exp.strategy_overrides.values())[0] if exp.strategy_overrides else "baseline"
            classes_added = exp.structural_metrics.get("class_count_delta", 0) if exp.success else 0
            max_depth = exp.structural_metrics.get("hierarchy_depth_max", 0) if exp.success else 0
            time_str = f"{exp.execution_time_seconds:.1f}" if exp.success else "N/A"

            lines.append(f"| {exp.experiment_name} | {exp.model} | {exp.model_size_category} | {strategy} | {'✓' if exp.success else '✗'} | {classes_added} | {max_depth} | {time_str} |")

        lines.append("")

        # Small model summary
        if report.small_model_summary:
            lines.append("## Small Model Summary")
            lines.append("")
            s = report.small_model_summary
            lines.append(f"- **Experiments:** {s.get('count', 0)} successful")
            lines.append(f"- **Success Rate:** {s.get('success_rate', 0):.1%}")
            lines.append(f"- **Classes Added:** {s.get('class_count_delta_avg', 0):.1f} avg ({s.get('class_count_delta_min', 0)} - {s.get('class_count_delta_max', 0)})")
            lines.append(f"- **Max Hierarchy Depth:** {s.get('hierarchy_depth_max_avg', 0):.1f} avg")
            lines.append(f"- **Best Strategy:** {s.get('best_strategy', 'none')}")
            lines.append(f"- **Avg Execution Time:** {s.get('execution_time_avg', 0):.1f}s")
            lines.append("")

        # Large model summary
        if report.large_model_summary:
            lines.append("## Large Model Summary")
            lines.append("")
            l = report.large_model_summary
            lines.append(f"- **Experiments:** {l.get('count', 0)} successful")
            lines.append(f"- **Success Rate:** {l.get('success_rate', 0):.1%}")
            lines.append(f"- **Classes Added:** {l.get('class_count_delta_avg', 0):.1f} avg ({l.get('class_count_delta_min', 0)} - {l.get('class_count_delta_max', 0)})")
            lines.append(f"- **Max Hierarchy Depth:** {l.get('hierarchy_depth_max_avg', 0):.1f} avg")
            lines.append(f"- **Best Strategy:** {l.get('best_strategy', 'none')}")
            lines.append(f"- **Avg Execution Time:** {l.get('execution_time_avg', 0):.1f}s")
            lines.append("")

        # Comparison
        if report.comparison:
            lines.append("## Model Comparison")
            lines.append("")
            c = report.comparison
            lines.append(f"- **Classes Added Delta:** Large +{c.get('class_count_delta_delta', 0):.1f} vs Small")
            lines.append(f"- **Hierarchy Depth Delta:** Large +{c.get('hierarchy_depth_max_delta', 0):.1f} vs Small")
            lines.append(f"- **Property Connectivity Delta:** Large {c.get('property_connectivity_delta', 0):+.2f} vs Small")
            lines.append(f"- **Execution Time Ratio:** Large is {c.get('execution_time_ratio', 0):.1f}x slower than Small")
            lines.append(f"- **Strategy Impact (Small):** +{c.get('strategy_impact_small', 0):.1f} classes from best strategy")
            lines.append(f"- **Strategy Impact (Large):** +{c.get('strategy_impact_large', 0):.1f} classes from best strategy")
            lines.append("")

        # Failed experiments
        failed = [r for r in report.experiments if not r.success]
        if failed:
            lines.append("## Failed Experiments")
            lines.append("")
            for r in failed:
                lines.append(f"- **{r.experiment_name}:** {r.error_message}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for model comparison experiments.

    Usage:
        # Run experiments from a config file
        python scripts/run_model_comparison.py \\
            --experiments experiments/small_model_experiments.json \\
            --output results/small_model_results.json

        # Run ALL experiments (both small and large model)
        python scripts/run_model_comparison.py \\
            --run-all \\
            --output results/full_comparison.json \\
            --report results/comparison_report.md

    Implementation Notes
    --------------------
    The implementor should:
    1. Parse arguments (--experiments, --run-all, --output, --report)
    2. If --run-all: Load both small and large experiment configs
    3. Instantiate ModelExperimentRunner
    4. Call run_experiment_suite for each config set
    5. Call generate_comparison_report
    6. Call save_results
    7. Print summary to stdout
    """
    parser = argparse.ArgumentParser(
        description="Run model comparison experiments for ontology extension"
    )
    parser.add_argument(
        "--experiments", type=str,
        help="Path to experiment config JSON file"
    )
    parser.add_argument(
        "--run-all", action="store_true",
        help="Run all experiments (small + large model)"
    )
    parser.add_argument(
        "--output", type=str, default="results/model_comparison_results.json",
        help="Path to save results JSON"
    )
    parser.add_argument(
        "--report", type=str, default=None,
        help="Path to save markdown comparison report"
    )
    args = parser.parse_args()

    # Determine base directory
    base_dir = Path(__file__).parent.parent

    # Load experiment configurations
    if args.run_all:
        small_config_path = base_dir / "experiments" / "small_model_experiments.json"
        large_config_path = base_dir / "experiments" / "large_model_experiments.json"

        if not small_config_path.exists() or not large_config_path.exists():
            print("Error: --run-all requires both experiment config files:")
            print(f"  {small_config_path}")
            print(f"  {large_config_path}")
            sys.exit(1)

        with open(small_config_path, 'r') as f:
            small_configs = [ModelExperimentConfig(**exp) for exp in json.load(f)]

        with open(large_config_path, 'r') as f:
            large_configs = [ModelExperimentConfig(**exp) for exp in json.load(f)]

        all_configs = small_configs + large_configs
        print(f"Running all experiments: {len(small_configs)} small + {len(large_configs)} large = {len(all_configs)} total")

    elif args.experiments:
        config_path = Path(args.experiments)
        if not config_path.exists():
            print(f"Error: Experiment config file not found: {config_path}")
            sys.exit(1)

        with open(config_path, 'r') as f:
            all_configs = [ModelExperimentConfig(**exp) for exp in json.load(f)]

        print(f"Running {len(all_configs)} experiments from {config_path}")

    else:
        print("Model comparison experiments")
        print()
        print("Usage:")
        print("  # Run specific experiment config")
        print("  python scripts/run_model_comparison.py --experiments experiments/small_model_experiments.json")
        print()
        print("  # Run all experiments (small + large models)")
        print("  python scripts/run_model_comparison.py --run-all --output results/full_comparison.json")
        print()
        print("Available experiment configs:")
        print("  small_model_experiments.json  (llama3.2:3b, 4 experiments)")
        print("  large_model_experiments.json  (qwen3-next, 4 experiments)")
        sys.exit(0)

    # Set up results directory
    results_dir = Path(args.output).parent
    results_dir.mkdir(parents=True, exist_ok=True)

    # Initialize runner and run experiments
    runner = ModelExperimentRunner(base_dir=base_dir, results_dir=results_dir)

    print(f"Starting experiment suite with {len(all_configs)} experiments...")
    start_time = time.time()

    results = runner.run_experiment_suite(all_configs)

    total_time = time.time() - start_time
    successful = sum(1 for r in results if r.success)

    print(f"\nCompleted in {total_time:.1f}s")
    print(f"Results: {successful}/{len(results)} experiments successful")

    # Save results
    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else None

    runner.save_results(results, output_path, report_path)

    print(f"\nResults saved to: {output_path}")
    if report_path:
        print(f"Report saved to: {report_path}")

    # Print summary
    if successful > 0:
        small_results = [r for r in results if r.model_size_category == "small" and r.success]
        large_results = [r for r in results if r.model_size_category == "large" and r.success]

        if small_results:
            avg_classes_small = mean(r.structural_metrics.get("class_count_delta", 0) for r in small_results)
            print(f"  Small model: {avg_classes_small:.1f} classes added avg")
        if large_results:
            avg_classes_large = mean(r.structural_metrics.get("class_count_delta", 0) for r in large_results)
            print(f"  Large model: {avg_classes_large:.1f} classes added avg")

        if small_results and large_results:
            delta = avg_classes_large - avg_classes_small
            print(f"  Large vs Small delta: {delta:+.1f} classes")


if __name__ == "__main__":
    main()

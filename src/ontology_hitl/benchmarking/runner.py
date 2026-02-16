"""Benchmark runner: orchestrates all phases of a benchmark suite.

Coordinates the end-to-end benchmarking workflow:
  1. Generate test cases (ontology decomposition)
  2. Run each system on each test case
  3. Evaluate outputs with the six-dimension scorer
  4. Aggregate results into comparison tables
  5. Run statistical significance tests
  6. Generate publication-ready reports

The runner supports:
  - Sequential or parallel system execution
  - Resumption from checkpoints (skip already-completed runs)
  - W&B experiment tracking
  - Configurable subsets (e.g., run only CogAgent + LLM4ACOE)

Usage
-----
::

    from ontology_hitl.benchmarking.runner import BenchmarkRunner
    from ontology_hitl.benchmarking.models import BenchmarkConfig

    config = BenchmarkConfig.model_validate_json(Path("benchmark_config.json").read_text())
    runner = BenchmarkRunner(config)
    runner.run_all()

Dependencies
------------
- All submodules in ``ontology_hitl.benchmarking``
- ``structlog`` for logging
- ``wandb`` for experiment tracking (optional)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

from .aggregator import ResultsAggregator
from .baselines import BaselineAdapter, create_adapter
from .metrics import BenchmarkEvaluator
from .models import (
    BaselineSystem,
    BaselineSystemConfig,
    BenchmarkConfig,
    BenchmarkResult,
    MetricScores,
    ReductionLevel,
    TestCase,
)
from .reporting import ReportGenerator
from .statistics import StatisticalAnalyzer
from .test_cases import TestCaseGenerator

logger = structlog.get_logger(__name__)


class BenchmarkRunner:
    """End-to-end orchestrator for a benchmark suite.

    Parameters
    ----------
    config : BenchmarkConfig
        Full benchmark configuration: which test cases, which systems,
        output directories, evaluation parameters.
    skip_existing : bool
        If True, skip systems/test-cases that already have results
        in ``config.output_dir``.  Enables incremental runs.
    parallel : bool
        If True, run different systems in parallel threads.
        (Test cases within one system are always sequential.)

    Attributes
    ----------
    aggregator : ResultsAggregator
        Accumulates results as runs complete.
    evaluator : BenchmarkEvaluator
        Computes the six-dimension scores.
    stats : StatisticalAnalyzer
        Significance testing after all runs finish.
    reporter : ReportGenerator
        Produces charts and tables.
    """

    def __init__(
        self,
        config: BenchmarkConfig,
        skip_existing: bool = True,
        parallel: bool = False,
    ) -> None:
        self.config = config
        self.skip_existing = skip_existing
        self.parallel = parallel

        self.aggregator = ResultsAggregator(output_dir=config.output_dir)
        self.evaluator = BenchmarkEvaluator(
            embedding_url=config.embedding_url,
            embedding_model=config.embedding_model,
            similarity_threshold=config.similarity_threshold,
            semantic_embedding_model=getattr(config, 'semantic_embedding_model', None),
        )
        self.stats = StatisticalAnalyzer()
        self.reporter = ReportGenerator(
            output_dir=config.output_dir / "reports",
        )

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def run_all(self) -> dict[str, Any]:
        """Execute the full benchmark pipeline.

        Phases
        ------
        1. **Generate test cases**: decompose gold-standard into
           4 reduction levels (or load existing test cases).
        2. **Setup baselines**: run one-time setup for each system.
        3. **Execute runs**: for each (system × test_case), invoke the
           adapter and collect raw output.
        4. **Evaluate**: score each output with the 6-dimension evaluator.
        5. **Aggregate**: build comparison tables.
        6. **Statistical analysis**: significance testing.
        7. **Report**: generate charts, LaTeX tables, Markdown summary.

        Returns
        -------
        dict[str, Any]
            Summary structure with keys:
              - ``"master_table"``   — systems × metrics dict
              - ``"ranking"``        — per-metric winner
              - ``"significance"``   — statistical report dict
              - ``"reports"``        — dict of generated file paths
              - ``"total_time_seconds"`` — wall-clock time

        Raises
        ------
        RuntimeError
            If no system is available to run.
        """
        start = time.time()
        # Phase 1: test cases
        test_cases = self.generate_test_cases()
        if not test_cases:
            raise RuntimeError("No test cases available; generate or provide test_cases in config.")

        # Phase 2: setup baselines
        adapters = self.setup_baselines()
        if not adapters:
            logger.warning("no_adapters_available", msg="No baseline adapters available after setup")

        all_results: list[BenchmarkResult] = []

        # Phase 3: execute runs sequentially (per adapter)
        for system, adapter in adapters.items():
            logger.info("running_system", system=system.value)
            results = self.run_system_on_all_cases(adapter, test_cases)
            all_results.extend(results)
            # Save intermediate aggregation
            self.aggregator.add_results(results)

        # Phase 4: aggregate & report
        report = self.aggregate_and_report()

        total_time = time.time() - start
        return {"master_table": report.get("master_table", {}), "reports": report.get("reports", {}), "total_time_seconds": total_time}


    # ------------------------------------------------------------------
    # Phase 1: Test Case Generation
    # ------------------------------------------------------------------

    def generate_test_cases(self) -> list[TestCase]:
        """Generate or load test cases.

        If ``config.test_cases`` is non-empty, uses those directly.
        Otherwise, runs the ``TestCaseGenerator`` to decompose
        ``config.gold_standard_path``.

        Returns
        -------
        list[TestCase]
            Four test cases at 50/75/90/95 % reduction.
        """
        if self.config.test_cases:
            return self.config.test_cases
        # fallback: attempt to generate via TestCaseGenerator if implemented
        try:
            gen = TestCaseGenerator(
                gold_standard_path=self.config.gold_standard_path,
                output_dir=self.config.output_dir / "test_cases",
                random_seed=self.config.random_seed,
            )
            cases = gen.generate_all()
            return cases
        except Exception:
            # As a graceful fallback create a single minimal test case
            logger.warning("test_case_generation_fallback", msg="Using single smoke test case")
            tc = TestCase(
                id=f"{self.config.name}-smoke",
                reduction_level=ReductionLevel.PCT_75,
                seed_ontology_path=self.config.gold_standard_path,
                gold_standard_path=self.config.gold_standard_path,
                removed_classes=[],
                removed_properties=[],
                competency_questions=[],
                num_original_classes=0,
                num_remaining_classes=0,
            )
            return [tc]

    # ------------------------------------------------------------------
    # Phase 2: Baseline Setup
    # ------------------------------------------------------------------

    def setup_baselines(self) -> dict[BaselineSystem, BaselineAdapter]:
        """Instantiate and set up all configured baseline adapters.

        For each system in ``config.systems``:
          1. Create the adapter via ``create_adapter()``.
          2. Call ``adapter.setup()`` (clone, install deps).
          3. Verify ``adapter.is_available()``.

        Returns
        -------
        dict[BaselineSystem, BaselineAdapter]
            Mapped adapters, excluding any that failed setup.
        """
        adapters: dict[BaselineSystem, BaselineAdapter] = {}
        for sys_cfg in self.config.systems:
            try:
                adapter = create_adapter(sys_cfg)
                # run setup if any commands
                try:
                    adapter.setup()
                except NotImplementedError:
                    pass
                except Exception as e:
                    logger.warning("adapter_setup_failed", system=sys_cfg.system.value, error=str(e))
                    continue
                try:
                    if adapter.is_available():
                        adapters[sys_cfg.system] = adapter
                    else:
                        logger.warning("adapter_not_available", system=sys_cfg.system.value)
                except Exception as e:
                    logger.warning("adapter_is_available_failed", system=sys_cfg.system.value, error=str(e))
            except Exception as e:
                logger.warning("create_adapter_failed", system=getattr(sys_cfg, 'system', None), error=str(e))
                continue
        return adapters

    # ------------------------------------------------------------------
    # Phase 3: Execution
    # ------------------------------------------------------------------

    def run_system_on_all_cases(
        self,
        adapter: BaselineAdapter,
        test_cases: list[TestCase],
    ) -> list[BenchmarkResult]:
        """Run one system on all test cases sequentially.

        Parameters
        ----------
        adapter : BaselineAdapter
        test_cases : list[TestCase]

        Returns
        -------
        list[BenchmarkResult]
            One result per test case.
        """
        results: list[BenchmarkResult] = []
        for tc in test_cases:
            try:
                res = self.run_single(adapter, tc)
                results.append(res)
            except Exception as e:
                logger.exception("run_system_test_case_failed", system=adapter.config.system.value, test_case=tc.id, error=str(e))
        return results

    def run_single(
        self,
        adapter: BaselineAdapter,
        test_case: TestCase,
    ) -> BenchmarkResult:
        """Run one system on one test case and evaluate the output.

        Steps
        -----
        1. Check for existing checkpoint (``skip_existing``).
        2. Call ``adapter.run(test_case)`` → raw result.
        3. Call ``evaluator.evaluate_all()`` → metric scores.
        4. Update result with scores.
        5. Save checkpoint JSON to ``output_dir``.

        Parameters
        ----------
        adapter : BaselineAdapter
        test_case : TestCase

        Returns
        -------
        BenchmarkResult
            Complete result with metrics.
        """
        # Checkpoint skip
        existing = self._load_checkpoint(adapter.config.system, test_case.id)
        if existing and self.skip_existing:
            logger.info("checkpoint_loaded", system=adapter.config.system.value, test_case=test_case.id)
            return existing

        start = time.time()
        result = None
        try:
            result = adapter.run(test_case)
        except NotImplementedError:
            # Adapter not implemented — return an error result placeholder
            br = BenchmarkResult(
                system=adapter.config.system,
                test_case_id=test_case.id,
                reduction_level=test_case.reduction_level,
                wall_clock_seconds=0.0,
                error="adapter_run_not_implemented",
            )
            self._save_checkpoint(br)
            return br
        except Exception as e:
            br = BenchmarkResult(
                system=adapter.config.system,
                test_case_id=test_case.id,
                reduction_level=test_case.reduction_level,
                wall_clock_seconds=time.time() - start,
                error=str(e),
            )
            self._save_checkpoint(br)
            return br

        # Ensure wall clock and output path are present
        result.wall_clock_seconds = getattr(result, "wall_clock_seconds", time.time() - start)
        # Evaluate if output exists
        if result.output_ontology_path:
            try:
                result = self.evaluate_result(result, test_case)
            except Exception as e:
                result.error = f"evaluation_failed: {e}"
        else:
            result.error = result.error or "no_output_generated"

        # Save checkpoint
        self._save_checkpoint(result)
        return result

    # ------------------------------------------------------------------
    # Phase 4: Evaluation (handled by evaluator)
    # ------------------------------------------------------------------

    def evaluate_result(
        self, result: BenchmarkResult, test_case: TestCase
    ) -> BenchmarkResult:
        """Compute metric scores for a raw result.

        Parameters
        ----------
        result : BenchmarkResult
            Must have ``output_ontology_path`` set.
        test_case : TestCase

        Returns
        -------
        BenchmarkResult
            Same result with ``metrics`` populated.
        """
        if not result.output_ontology_path:
            raise ValueError("Result has no output_ontology_path to evaluate")
        scores = self.evaluator.evaluate_all(result.output_ontology_path, test_case)
        result.metrics = scores
        return result

    # ------------------------------------------------------------------
    # Phase 5–7: Aggregation, Statistics, Reporting
    # ------------------------------------------------------------------

    def aggregate_and_report(self) -> dict[str, Any]:
        """Aggregate all results, run stats, generate reports.

        Called after all runs complete (or on cached results).

        Returns
        -------
        dict[str, Any]
            Combined output of aggregator, stats, and reporter.
        """
        master = self.aggregator.build_master_table()
        # Run simple statistics (placeholder)
        stats = self.stats.run(self.aggregator.results) if hasattr(self.stats, 'run') else {}
        reports = {}
        try:
            reports = self.reporter.render(master) if hasattr(self.reporter, 'render') else {}
        except Exception:
            reports = {}
        return {"master_table": master, "statistics": stats, "reports": reports}

    # ------------------------------------------------------------------
    # Checkpointing
    # ------------------------------------------------------------------

    def _save_checkpoint(self, result: BenchmarkResult) -> Path:
        """Save a single result as a JSON checkpoint file.

        Parameters
        ----------
        result : BenchmarkResult

        Returns
        -------
        Path
            Path to the checkpoint file.

        File naming
        -----------
        ``{output_dir}/{system}_{test_case_id}_result.json``
        """
        fname = f"{result.system.value}_{result.test_case_id}_result.json"
        outdir = Path(self.config.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / fname
        path.write_text(result.model_dump_json(indent=2))
        return path

    def _load_checkpoint(
        self, system: BaselineSystem, test_case_id: str
    ) -> BenchmarkResult | None:
        """Load a checkpoint if it exists.

        Parameters
        ----------
        system : BaselineSystem
        test_case_id : str

        Returns
        -------
        BenchmarkResult | None
            The loaded result, or ``None`` if no checkpoint exists.
        """
        fname = Path(self.config.output_dir) / f"{system.value}_{test_case_id}_result.json"
        if not fname.exists():
            return None
        try:
            data = json.loads(fname.read_text())
            return BenchmarkResult.model_validate(data)
        except Exception as e:
            logger.warning("load_checkpoint_failed", file=str(fname), error=str(e))
            return None

    # ------------------------------------------------------------------
    # W&B Integration
    # ------------------------------------------------------------------

    def _init_wandb(self) -> None:
        """Initialise a W&B run for the benchmark suite.

        Creates a run with:
          - Name: ``config.name``
          - Project: ``config.wandb_project``
          - Config: full BenchmarkConfig as dict
          - Tags: system names, reduction levels

        No-op if ``config.wandb_enabled`` is False.
        """
        try:
            import wandb
        except Exception:
            return
        if not getattr(self.config, "wandb_enabled", False):
            return
        wandb.init(project=self.config.wandb_project, name=self.config.name, config=self.config.model_dump())
        logger.info("wandb_initialized", project=self.config.wandb_project)

    def _log_result_to_wandb(self, result: BenchmarkResult) -> None:
        try:
            import wandb
        except Exception:
            return
        if not getattr(self.config, "wandb_enabled", False):
            return
        metrics = result.metrics.model_dump()
        wandb.log({f"{result.system.value}/{result.test_case_id}/{k}": v for k, v in metrics.items()})
        logger.info("wandb_logged", system=result.system.value, test_case=result.test_case_id)

    def _log_result_to_wandb(self, result: BenchmarkResult) -> None:
        """Log a single result's metrics to W&B.

        Parameters
        ----------
        result : BenchmarkResult
        """
        raise NotImplementedError(
            "TODO: wandb.log with system/test_case prefix"
        )


# =========================================================================
# Convenience function
# =========================================================================

def run_benchmark_from_config(config_path: str | Path) -> dict[str, Any]:
    """Load a benchmark config from JSON and execute the full suite.

    This is the simplest way to run a complete benchmark:

    Parameters
    ----------
    config_path : str | Path
        Path to a JSON file conforming to ``BenchmarkConfig`` schema.

    Returns
    -------
    dict[str, Any]
        Full results summary from ``BenchmarkRunner.run_all()``.

    Examples
    --------
    >>> results = run_benchmark_from_config("benchmark_config.json")
    >>> print(results["master_table"]["cogagent"]["composite_score"])
    0.89
    """
    config_data = json.loads(Path(config_path).read_text())
    config = BenchmarkConfig.model_validate(config_data)
    runner = BenchmarkRunner(config)
    return runner.run_all()

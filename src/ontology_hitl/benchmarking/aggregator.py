"""Results aggregator: collect, merge, and tabulate cross-system benchmark results.

This module gathers ``BenchmarkResult`` objects from all systems across
all test cases and produces:
  - Master comparison table (systems × metrics)
  - Per-reduction-level comparison tables
  - Ranking tables (which system wins on each dimension)
  - Delta tables (CogAgent improvement vs. each baseline)

Output formats: JSON, CSV, Markdown, and pandas DataFrames.

Usage
-----
::

    from ontology_hitl.benchmarking.aggregator import ResultsAggregator

    agg = ResultsAggregator(output_dir="results/benchmarking")
    agg.add_result(cogagent_result_75pct)
    agg.add_result(llm4acoe_result_75pct)
    agg.add_result(agent_om_result_75pct)
    agg.add_result(nlp_w2v_result_75pct)

    master_table = agg.build_master_table()
    agg.export_all()

References
----------
- BENCHMARKING_STRATEGY.md §Phase 3: Concrete Benchmark Table
- BENCHMARKING_EXECUTIVE_SUMMARY.md §Master Comparison Table
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import structlog

from .models import (
    BaselineSystem,
    BenchmarkResult,
    MetricScores,
    ReductionLevel,
)

logger = structlog.get_logger(__name__)


class ResultsAggregator:
    """Collect and tabulate benchmark results across systems and test cases.

    Parameters
    ----------
    output_dir : str | Path
        Directory for exported tables and JSON files.

    Attributes
    ----------
    results : list[BenchmarkResult]
        All accumulated results.
    """

    def __init__(self, output_dir: str | Path = "results/benchmarking") -> None:
        self.output_dir = Path(output_dir)
        self.results: list[BenchmarkResult] = []

    # ------------------------------------------------------------------
    # Adding results
    # ------------------------------------------------------------------

    def add_result(self, result: BenchmarkResult) -> None:
        """Add a single benchmark result.

        Parameters
        ----------
        result : BenchmarkResult
        """
        self.results.append(result)
        logger.info(
            "result_added",
            system=result.system.value,
            test_case=result.test_case_id,
            composite=result.metrics.composite_score,
        )

    def add_results(self, results: list[BenchmarkResult]) -> None:
        """Add multiple benchmark results at once.

        Parameters
        ----------
        results : list[BenchmarkResult]
        """
        for r in results:
            self.add_result(r)

    def load_results_from_dir(self, results_dir: str | Path) -> None:
        """Load previously saved BenchmarkResult JSON files from a directory.

        Scans for ``*_result.json`` files and deserialises them.

        Parameters
        ----------
        results_dir : str | Path
            Directory containing JSON result files.
        """
        raise NotImplementedError(
            "TODO: glob for *_result.json, json.load each, "
            "BenchmarkResult.model_validate(data)"
        )

    # ------------------------------------------------------------------
    # Table builders
    # ------------------------------------------------------------------

    def build_master_table(self) -> dict[str, dict[str, float]]:
        """Build the master comparison table: systems × metrics.

        Aggregates across all reduction levels (mean of each metric
        per system).

        Returns
        -------
        dict[str, dict[str, float]]
            Outer key: system name.  Inner key: metric name.
            Example::

                {
                    "cogagent": {
                        "semantic_correctness": 0.92,
                        "hallucination_rate": 0.03,
                        ...
                        "composite_score": 0.89
                    },
                    "llm4acoe": { ... },
                }

        Raises
        ------
        ValueError
            If no results have been added.
        """
        raise NotImplementedError(
            "TODO: group results by system, average metrics across test cases"
        )

    def build_per_level_table(
        self, level: ReductionLevel
    ) -> dict[str, dict[str, float]]:
        """Build comparison table for a single reduction level.

        Parameters
        ----------
        level : ReductionLevel
            Filter results to this reduction level only.

        Returns
        -------
        dict[str, dict[str, float]]
            Same structure as ``build_master_table()``.
        """
        raise NotImplementedError(
            "TODO: filter results by level, then aggregate per system"
        )

    def build_ranking_table(self) -> dict[str, str]:
        """Determine which system wins on each metric dimension.

        Returns
        -------
        dict[str, str]
            Metric name → winning system name.
            Example: ``{"semantic_correctness": "cogagent", ...}``
        """
        raise NotImplementedError(
            "TODO: for each metric, find system with best average score"
        )

    def build_delta_table(
        self, reference_system: BaselineSystem = BaselineSystem.LLM4ACOE,
    ) -> dict[str, dict[str, float]]:
        """Compute CogAgent's improvement over a reference baseline.

        Parameters
        ----------
        reference_system : BaselineSystem
            The baseline to compare against (default: LLM4ACOE as it
            is the closest comparable system).

        Returns
        -------
        dict[str, dict[str, float]]
            Outer key: metric name.
            Inner keys: ``"cogagent"``, ``"reference"``, ``"delta"``,
            ``"improvement_pct"``.
            Example::

                {
                    "semantic_correctness": {
                        "cogagent": 0.92,
                        "reference": 0.70,
                        "delta": 0.22,
                        "improvement_pct": 31.4
                    }
                }
        """
        raise NotImplementedError(
            "TODO: compute per-metric delta between cogagent and reference"
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_all(self) -> dict[str, Path]:
        """Export all tables to JSON, CSV, and Markdown files.

        Creates the following files in ``output_dir``:
          - ``master_comparison.json``
          - ``master_comparison.csv``
          - ``master_comparison.md``
          - ``per_level_50pct.json``  (and 75/90/95)
          - ``ranking.json``
          - ``delta_vs_llm4acoe.json``
          - ``all_results.json``   (raw results for reproducibility)

        Returns
        -------
        dict[str, Path]
            Mapping from file description to path.
        """
        raise NotImplementedError(
            "TODO: call each build_* method, serialise to multiple formats"
        )

    def to_markdown(self, table: dict[str, dict[str, float]]) -> str:
        """Convert a comparison table to a Markdown-formatted string.

        Parameters
        ----------
        table : dict[str, dict[str, float]]
            Systems × metrics table.

        Returns
        -------
        str
            Markdown table suitable for README or paper draft.

        Example Output
        --------------
        ::

            | System   | Semantic | Halluc. | CQ Cov. | Hier. | Domain | Expert | Composite |
            |----------|----------|---------|---------|-------|--------|--------|-----------|
            | CogAgent | 0.92     | 0.03    | 0.87    | 0.85  | 0.95   | 0.88   | 0.89      |
            | LLM4ACOE | 0.70     | 0.15    | 0.78    | 0.40  | 0.60   | 0.65   | 0.65      |
        """
        raise NotImplementedError(
            "TODO: build markdown table string from dict"
        )

    def to_csv(self, table: dict[str, dict[str, float]], path: Path) -> None:
        """Write a comparison table to a CSV file.

        Parameters
        ----------
        table : dict[str, dict[str, float]]
        path : Path
        """
        raise NotImplementedError(
            "TODO: csv.DictWriter with system as first column"
        )

    def to_json(self, data: Any, path: Path) -> None:
        """Write data to a JSON file with pretty formatting.

        Parameters
        ----------
        data : Any
            JSON-serialisable data.
        path : Path
        """
        raise NotImplementedError(
            "TODO: json.dump with indent=2"
        )

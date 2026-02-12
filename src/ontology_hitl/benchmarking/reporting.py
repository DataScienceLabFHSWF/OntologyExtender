"""Report generator: publication-ready tables, charts, and LaTeX fragments.

Produces visual and textual outputs for inclusion in papers and
presentations:
  - Radar / spider charts comparing systems across 6 dimensions
  - Bar charts per metric per reduction level
  - Heatmaps (systems × metrics × reduction levels)
  - LaTeX table fragments for direct paper insertion
  - Markdown summaries for README / documentation

Usage
-----
::

    from ontology_hitl.benchmarking.reporting import ReportGenerator

    gen = ReportGenerator(output_dir="results/benchmarking/reports")
    gen.generate_all(aggregator)

Dependencies
------------
- ``matplotlib`` for charts
- ``pandas``     for DataFrame manipulation (optional)

References
----------
- BENCHMARKING_QUICKSTART.md §Step 3: Generate Comparison Charts
- BENCHMARKING_STRATEGY.md §How to Report Results
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from .aggregator import ResultsAggregator
from .models import BenchmarkResult, MetricScores, ReductionLevel
from .statistics import StatisticalAnalyzer

logger = structlog.get_logger(__name__)

# Metric display names and short labels for charts
_METRIC_DISPLAY = {
    "semantic_correctness": ("Semantic Correctness", "Semantic"),
    "hallucination_rate": ("Hallucination Rate", "Halluc."),
    "cq_coverage": ("CQ Coverage", "CQ Cov."),
    "hierarchy_quality": ("Hierarchy Quality", "Hierarchy"),
    "domain_compliance": ("Domain Compliance", "Domain"),
    "expert_acceptance": ("Expert Acceptance", "Expert"),
    "composite_score": ("Composite Score", "Composite"),
}

# System display names and colors for charts
_SYSTEM_COLORS = {
    "cogagent": ("#2196F3", "CogAgent (Ours)"),
    "agent_om": ("#FF9800", "Agent-OM"),
    "llm4acoe": ("#4CAF50", "LLM4ACOE"),
    "nlp_w2v": ("#9C27B0", "NLP-W2V"),
}


class ReportGenerator:
    """Generate publication-ready reports from benchmark results.

    Parameters
    ----------
    output_dir : str | Path
        Directory for generated charts and tables.
    dpi : int
        Resolution for saved chart images.
    figure_format : str
        Image format: ``"png"``, ``"pdf"``, ``"svg"``.
    """

    def __init__(
        self,
        output_dir: str | Path = "results/benchmarking/reports",
        dpi: int = 300,
        figure_format: str = "png",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.dpi = dpi
        self.figure_format = figure_format

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def generate_all(self, aggregator: ResultsAggregator) -> dict[str, Path]:
        """Generate all report artefacts from aggregated results.

        Produces:
          - Radar chart (``radar_comparison.{fmt}``)
          - Per-metric bar charts (``bar_{metric}.{fmt}``)
          - Heatmap (``heatmap_all.{fmt}``)
          - LaTeX table (``comparison_table.tex``)
          - Markdown summary (``comparison_summary.md``)
          - Statistical report (``statistical_report.json``)

        Parameters
        ----------
        aggregator : ResultsAggregator
            Contains all collected results.

        Returns
        -------
        dict[str, Path]
            Mapping from artefact name to file path.
        """
        raise NotImplementedError(
            "TODO: call each generate_* method, collect output paths"
        )

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------

    def generate_radar_chart(
        self, master_table: dict[str, dict[str, float]]
    ) -> Path:
        """Generate a radar / spider chart comparing all systems.

        Each axis is one of the six metric dimensions.  Each system
        is a polygon overlaid on the same chart.  Hallucination rate
        is plotted as (1 - rate) so all axes point "outward = better".

        Parameters
        ----------
        master_table : dict[str, dict[str, float]]
            From ``aggregator.build_master_table()``.

        Returns
        -------
        Path
            Path to saved chart file.

        Notes
        -----
        Radar charts are effective for showing that CogAgent dominates
        on most dimensions while acknowledging where baselines are
        competitive.
        """
        raise NotImplementedError(
            "TODO: matplotlib polar plot with one polygon per system"
        )

    def generate_bar_charts(
        self,
        master_table: dict[str, dict[str, float]],
    ) -> list[Path]:
        """Generate grouped bar charts — one per metric dimension.

        Each chart shows all systems side-by-side for one metric,
        with error bars if per-level data is available.

        Parameters
        ----------
        master_table : dict[str, dict[str, float]]

        Returns
        -------
        list[Path]
            Paths to each saved chart (6 files).
        """
        raise NotImplementedError(
            "TODO: for each metric, create bar chart with system bars"
        )

    def generate_heatmap(
        self,
        per_level_tables: dict[ReductionLevel, dict[str, dict[str, float]]],
    ) -> Path:
        """Generate a heatmap: (system × metric) cells, one per reduction level.

        Colour intensity indicates score magnitude.  Useful for
        identifying where systems degrade as difficulty increases.

        Parameters
        ----------
        per_level_tables : dict[ReductionLevel, dict[str, dict[str, float]]]
            One table per reduction level.

        Returns
        -------
        Path
            Path to saved heatmap image.
        """
        raise NotImplementedError(
            "TODO: matplotlib imshow or seaborn heatmap"
        )

    def generate_difficulty_curve(
        self,
        results: list[BenchmarkResult],
    ) -> Path:
        """Generate line charts showing each system's performance
        degradation as reduction level increases (50 → 75 → 90 → 95 %).

        One line per system, X-axis = reduction level, Y-axis = metric.
        Creates one chart per metric dimension.

        Parameters
        ----------
        results : list[BenchmarkResult]
            All results across systems and levels.

        Returns
        -------
        Path
            Path to saved multi-panel figure.

        Notes
        -----
        This chart is the most compelling for showing CogAgent's
        robustness under increasing difficulty — if CogAgent degrades
        more slowly than baselines, it demonstrates the value of
        debate + HITL.
        """
        raise NotImplementedError(
            "TODO: group by system × level, plot line for each system"
        )

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def generate_latex_table(
        self, master_table: dict[str, dict[str, float]]
    ) -> Path:
        """Generate a LaTeX table fragment for direct paper insertion.

        Produces a ``\\begin{table}...\\end{table}`` block with
        proper formatting, bold best-values, and a caption.

        Parameters
        ----------
        master_table : dict[str, dict[str, float]]

        Returns
        -------
        Path
            Path to ``.tex`` file.

        Example Output
        --------------
        ::

            \\begin{table}[t]
            \\centering
            \\caption{Performance comparison on Plan-Ontology benchmark.}
            \\begin{tabular}{l|cccccc|c}
            \\toprule
            System & Sem. & Hal. & CQ & Hier. & Dom. & Exp. & Comp. \\\\
            \\midrule
            CogAgent & \\textbf{0.92} & \\textbf{0.03} & ... \\\\
            LLM4ACOE & 0.70 & 0.15 & ... \\\\
            ...
            \\bottomrule
            \\end{tabular}
            \\end{table}
        """
        raise NotImplementedError(
            "TODO: format LaTeX table, bold best per column"
        )

    def generate_markdown_summary(
        self,
        aggregator: ResultsAggregator,
        statistical_report: dict[str, Any] | None = None,
    ) -> Path:
        """Generate a comprehensive Markdown summary report.

        Includes:
          - Executive summary (1-paragraph overview)
          - Master comparison table
          - Per-metric analysis paragraphs
          - Statistical significance callouts
          - Key takeaways and limitations

        Parameters
        ----------
        aggregator : ResultsAggregator
        statistical_report : dict[str, Any] | None
            Output from ``StatisticalAnalyzer.full_significance_report()``.

        Returns
        -------
        Path
            Path to ``.md`` file.
        """
        raise NotImplementedError(
            "TODO: build markdown with tables, bullet points, and narrative"
        )

    # ------------------------------------------------------------------
    # W&B Integration
    # ------------------------------------------------------------------

    def log_to_wandb(
        self,
        aggregator: ResultsAggregator,
        project: str = "ontology-hitl-benchmark",
    ) -> None:
        """Log benchmark results and charts to Weights & Biases.

        Creates a W&B run with:
          - Summary metrics table
          - All chart images as W&B artifacts
          - Per-system metric histories
          - Comparison tables as W&B tables

        Parameters
        ----------
        aggregator : ResultsAggregator
        project : str
            W&B project name.

        Notes
        -----
        Requires ``wandb`` to be installed and authenticated.
        """
        raise NotImplementedError(
            "TODO: wandb.init, wandb.log, wandb.Table for comparison"
        )

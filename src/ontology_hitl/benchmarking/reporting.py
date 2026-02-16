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
import json

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
    # Extended evaluations (displayed when available)
    "semantic_match_concept": ("Semantic Match (Concept)", "SemMatchC"),
    "semantic_match_triple": ("Semantic Match (Triple)", "SemMatchT"),
    "owlunit_pass_rate": ("OWLUnit Pass Rate", "OWLUnit"),
    "ontourl_overall": ("OntoURL Overall", "OntoURL"),
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
        """Generate basic report artefacts from aggregated results.

        Currently implements a minimal, dependency-free report set:
          - ``master_comparison.json``
          - ``master_comparison.md``

        More advanced charts remain optional and can be added later.
        """
        outdir = Path(self.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        master = aggregator.build_master_table()
        json_path = outdir / "master_comparison.json"
        md_path = outdir / "master_comparison.md"
        # write JSON
        json_path.write_text(json.dumps(master, indent=2))
        # write markdown summary (simple table)
        if master:
            cols = list(next(iter(master.values())).keys())
            header = "| System | " + " | ".join(cols) + " |\n"
            sep = "|---" + "|---" * len(cols) + "|\n"
            rows = [header, sep]
            for sys in sorted(master.keys()):
                vals = master[sys]
                row = f"| {sys} | " + " | ".join(f"{vals.get(c, 0.0):.3f}" for c in cols) + " |\n"
                rows.append(row)
            md_path.write_text("".join(rows))

        # Optional: generate charts if matplotlib is available
        outputs: dict[str, Path] = {"master_json": json_path, "master_md": md_path}
        radar_path = None
        bar_paths: list[Path] | None = None
        try:
            radar = self.generate_radar_chart(master)
            outputs["radar_chart"] = radar
            radar_path = radar
        except Exception:
            radar_path = None
        try:
            bars = self.generate_bar_charts(master)
            outputs["bar_charts"] = bars
            bar_paths = bars
        except Exception:
            bar_paths = None

        # Generate a small HTML summary that embeds the charts and table
        html_path = outdir / "master_comparison.html"
        try:
            html_lines = [
                "<html>",
                "<head><meta charset=\"utf-8\"><title>Benchmark master comparison</title></head>",
                "<body>",
                "<h1>Master comparison</h1>",
            ]
            # insert markdown table as HTML
            if master:
                cols = list(next(iter(master.values())).keys())
                html_lines.append("<table border=\"1\" cellpadding=\"6\">")
                # header
                html_lines.append("<tr><th>System</th>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>")
                for sys in sorted(master.keys()):
                    vals = master[sys]
                    html_lines.append(
                        "<tr><td>" + sys + "</td>" + "".join(f"<td>{vals.get(c, 0.0):.3f}</td>" for c in cols) + "</tr>"
                    )
                html_lines.append("</table>")

            # embed radar chart and bar charts if available
            if radar_path:
                html_lines.append(f"<h2>Capability radar</h2><img src=\"{radar_path.name}\" alt=\"radar\" style=\"max-width:800px;\">")
            if bar_paths:
                html_lines.append("<h2>Per-metric bar charts</h2>")
                for bp in bar_paths:
                    html_lines.append(f"<img src=\"{bp.name}\" alt=\"{bp.stem}\" style=\"max-width:48%;margin:6px;\">")

            html_lines.append("</body></html>")
            html_path.write_text("\n".join(html_lines))
            outputs["master_html"] = html_path
        except Exception:
            pass

        return outputs

    def render(self, master_table: dict[str, dict[str, float]]) -> dict[str, Path]:
        """Render a minimal set of report artefacts from a master table.

        Kept deliberately simple so runner.aggregate_and_report() can
        call this without heavy plotting dependencies.
        """
        outdir = Path(self.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        json_path = outdir / "master_comparison.json"
        md_path = outdir / "master_comparison.md"
        json_path.write_text(json.dumps(master_table, indent=2))
        # reuse simple markdown generator
        if master_table:
            cols = list(next(iter(master_table.values())).keys())
            header = "| System | " + " | ".join(cols) + " |\n"
            sep = "|---" + "|---" * len(cols) + "|\n"
            rows = [header, sep]
            for sys in sorted(master_table.keys()):
                vals = master_table[sys]
                row = f"| {sys} | " + " | ".join(f"{vals.get(c, 0.0):.3f}" for c in cols) + " |\n"
                rows.append(row)
            md_path.write_text("".join(rows))
        return {"master_json": json_path, "master_md": md_path}

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------

    def generate_radar_chart(
        self, master_table: dict[str, dict[str, float]]
    ) -> Path:
        """Generate a radar / spider chart comparing all systems.

        Falls back gracefully if `matplotlib` is not installed.
        """
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except Exception as e:
            raise RuntimeError("matplotlib is required to generate charts") from e

        # Use the six primary metrics (plot hallucination as 1 - rate)
        axes = [
            "semantic_correctness",
            "hallucination_rate",
            "cq_coverage",
            "hierarchy_quality",
            "domain_compliance",
            "expert_acceptance",
        ]
        labels = [
            _METRIC_DISPLAY[a][1] if a in _METRIC_DISPLAY else a for a in axes
        ]
        N = len(axes)
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        for system, vals in master_table.items():
            # prepare values and clamp to [0,1]
            v = []
            for a in axes:
                x = float(vals.get(a, 0.0) or 0.0)
                if a == "hallucination_rate":
                    x = 1.0 - x
                v.append(max(0.0, min(1.0, x)))
            v += v[:1]
            ax.plot(angles, v, label=_SYSTEM_COLORS.get(system, ("#666666", system))[1])
            ax.fill(angles, v, alpha=0.15)

        ax.set_thetagrids(np.degrees(angles[:-1]), labels)
        ax.set_ylim(0, 1)
        ax.set_title("Benchmark capability profile", y=1.08)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
        outdir = Path(self.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"radar_profile.{self.figure_format}"
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        return path

    def generate_bar_charts(
        self,
        master_table: dict[str, dict[str, float]],
    ) -> list[Path]:
        """Generate grouped bar charts — one per metric dimension.

        Returns saved file paths.
        """
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except Exception as e:
            raise RuntimeError("matplotlib is required to generate charts") from e

        metrics = [
            "semantic_correctness",
            "hallucination_rate",
            "cq_coverage",
            "hierarchy_quality",
            "domain_compliance",
            "expert_acceptance",
        ]
        systems = sorted(master_table.keys())
        n = len(systems)
        paths: list[Path] = []
        for metric in metrics:
            fig, ax = plt.subplots(figsize=(6, 3))
            vals = [
                max(0.0, min(1.0, (1.0 - master_table[s][metric]) if metric == "hallucination_rate" else master_table[s].get(metric, 0.0)))
                for s in systems
            ]
            x = np.arange(len(systems))
            bars = ax.bar(x, vals, color=[_SYSTEM_COLORS.get(s, ("#666666", s))[0] for s in systems])
            ax.set_ylim(0, 1)
            ax.set_xticks(x)
            ax.set_xticklabels([_SYSTEM_COLORS.get(s, (None, s))[1] for s in systems], rotation=45, ha="right")
            ax.set_ylabel(_METRIC_DISPLAY.get(metric, (metric, metric))[0])
            ax.set_title(f"{_METRIC_DISPLAY.get(metric, (metric, metric))[0]} by system")
            for rect, v in zip(bars, vals):
                ax.text(rect.get_x() + rect.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
            outdir = Path(self.output_dir)
            outdir.mkdir(parents=True, exist_ok=True)
            filepath = outdir / f"bar_{metric}.{self.figure_format}"
            fig.tight_layout()
            fig.savefig(filepath, dpi=self.dpi)
            plt.close(fig)
            paths.append(filepath)
        return paths

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

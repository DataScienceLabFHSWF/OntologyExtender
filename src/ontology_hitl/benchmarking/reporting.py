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
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except Exception as e:
            raise RuntimeError("matplotlib is required to generate charts") from e

        metrics = [
            "semantic_correctness", "hallucination_rate", "cq_coverage",
            "hierarchy_quality", "domain_compliance", "expert_acceptance",
        ]

        levels = sorted(per_level_tables.keys(), key=lambda lv: lv.value)
        if not levels:
            raise ValueError("No per-level data to plot")

        # Determine systems from first level
        first_table = per_level_tables[levels[0]]
        systems = sorted(first_table.keys())
        n_levels = len(levels)
        n_metrics = len(metrics)
        n_systems = len(systems)

        fig, axes = plt.subplots(
            1, n_levels, figsize=(5 * n_levels, max(3, 0.6 * n_systems * n_metrics)),
            squeeze=False,
        )

        for col, level in enumerate(levels):
            ax = axes[0][col]
            table = per_level_tables.get(level, {})
            data = np.zeros((n_systems, n_metrics))
            for si, sys in enumerate(systems):
                for mi, met in enumerate(metrics):
                    v = table.get(sys, {}).get(met, 0.0)
                    if met == "hallucination_rate":
                        v = 1.0 - v  # invert for colour consistency
                    data[si, mi] = max(0.0, min(1.0, v))

            im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
            ax.set_xticks(range(n_metrics))
            ax.set_xticklabels(
                [_METRIC_DISPLAY.get(m, (m, m))[1] for m in metrics],
                rotation=45, ha="right", fontsize=8,
            )
            ax.set_yticks(range(n_systems))
            ax.set_yticklabels(
                [_SYSTEM_COLORS.get(s, (None, s))[1] for s in systems],
                fontsize=8,
            )
            ax.set_title(f"Reduction {level.value}", fontsize=10)
            # annotate cells
            for si in range(n_systems):
                for mi in range(n_metrics):
                    ax.text(mi, si, f"{data[si, mi]:.2f}", ha="center", va="center", fontsize=7)

        fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.6, label="Score")
        fig.suptitle("Performance heatmap (systems × metrics per reduction level)", fontsize=12)

        outdir = Path(self.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"heatmap.{self.figure_format}"
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        return path

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
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except Exception as e:
            raise RuntimeError("matplotlib is required to generate charts") from e

        metrics = [
            "semantic_correctness", "hallucination_rate", "cq_coverage",
            "hierarchy_quality", "domain_compliance", "expert_acceptance",
        ]

        # Group by system and level
        level_order = [ReductionLevel.PCT_50, ReductionLevel.PCT_75,
                       ReductionLevel.PCT_90, ReductionLevel.PCT_95]
        level_labels = ["50%", "75%", "90%", "95%"]

        by_system: dict[str, dict[str, list[float]]] = {}
        for r in results:
            sys_name = r.system.value
            if sys_name not in by_system:
                by_system[sys_name] = {m: [] for m in metrics}
            for m in metrics:
                by_system[sys_name][m].append(
                    (r.reduction_level, getattr(r.metrics, m, 0.0))
                )

        n_metrics = len(metrics)
        fig, axes = plt.subplots(2, 3, figsize=(15, 8))
        axes_flat = axes.ravel()

        for mi, metric in enumerate(metrics):
            ax = axes_flat[mi]
            for sys_name in sorted(by_system.keys()):
                # Average per level
                level_vals: dict[str, list[float]] = {lv.value: [] for lv in level_order}
                for lv, val in by_system[sys_name].get(metric, []):
                    if lv.value in level_vals:
                        level_vals[lv.value].append(val)
                means = []
                for lv in level_order:
                    vs = level_vals.get(lv.value, [])
                    means.append(sum(vs) / max(1, len(vs)) if vs else 0.0)
                color = _SYSTEM_COLORS.get(sys_name, ("#666666", sys_name))[0]
                label = _SYSTEM_COLORS.get(sys_name, (None, sys_name))[1]
                ax.plot(level_labels, means, marker="o", color=color, label=label)

            ax.set_title(_METRIC_DISPLAY.get(metric, (metric, metric))[0], fontsize=10)
            ax.set_xlabel("Reduction level")
            ax.set_ylabel("Score")
            ax.set_ylim(0, 1)
            ax.legend(fontsize=7)
            ax.grid(alpha=0.3)

        fig.suptitle("Performance degradation by reduction level", fontsize=14)
        fig.tight_layout(rect=[0, 0, 1, 0.96])

        outdir = Path(self.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"difficulty_curve.{self.figure_format}"
        fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        return path

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
        metrics = [
            "semantic_correctness", "hallucination_rate", "cq_coverage",
            "hierarchy_quality", "domain_compliance", "expert_acceptance",
            "composite_score",
        ]
        short_labels = ["Sem.", "Hal.", "CQ", "Hier.", "Dom.", "Exp.", "Comp."]
        systems = sorted(master_table.keys())

        # Find best per column (for bold formatting)
        bests: dict[str, str] = {}
        for mi, m in enumerate(metrics):
            best_sys = None
            best_val = float("-inf")
            for s in systems:
                v = master_table[s].get(m, 0.0)
                cmp = -v if m == "hallucination_rate" else v
                if cmp > best_val:
                    best_val = cmp
                    best_sys = s
            if best_sys:
                bests[m] = best_sys

        col_spec = "l|" + "c" * (len(metrics) - 1) + "|c"
        lines = [
            "\\begin{table}[t]",
            "\\centering",
            "\\caption{Performance comparison on Plan-Ontology benchmark.}",
            f"\\begin{{tabular}}{{{col_spec}}}",
            "\\toprule",
            "System & " + " & ".join(short_labels) + " \\\\",
            "\\midrule",
        ]

        for s in systems:
            display_name = _SYSTEM_COLORS.get(s, (None, s))[1]
            vals = master_table[s]
            cells = []
            for m in metrics:
                v = vals.get(m, 0.0)
                formatted = f"{v:.2f}"
                if bests.get(m) == s:
                    formatted = f"\\textbf{{{formatted}}}"
                cells.append(formatted)
            lines.append(f"{display_name} & " + " & ".join(cells) + " \\\\")

        lines.extend([
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ])

        outdir = Path(self.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / "comparison_table.tex"
        path.write_text("\n".join(lines))
        return path

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
        master = aggregator.build_master_table()
        systems = sorted(master.keys())

        lines: list[str] = [
            "# Benchmark Comparison Report\n",
            "## Executive Summary\n",
        ]

        if systems:
            best_composite = max(systems, key=lambda s: master[s].get("composite_score", 0))
            lines.append(
                f"Across {len(aggregator.results)} evaluation runs, "
                f"**{_SYSTEM_COLORS.get(best_composite, (None, best_composite))[1]}** "
                f"achieved the highest composite score "
                f"({master[best_composite].get('composite_score', 0):.3f}).\n"
            )

        # Master table
        lines.append("\n## Master Comparison Table\n")
        lines.append(aggregator.to_markdown(master))

        # Per-metric analysis
        lines.append("\n## Per-Metric Analysis\n")
        ranking = aggregator.build_ranking_table()
        for metric, winner in ranking.items():
            display = _METRIC_DISPLAY.get(metric, (metric, metric))[0]
            lines.append(f"- **{display}**: Best system = {winner}")
        lines.append("")

        # Statistical significance
        if statistical_report:
            lines.append("\n## Statistical Significance\n")
            overall = statistical_report.get("overall", {})
            lines.append(
                f"- Test cases: {overall.get('n_test_cases', 'N/A')}\n"
                f"- Significance level: α = {overall.get('alpha', 0.05)}\n"
                f"- Any significant differences: {overall.get('any_significant', False)}\n"
            )
            per_metric = statistical_report.get("per_metric", {})
            for metric, data in per_metric.items():
                display = _METRIC_DISPLAY.get(metric, (metric, metric))[0]
                sig = "✅" if data.get("significant") else "❌"
                lines.append(
                    f"- **{display}**: p={data.get('p_value', 'N/A'):.4f} {sig}, "
                    f"Cohen's d={data.get('cohens_d', 0):.2f} ({data.get('effect_size', 'N/A')}), "
                    f"improvement={data.get('improvement_pct', 0):.1f}%"
                )
            lines.append("")

        # Key takeaways
        lines.append("\n## Key Takeaways\n")
        lines.append("- Results are preliminary; more test cases improve statistical power.")
        lines.append("- Hallucination rate and expert acceptance require careful interpretation.")
        lines.append("")

        outdir = Path(self.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / "benchmark_report.md"
        path.write_text("\n".join(lines))
        return path

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
        try:
            import wandb
        except ImportError:
            logger.warning("wandb_not_installed", msg="pip install wandb to enable W&B logging")
            return

        master = aggregator.build_master_table()

        run = wandb.init(project=project, name="benchmark-report", reinit=True)
        if run is None:
            return

        # Log master table as W&B Table
        if master:
            cols = ["system"] + list(next(iter(master.values())).keys())
            wb_table = wandb.Table(columns=cols)
            for system, vals in sorted(master.items()):
                wb_table.add_data(system, *[vals.get(c, 0.0) for c in cols[1:]])
            wandb.log({"master_comparison": wb_table})

        # Log summary metrics
        for system, vals in master.items():
            for metric, value in vals.items():
                wandb.log({f"{system}/{metric}": value})

        # Log chart images if they exist
        outdir = Path(self.output_dir)
        for chart_name in ["radar_profile", "heatmap", "difficulty_curve"]:
            for ext in ("png", "pdf", "svg"):
                chart_path = outdir / f"{chart_name}.{ext}"
                if chart_path.exists():
                    wandb.log({chart_name: wandb.Image(str(chart_path))})
                    break

        wandb.finish()
        logger.info("wandb_report_logged", project=project)

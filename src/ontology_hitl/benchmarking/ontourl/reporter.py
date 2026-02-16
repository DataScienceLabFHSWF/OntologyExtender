"""Results aggregation, comparison tables, and charting for OntoURL.

Generates publication-ready comparison tables (Markdown, CSV) and
optional visualisations comparing our models against OntoURL's
published baselines.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from ontology_hitl.benchmarking.models import (
    OntoURLCapability,
    OntoURLCapabilityProfile,
    OntoURLTask,
    OntoURLTaskScore,
)
from .loader import SPLIT_TASK_MAP

logger = structlog.get_logger(__name__)


# ── OntoURL published baselines (from Table 2 in the paper) ─────────

PUBLISHED_BASELINES: dict[str, dict[str, float]] = {
    "Qwen2.5-3B": {
        "U1": 77.8, "U2": 86.3, "U3": 73.6, "U4": 69.2, "U5": 76.4,
        "R1": 64.1, "R2": 66.5, "R3": 58.2, "R4": 47.5, "R5": 50.6,
        "L1": 12.6, "L2": 0.1, "L3": 0.0, "L4": 0.2, "L5": 6.7,
    },
    "Qwen2.5-72B": {
        "U1": 89.1, "U2": 92.8, "U3": 82.4, "U4": 82.6, "U5": 86.9,
        "R1": 79.5, "R2": 79.8, "R3": 72.5, "R4": 60.4, "R5": 64.0,
        "L1": 19.7, "L2": 0.1, "L3": 0.0, "L4": 0.1, "L5": 1.6,
    },
    "LLaMA3.3-70B": {
        "U1": 88.0, "U2": 91.5, "U3": 81.3, "U4": 81.8, "U5": 85.7,
        "R1": 78.2, "R2": 78.1, "R3": 70.8, "R4": 58.1, "R5": 62.5,
        "L1": 18.3, "L2": 0.1, "L3": 0.0, "L4": 0.1, "L5": 1.3,
    },
}


class OntoURLReporter:
    """Aggregate results and generate comparison reports.

    Parameters
    ----------
    output_dir : Path
        Directory for output files.
    """

    def __init__(self, output_dir: Path | str = "results/ontourl") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_predictions(
        self,
        predictions: list[dict[str, Any]],
        model: str,
        strategy: str,
        split_id: str,
    ) -> Path:
        """Save per-example predictions as JSONL.

        Parameters
        ----------
        predictions : list[dict]
            Per-example prediction records.
        model : str
            Model name.
        strategy : str
            Strategy name.
        split_id : str
            Split ID.

        Returns
        -------
        Path
            Path to the saved JSONL file.
        """
        model_safe = model.replace("/", "_").replace(":", "_")
        out_dir = self.output_dir / model_safe / strategy
        out_dir.mkdir(parents=True, exist_ok=True)

        jsonl_path = out_dir / f"{split_id}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for record in predictions:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        logger.info(
            "predictions_saved",
            path=str(jsonl_path),
            count=len(predictions),
        )
        return jsonl_path

    def save_split_summary(
        self,
        metrics: dict[str, float],
        model: str,
        strategy: str,
        split_id: str,
        num_examples: int,
    ) -> Path:
        """Save aggregate metrics for one (model, strategy, split) run.

        Returns
        -------
        Path
            Path to the saved JSON summary file.
        """
        model_safe = model.replace("/", "_").replace(":", "_")
        out_dir = self.output_dir / model_safe / strategy
        out_dir.mkdir(parents=True, exist_ok=True)

        task_info = SPLIT_TASK_MAP.get(split_id)
        summary = {
            "model": model,
            "strategy": strategy,
            "split_id": split_id,
            "task": task_info[1].value if task_info else split_id,
            "capability": task_info[2].value if task_info else "",
            "task_type": task_info[0] if task_info else "",
            "num_examples": num_examples,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat(),
        }

        summary_path = out_dir / f"{split_id}_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        return summary_path

    def build_capability_profile(
        self,
        all_metrics: dict[str, dict[str, float]],
        model: str,
    ) -> OntoURLCapabilityProfile:
        """Build a capability profile from per-split metrics.

        Parameters
        ----------
        all_metrics : dict
            Mapping split_id → metrics dict.
        model : str
            Model name.

        Returns
        -------
        OntoURLCapabilityProfile
            Aggregated profile.
        """
        task_scores: list[OntoURLTaskScore] = []
        u_scores: list[float] = []
        r_scores: list[float] = []
        l_scores: list[float] = []

        for split_id, (task_type, task_enum, capability) in SPLIT_TASK_MAP.items():
            metrics = all_metrics.get(split_id, {})

            score = OntoURLTaskScore(
                task=task_enum,
                capability=capability,
                num_questions=metrics.get("total", 0),
            )

            if task_type in ("mc", "bool"):
                score.accuracy = metrics.get("accuracy", 0.0)
                val = score.accuracy or 0.0
            elif task_type == "open_text":
                score.rouge_l = metrics.get("rouge_l", 0.0)
                val = score.rouge_l or 0.0
            elif task_type == "open_triple":
                score.triple_f1 = metrics.get("triple_f1", 0.0)
                val = score.triple_f1 or 0.0
            elif task_type == "open_tuple":
                score.tuple_f1 = metrics.get("tuple_f1", 0.0)
                val = score.tuple_f1 or 0.0
            else:
                val = 0.0

            task_scores.append(score)

            if capability == OntoURLCapability.UNDERSTANDING:
                u_scores.append(val)
            elif capability == OntoURLCapability.REASONING:
                r_scores.append(val)
            else:
                l_scores.append(val)

        u_avg = sum(u_scores) / len(u_scores) if u_scores else 0.0
        r_avg = sum(r_scores) / len(r_scores) if r_scores else 0.0
        l_avg = sum(l_scores) / len(l_scores) if l_scores else 0.0
        overall = (u_avg + r_avg + l_avg) / 3.0 if (u_scores or r_scores or l_scores) else 0.0

        return OntoURLCapabilityProfile(
            understanding_avg=u_avg,
            reasoning_avg=r_avg,
            learning_avg=l_avg,
            task_scores=task_scores,
            overall_avg=overall,
            model_name=model,
        )

    def generate_html_summary(self, our_results: dict[str, dict[str, dict[str, float]]], model: str, strategy: str) -> dict[str, Path]:
        """Generate an HTML summary for one model/strategy including charts.

        Writes:
          - `comparison_table.md` (already written by generate_comparison_table)
          - `ontourl_summary.html` embedding charts and the comparison table
          - radar + bar charts (PNG)
        """
        outdir = self.output_dir / model.replace("/", "_").replace(":", "_") / strategy
        outdir.mkdir(parents=True, exist_ok=True)

        # Build capability profile
        profile = self.build_capability_profile(our_results.get(model, {}).get(strategy, {}), model)

        # Create radar chart (understanding, reasoning, learning)
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except Exception:
            return {}

        caps = [profile.understanding_avg, profile.reasoning_avg, profile.learning_avg]
        labels = ["Understanding", "Reasoning", "Learning"]
        angles = np.linspace(0, 2 * np.pi, len(caps), endpoint=False).tolist()
        caps += caps[:1]
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(5, 4), subplot_kw=dict(polar=True))
        ax.plot(angles, caps, 'o-', linewidth=2)
        ax.fill(angles, caps, alpha=0.25)
        ax.set_thetagrids(np.degrees(angles[:-1]), labels)
        ax.set_ylim(0, 1)
        radar_path = outdir / 'ontourl_radar.png'
        fig.savefig(radar_path, dpi=200, bbox_inches='tight')
        plt.close(fig)

        # Bar chart for the 15 task scores
        task_ids = [t.name.split('_')[0].upper() for t in [
            OntoURLTask.U1_CLASS_DEFINITION,
            OntoURLTask.U2_CLASS_RELATION,
            OntoURLTask.U3_PROPERTY_DOMAIN,
            OntoURLTask.U4_INSTANCE_CLASS,
            OntoURLTask.U5_INSTANCE_DEFINITION,
            OntoURLTask.R1_INFERRED_RELATION,
            OntoURLTask.R2_CONSTRAINT,
            OntoURLTask.R3_INSTANCE_CLASS_INFERRED,
            OntoURLTask.R4_SWRL_BASED,
            OntoURLTask.R5_DESCRIPTION_LOGIC,
            OntoURLTask.L1_CLASS_DEF_GENERATION,
            OntoURLTask.L2_HIERARCHY_CONSTRUCTION,
            OntoURLTask.L3_PROPERTY_CONSTRUCTION,
            OntoURLTask.L4_CONSTRAINT_CONSTRUCTION,
            OntoURLTask.L5_ONTOLOGY_ALIGNMENT,
        ]]

        scores = []
        for t in profile.task_scores:
            # prefer accuracy/rouge/triple/tuple metrics (values already in 0..1)
            if t.capability == OntoURLCapability.UNDERSTANDING or t.capability == OntoURLCapability.REASONING:
                # try to pick the most representative field
                val = t.accuracy or t.triple_f1 or t.tuple_f1 or t.rouge_l or 0.0
            else:
                val = t.rouge_l or t.triple_f1 or t.tuple_f1 or 0.0
            scores.append(val)

        # Fallback: if profile.task_scores missing, build from our_results if possible
        if not scores or len(scores) != len(task_ids):
            # try pulling metrics from our_results dict
            metrics_map = our_results.get(model, {}).get(strategy, {})
            scores = []
            for tid in [
                '1_1','1_2','1_3','1_4','1_5','2_1','2_2','2_3','2_4','2_5','3_1','3_2','3_3','3_4','3_5'
            ]:
                m = metrics_map.get(tid, {})
                # choose a sensible metric
                candidates = ['accuracy','rouge_l','triple_f1','tuple_f1']
                v = 0.0
                for c in candidates:
                    if c in m:
                        v = m[c]
                        break
                scores.append(v)

        # create bar chart
        fig, ax = plt.subplots(figsize=(10, 3))
        x = range(len(task_ids))
        ax.bar(x, scores, color='#2196F3')
        ax.set_xticks(list(x))
        ax.set_xticklabels(task_ids, rotation=45, ha='right')
        ax.set_ylim(0, 1)
        ax.set_title(f"OntoURL task scores — {model} / {strategy}")
        bar_path = outdir / 'ontourl_tasks_bar.png'
        fig.tight_layout()
        fig.savefig(bar_path, dpi=200)
        plt.close(fig)

        # Generate HTML embedding the MD table and the charts
        comparison_md = self.generate_comparison_table(our_results)
        html_lines = [
            '<html>',
            '<head><meta charset="utf-8"><title>OntoURL summary</title></head>',
            '<body>',
            f'<h1>OntoURL summary — {model} / {strategy}</h1>',
            '<h2>Capability profile</h2>',
            f'<img src="{radar_path.name}" alt="radar" style="max-width:600px;">',
            '<h2>Per-task scores</h2>',
            f'<img src="{bar_path.name}" alt="tasks" style="max-width:900px;">',
            '<h2>Comparison table</h2>',
            '<pre>',
            comparison_md,
            '</pre>',
            '</body></html>'
        ]
        html_path = outdir / 'ontourl_summary.html'
        html_path.write_text('\n'.join(html_lines))

        return {'html': html_path, 'radar': radar_path, 'bars': bar_path}

    def generate_comparison_table(
        self,
        our_results: dict[str, dict[str, dict[str, float]]],
        output_format: str = "markdown",
    ) -> str:
        """Generate a comparison table: our models × strategies vs published baselines.

        Parameters
        ----------
        our_results : dict
            Nested dict: model → strategy → split_id → metrics.
        output_format : str
            'markdown' or 'csv'.

        Returns
        -------
        str
            Formatted table string.
        """
        # Collect all task IDs in order
        task_ids = ["U1", "U2", "U3", "U4", "U5",
                    "R1", "R2", "R3", "R4", "R5",
                    "L1", "L2", "L3", "L4", "L5"]

        split_for_task = {
            "U1": "1_1", "U2": "1_2", "U3": "1_3", "U4": "1_4", "U5": "1_5",
            "R1": "2_1", "R2": "2_2", "R3": "2_3", "R4": "2_4", "R5": "2_5",
            "L1": "3_1", "L2": "3_2", "L3": "3_3", "L4": "3_4", "L5": "3_5",
        }

        metric_for_task = {
            "U1": "accuracy", "U2": "accuracy", "U3": "accuracy",
            "U4": "accuracy", "U5": "accuracy",
            "R1": "accuracy", "R2": "accuracy", "R3": "accuracy",
            "R4": "accuracy", "R5": "accuracy",
            "L1": "rouge_l", "L2": "triple_f1", "L3": "triple_f1",
            "L4": "triple_f1", "L5": "tuple_f1",
        }

        # Build columns: published baselines + our models × strategies
        columns: list[tuple[str, str]] = []  # (label, "published"|"ours")
        for baseline_name in PUBLISHED_BASELINES:
            columns.append((baseline_name, "published"))

        for model in our_results:
            for strategy in our_results[model]:
                columns.append((f"{model}|{strategy}", "ours"))

        # Build rows
        rows: list[list[str]] = []
        for tid in task_ids:
            sid = split_for_task[tid]
            metric_key = metric_for_task[tid]
            row = [tid, metric_key]

            for col_label, col_type in columns:
                if col_type == "published":
                    val = PUBLISHED_BASELINES[col_label].get(tid, 0.0)
                    row.append(f"{val:.1f}")
                else:
                    model, strategy = col_label.split("|", 1)
                    metrics = our_results.get(model, {}).get(strategy, {}).get(sid, {})
                    val = metrics.get(metric_key, 0.0)
                    row.append(f"{val * 100:.1f}" if val is not None else "—")

            rows.append(row)

        # Format output
        if output_format == "csv":
            return self._format_csv(columns, rows)
        table_md = self._format_markdown(columns, rows)

        return table_md
    def _format_markdown(
        self,
        columns: list[tuple[str, str]],
        rows: list[list[str]],
    ) -> str:
        """Format comparison table as Markdown."""
        col_headers = ["Task", "Metric"] + [c[0] for c in columns]
        header = "| " + " | ".join(col_headers) + " |"
        separator = "| " + " | ".join(["---"] * len(col_headers)) + " |"

        lines = [header, separator]
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")

        table = "\n".join(lines)

        # Save to file
        md_path = self.output_dir / "comparison_table.md"
        with open(md_path, "w") as f:
            f.write(f"# OntoURL Benchmark Comparison\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            f.write(table)

        return table

    def _format_csv(
        self,
        columns: list[tuple[str, str]],
        rows: list[list[str]],
    ) -> str:
        """Format comparison table as CSV."""
        csv_path = self.output_dir / "comparison_table.csv"
        col_headers = ["Task", "Metric"] + [c[0] for c in columns]

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(col_headers)
            writer.writerows(rows)

        return str(csv_path)

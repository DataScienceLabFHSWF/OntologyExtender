"""C1.5.3 — IterationReporter: compare before/after metrics for iterations."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class IterationReporter:
    """Generate comparison reports between ontology iteration versions.

    Compares KG metrics before and after an ontology extension cycle
    to measure improvement.
    """

    def compare(
        self,
        before_path: Path | str,
        after_path: Path | str,
    ) -> dict:
        """Compare before/after metrics for an iteration.

        Args:
            before_path: KG metrics JSON before extension.
            after_path: KG metrics JSON after extension.

        Returns:
            Report dict with per-metric comparisons.
        """
        before_path = Path(before_path)
        after_path = Path(after_path)

        with open(before_path) as f:
            before = json.load(f)
        with open(after_path) as f:
            after = json.load(f)

        metrics = []

        # Extract comparable metrics
        metric_keys = [
            ("cq_coverage", "CQ Answerability"),
            ("entity_coverage", "Entity Coverage"),
            ("relation_coverage", "Relation Coverage"),
            ("avg_confidence", "Avg Confidence"),
        ]

        # Handle lists (e.g. if CQs are passed instead of metrics)
        if isinstance(before, list) or isinstance(after, list):
            logger.warning("comparison_on_lists_not_implemented", 
                           before_type=type(before).__name__, 
                           after_type=type(after).__name__)
            return {
                "before_file": str(before_path),
                "after_file": str(after_path),
                "metrics": [],
                "summary": {"improved": 0, "degraded": 0, "unchanged": 0},
                "notes": "Input files were lists (CQs?), expected dicts (metrics)."
            }

        for key, name in metric_keys:
            before_val = before.get(key, 0.0) if isinstance(before, dict) else 0.0
            after_val = after.get(key, 0.0) if isinstance(after, dict) else 0.0
            metrics.append({
                "name": name,
                "key": key,
                "before": before_val,
                "after": after_val,
                "change": after_val - before_val,
            })

        report = {
            "before_file": str(before_path),
            "after_file": str(after_path),
            "metrics": metrics,
            "summary": {
                "improved": sum(1 for m in metrics if m["change"] > 0),
                "degraded": sum(1 for m in metrics if m["change"] < 0),
                "unchanged": sum(1 for m in metrics if m["change"] == 0),
            },
        }

        logger.info(
            "comparison_complete",
            improved=report["summary"]["improved"],
            degraded=report["summary"]["degraded"],
        )
        return report

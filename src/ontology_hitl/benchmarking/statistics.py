"""Statistical analysis for benchmark comparisons.

Provides significance testing and confidence intervals to determine
whether CogAgent's improvements over baselines are statistically
meaningful (not just noise from a single run).

Methods
-------
- Paired t-test (when we have multiple test cases per system)
- Bootstrap confidence intervals (non-parametric, works with small N)
- Effect size (Cohen's d)
- Per-metric improvement with p-values

Usage
-----
::

    from ontology_hitl.benchmarking.statistics import StatisticalAnalyzer

    analyzer = StatisticalAnalyzer()
    report = analyzer.full_significance_report(
        cogagent_results=[r1, r2, r3, r4],
        baseline_results=[b1, b2, b3, b4],
        baseline_name="LLM4ACOE",
    )
    print(report)

Dependencies
------------
- ``scipy.stats`` for t-tests
- ``numpy`` for bootstrap resampling

References
----------
- BENCHMARKING_QUICKSTART.md §Step 2: Statistical Analysis
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from .models import BenchmarkResult, MetricScores

logger = structlog.get_logger(__name__)

# Metric fields to test (excluding hallucination_rate which is inverted)
_METRIC_FIELDS = [
    "semantic_correctness",
    "hallucination_rate",
    "cq_coverage",
    "hierarchy_quality",
    "domain_compliance",
    "expert_acceptance",
]


class StatisticalAnalyzer:
    """Statistical significance testing for benchmark comparisons.

    Parameters
    ----------
    alpha : float
        Significance level for hypothesis tests (default 0.05).
    n_bootstrap : int
        Number of bootstrap resamples for confidence intervals.
    random_seed : int
        Seed for reproducible bootstrap sampling.
    """

    def __init__(
        self,
        alpha: float = 0.05,
        n_bootstrap: int = 10_000,
        random_seed: int = 42,
    ) -> None:
        self.alpha = alpha
        self.n_bootstrap = n_bootstrap
        self.random_seed = random_seed
        self._rng = np.random.RandomState(random_seed)

    # ------------------------------------------------------------------
    # Full report
    # ------------------------------------------------------------------

    def full_significance_report(
        self,
        cogagent_results: list[BenchmarkResult],
        baseline_results: list[BenchmarkResult],
        baseline_name: str = "baseline",
    ) -> dict[str, Any]:
        """Generate a complete statistical significance report.

        For each of the six metric dimensions, computes:
          - Mean ± std for CogAgent and baseline
          - Paired t-test p-value
          - Bootstrap 95 % CI for the difference
          - Cohen's d effect size
          - Whether the improvement is significant at ``alpha``

        Parameters
        ----------
        cogagent_results : list[BenchmarkResult]
            CogAgent results across multiple test cases.
        baseline_results : list[BenchmarkResult]
            Baseline results on the *same* test cases (matched pairs).
        baseline_name : str
            Human-readable name for the comparison narrative.

        Returns
        -------
        dict[str, Any]
            Structure::

                {
                    "overall": {
                        "n_test_cases": 4,
                        "alpha": 0.05,
                        "any_significant": True
                    },
                    "per_metric": {
                        "semantic_correctness": {
                            "cogagent_mean": 0.92,
                            "cogagent_std": 0.03,
                            "baseline_mean": 0.70,
                            "baseline_std": 0.08,
                            "p_value": 0.002,
                            "significant": True,
                            "cohens_d": 3.12,
                            "effect_size": "large",
                            "ci_lower": 0.15,
                            "ci_upper": 0.29,
                            "improvement_pct": 31.4
                        },
                        ...
                    }
                }

        Raises
        ------
        ValueError
            If the number of CogAgent and baseline results differ
            (not matched pairs).
        """
        if len(cogagent_results) != len(baseline_results):
            raise ValueError(
                f"Mismatched result counts: CogAgent={len(cogagent_results)}, "
                f"{baseline_name}={len(baseline_results)}"
            )

        n = len(cogagent_results)
        report: dict[str, Any] = {
            "overall": {
                "n_test_cases": n,
                "alpha": self.alpha,
                "baseline_name": baseline_name,
                "any_significant": False,
            },
            "per_metric": {},
        }

        any_sig = False
        for metric in _METRIC_FIELDS:
            cog_scores = self._extract_metric_scores(cogagent_results, metric)
            bas_scores = self._extract_metric_scores(baseline_results, metric)

            cog_mean = float(np.mean(cog_scores))
            cog_std = float(np.std(cog_scores, ddof=1)) if n > 1 else 0.0
            bas_mean = float(np.mean(bas_scores))
            bas_std = float(np.std(bas_scores, ddof=1)) if n > 1 else 0.0

            # For hallucination_rate, lower is better — invert for
            # improvement interpretation
            improvement_pct = 0.0
            if bas_mean != 0:
                if metric == "hallucination_rate":
                    improvement_pct = (bas_mean - cog_mean) / abs(bas_mean) * 100
                else:
                    improvement_pct = (cog_mean - bas_mean) / abs(bas_mean) * 100

            # Statistical tests
            p_value = 1.0
            t_stat = 0.0
            if n >= 2:
                try:
                    t_stat, p_value = self.paired_t_test(cog_scores, bas_scores)
                except Exception:
                    pass

            mean_diff, ci_lower, ci_upper = 0.0, 0.0, 0.0
            if n >= 2:
                try:
                    mean_diff, ci_lower, ci_upper = self.bootstrap_confidence_interval(
                        cog_scores, bas_scores
                    )
                except Exception:
                    pass

            d_val, d_interp = 0.0, "negligible"
            if n >= 2:
                try:
                    d_val, d_interp = self.cohens_d(cog_scores, bas_scores)
                except Exception:
                    pass

            significant = p_value < self.alpha
            if significant:
                any_sig = True

            report["per_metric"][metric] = {
                "cogagent_mean": round(cog_mean, 4),
                "cogagent_std": round(cog_std, 4),
                "baseline_mean": round(bas_mean, 4),
                "baseline_std": round(bas_std, 4),
                "t_statistic": round(t_stat, 4),
                "p_value": round(p_value, 6),
                "significant": significant,
                "cohens_d": round(d_val, 4),
                "effect_size": d_interp,
                "ci_lower": round(ci_lower, 4),
                "ci_upper": round(ci_upper, 4),
                "improvement_pct": round(improvement_pct, 2),
            }

        report["overall"]["any_significant"] = any_sig
        return report

    # ------------------------------------------------------------------
    # Individual tests
    # ------------------------------------------------------------------

    def paired_t_test(
        self, scores_a: list[float], scores_b: list[float]
    ) -> tuple[float, float]:
        """Paired two-sided t-test for dependent samples.

        Tests H₀: mean(scores_a) = mean(scores_b).

        Parameters
        ----------
        scores_a : list[float]
            Scores from system A (CogAgent) on each test case.
        scores_b : list[float]
            Scores from system B (baseline) on same test cases.

        Returns
        -------
        t_statistic : float
        p_value : float

        Notes
        -----
        Requires ``len(scores_a) == len(scores_b) >= 2``.
        With only 4 test cases, the t-test has low power —
        use bootstrap CI as a complement.
        """
        from scipy.stats import ttest_rel

        a = np.array(scores_a, dtype=float)
        b = np.array(scores_b, dtype=float)
        t_stat, p_val = ttest_rel(a, b)
        return float(t_stat), float(p_val)

    def bootstrap_confidence_interval(
        self,
        scores_a: list[float],
        scores_b: list[float],
        confidence: float = 0.95,
    ) -> tuple[float, float, float]:
        """Bootstrap confidence interval for the mean difference.

        Parameters
        ----------
        scores_a : list[float]
            System A scores.
        scores_b : list[float]
            System B scores.
        confidence : float
            Confidence level (default 0.95 for 95 % CI).

        Returns
        -------
        mean_diff : float
            Mean of the bootstrapped differences.
        ci_lower : float
            Lower bound of the CI.
        ci_upper : float
            Upper bound of the CI.

        Notes
        -----
        Non-parametric.  Works well even with N = 4 test cases.
        If the CI excludes 0, the difference is significant at
        the given confidence level.
        """
        a = np.array(scores_a, dtype=float)
        b = np.array(scores_b, dtype=float)
        diffs = a - b
        n = len(diffs)
        boot_diffs = np.empty(self.n_bootstrap)
        for i in range(self.n_bootstrap):
            idx = self._rng.randint(0, n, size=n)
            boot_diffs[i] = np.mean(diffs[idx])
        mean_diff = float(np.mean(boot_diffs))
        alpha_tail = (1.0 - confidence) / 2.0
        ci_lower = float(np.percentile(boot_diffs, 100 * alpha_tail))
        ci_upper = float(np.percentile(boot_diffs, 100 * (1.0 - alpha_tail)))
        return mean_diff, ci_lower, ci_upper

    def cohens_d(
        self, scores_a: list[float], scores_b: list[float]
    ) -> tuple[float, str]:
        """Compute Cohen's d effect size for the difference.

        Parameters
        ----------
        scores_a : list[float]
        scores_b : list[float]

        Returns
        -------
        d : float
            Cohen's d value.
        interpretation : str
            One of ``"negligible"`` (< 0.2), ``"small"`` (0.2–0.5),
            ``"medium"`` (0.5–0.8), ``"large"`` (≥ 0.8).
        """
        a = np.array(scores_a, dtype=float)
        b = np.array(scores_b, dtype=float)
        diff = a - b
        mean_diff = float(np.mean(diff))
        # Pooled standard deviation
        n_a, n_b = len(a), len(b)
        var_a = float(np.var(a, ddof=1)) if n_a > 1 else 0.0
        var_b = float(np.var(b, ddof=1)) if n_b > 1 else 0.0
        pooled_std = np.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / max(1, n_a + n_b - 2))
        d = mean_diff / pooled_std if pooled_std > 0 else 0.0
        abs_d = abs(d)
        if abs_d >= 0.8:
            interp = "large"
        elif abs_d >= 0.5:
            interp = "medium"
        elif abs_d >= 0.2:
            interp = "small"
        else:
            interp = "negligible"
        return float(d), interp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_metric_scores(
        self, results: list[BenchmarkResult], metric: str
    ) -> list[float]:
        """Extract a single metric's values from a list of results.

        Parameters
        ----------
        results : list[BenchmarkResult]
        metric : str
            Field name on ``MetricScores`` (e.g. ``"semantic_correctness"``).

        Returns
        -------
        list[float]
            One value per result, in order.
        """
        return [float(getattr(r.metrics, metric, 0.0)) for r in results]

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
        raise NotImplementedError(
            "TODO: for each metric, extract paired scores, "
            "call paired_t_test + bootstrap_ci + cohens_d"
        )

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
        raise NotImplementedError(
            "TODO: scipy.stats.ttest_rel(scores_a, scores_b)"
        )

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
        raise NotImplementedError(
            "TODO: resample with replacement, compute diff each time, "
            "take percentile bounds"
        )

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
        raise NotImplementedError(
            "TODO: d = mean(a - b) / pooled_std"
        )

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
        raise NotImplementedError(
            "TODO: [getattr(r.metrics, metric) for r in results]"
        )

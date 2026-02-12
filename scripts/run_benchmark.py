#!/usr/bin/env python3
"""CLI entry point for the benchmarking framework.

Run a complete benchmark suite comparing CogAgent against baseline
ontology extension systems (Agent-OM, LLM4ACOE, NLP-W2V).

Usage
-----
::

    # Generate test cases from gold-standard ontology
    python scripts/run_benchmark.py generate-test-cases \\
        --gold-standard data/seed_ontology/plan-ontology-v1.0.owl \\
        --output-dir data/test_cases

    # Run full benchmark suite from config file
    python scripts/run_benchmark.py run \\
        --config benchmark_config.json

    # Run only specific systems
    python scripts/run_benchmark.py run \\
        --config benchmark_config.json \\
        --systems cogagent llm4acoe

    # Evaluate a previously-generated ontology against gold standard
    python scripts/run_benchmark.py evaluate \\
        --generated results/cogagent_75pct/output.owl \\
        --gold-standard data/seed_ontology/plan-ontology-v1.0.owl \\
        --test-case data/test_cases/plan-ontology-75pct.json

    # Generate reports from existing results
    python scripts/run_benchmark.py report \\
        --results-dir results/benchmarking

    # Create a default benchmark config file
    python scripts/run_benchmark.py init \\
        --output benchmark_config.json

Examples
--------
::

    # Quick start: generate config, then run
    python scripts/run_benchmark.py init
    python scripts/run_benchmark.py run --config benchmark_config.json

    # Generate test cases first, inspect them, then run
    python scripts/run_benchmark.py generate-test-cases
    ls data/test_cases/
    python scripts/run_benchmark.py run --config benchmark_config.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def cmd_init(args: argparse.Namespace) -> None:
    """Create a default benchmark configuration file.

    Generates ``benchmark_config.json`` with sensible defaults:
      - Gold standard: ``data/seed_ontology/plan-ontology-v1.0.owl``
      - Systems: CogAgent + all three baselines
      - Output: ``results/benchmarking/``
      - All four reduction levels

    Parameters
    ----------
    args : argparse.Namespace
        ``args.output`` — path for the config file.
    """
    from ontology_hitl.benchmarking.models import (
        BaselineSystem,
        BaselineSystemConfig,
        BenchmarkConfig,
    )

    config = BenchmarkConfig(
        name="plan-ontology-benchmark-v1",
        gold_standard_path=Path("data/seed_ontology/plan-ontology-v1.0.owl"),
        systems=[
            BaselineSystemConfig(
                system=BaselineSystem.COGAGENT,
                repo_url="(in-process)",
                entry_command="(in-process)",
            ),
            BaselineSystemConfig(
                system=BaselineSystem.AGENT_OM,
                repo_url="https://github.com/qzc438/ontology-llm.git",
                repo_path=Path("/tmp/baselines/agent_om"),
                entry_command="python run_config.py",
                setup_commands=[
                    "git clone https://github.com/qzc438/ontology-llm.git /tmp/baselines/agent_om",
                    "cd /tmp/baselines/agent_om && pip install -r requirements.txt",
                ],
                output_format="csv",
            ),
            BaselineSystemConfig(
                system=BaselineSystem.LLM4ACOE,
                repo_url="https://github.com/AndreasSoularidis/LLM-based-OE-Framework-LC3.git",
                repo_path=Path("/tmp/baselines/llm4acoe"),
                entry_command="python LLM4ACOE.py",
                setup_commands=[
                    "git clone https://github.com/AndreasSoularidis/LLM-based-OE-Framework-LC3.git /tmp/baselines/llm4acoe",
                    "cd /tmp/baselines/llm4acoe && pip install -r requirements.txt",
                ],
                output_format="owl",
            ),
            BaselineSystemConfig(
                system=BaselineSystem.NLP_W2V,
                repo_url="https://github.com/TUDoAD/NLP-Based-Ontology-Extender.git",
                repo_path=Path("/tmp/baselines/nlp_w2v"),
                entry_command="python main.py",
                setup_commands=[
                    "git clone https://github.com/TUDoAD/NLP-Based-Ontology-Extender.git /tmp/baselines/nlp_w2v",
                    "cd /tmp/baselines/nlp_w2v && pip install -r requirements.txt",
                ],
                output_format="owl",
            ),
        ],
        output_dir=Path("results/benchmarking"),
    )

    output_path = Path(args.output)
    output_path.write_text(config.model_dump_json(indent=2))
    logger.info("config_created", path=str(output_path))
    print(f"Created benchmark config: {output_path}")


def cmd_generate_test_cases(args: argparse.Namespace) -> None:
    """Generate test cases by decomposing the gold-standard ontology.

    Parameters
    ----------
    args : argparse.Namespace
        ``args.gold_standard`` — path to gold-standard OWL file.
        ``args.output_dir``   — directory for reduced OWL files.
        ``args.seed``         — random seed for reproducibility.
    """
    from ontology_hitl.benchmarking.test_cases import TestCaseGenerator

    gen = TestCaseGenerator(
        gold_standard_path=args.gold_standard,
        output_dir=args.output_dir,
        random_seed=args.seed,
    )
    test_cases = gen.generate_all()

    # Save metadata
    metadata_path = Path(args.output_dir) / "test_cases.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps([tc.model_dump(mode="json") for tc in test_cases], indent=2)
    )

    print(f"Generated {len(test_cases)} test cases:")
    for tc in test_cases:
        print(f"  {tc.id}: {tc.num_remaining_classes}/{tc.num_original_classes} classes "
              f"({tc.reduction_level.value} reduction)")
    print(f"\nMetadata saved to: {metadata_path}")


def cmd_run(args: argparse.Namespace) -> None:
    """Run the full benchmark suite.

    Parameters
    ----------
    args : argparse.Namespace
        ``args.config``  — path to benchmark config JSON.
        ``args.systems`` — optional list of system IDs to run (subset).
        ``args.parallel`` — whether to run systems in parallel.
    """
    from ontology_hitl.benchmarking.models import BenchmarkConfig
    from ontology_hitl.benchmarking.runner import BenchmarkRunner

    config_data = json.loads(Path(args.config).read_text())
    config = BenchmarkConfig.model_validate(config_data)

    # Filter systems if specified
    if args.systems:
        config.systems = [
            s for s in config.systems if s.system.value in args.systems
        ]
        logger.info("filtered_systems", systems=args.systems)

    runner = BenchmarkRunner(
        config=config,
        skip_existing=not args.force,
        parallel=args.parallel,
    )
    results = runner.run_all()

    print("\n=== Benchmark Complete ===")
    print(f"Total time: {results.get('total_time_seconds', 0):.1f}s")
    print(f"Reports: {results.get('reports', {})}")


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Evaluate a single generated ontology against gold standard.

    Parameters
    ----------
    args : argparse.Namespace
        ``args.generated``     — path to generated OWL/TTL file.
        ``args.gold_standard`` — path to gold-standard OWL file.
        ``args.test_case``     — path to test case JSON metadata.
    """
    from ontology_hitl.benchmarking.metrics import BenchmarkEvaluator
    from ontology_hitl.benchmarking.models import TestCase

    test_case_data = json.loads(Path(args.test_case).read_text())
    test_case = TestCase.model_validate(test_case_data)

    evaluator = BenchmarkEvaluator()
    scores = evaluator.evaluate_all(
        generated_path=args.generated,
        test_case=test_case,
    )

    print("\n=== Evaluation Results ===")
    print(f"Semantic Correctness:  {scores.semantic_correctness:.3f}")
    print(f"Hallucination Rate:    {scores.hallucination_rate:.3f}")
    print(f"CQ Coverage:           {scores.cq_coverage:.3f}")
    print(f"Hierarchy Quality:     {scores.hierarchy_quality:.3f}")
    print(f"Domain Compliance:     {scores.domain_compliance:.3f}")
    print(f"Expert Acceptance:     {scores.expert_acceptance:.3f}")
    print(f"───────────────────────────────")
    print(f"Composite Score:       {scores.composite_score:.3f}")


def cmd_report(args: argparse.Namespace) -> None:
    """Generate reports from existing results.

    Parameters
    ----------
    args : argparse.Namespace
        ``args.results_dir`` — directory containing result JSON files.
        ``args.format``      — output format(s): png, pdf, svg.
    """
    from ontology_hitl.benchmarking.aggregator import ResultsAggregator
    from ontology_hitl.benchmarking.reporting import ReportGenerator

    aggregator = ResultsAggregator(output_dir=args.results_dir)
    aggregator.load_results_from_dir(args.results_dir)

    reporter = ReportGenerator(
        output_dir=Path(args.results_dir) / "reports",
        figure_format=args.format,
    )
    outputs = reporter.generate_all(aggregator)

    print("\n=== Reports Generated ===")
    for name, path in outputs.items():
        print(f"  {name}: {path}")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns
    -------
    argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="Benchmark CogAgent against baseline ontology systems.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- init ---
    p_init = subparsers.add_parser(
        "init",
        help="Create a default benchmark configuration file.",
    )
    p_init.add_argument(
        "--output", "-o",
        default="benchmark_config.json",
        help="Output path for the config file (default: benchmark_config.json)",
    )

    # --- generate-test-cases ---
    p_gen = subparsers.add_parser(
        "generate-test-cases",
        help="Decompose gold-standard ontology into graded test cases.",
    )
    p_gen.add_argument(
        "--gold-standard",
        default="data/seed_ontology/plan-ontology-v1.0.owl",
        help="Path to the gold-standard OWL file.",
    )
    p_gen.add_argument(
        "--output-dir",
        default="data/test_cases",
        help="Directory for reduced OWL files and metadata.",
    )
    p_gen.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible decomposition.",
    )

    # --- run ---
    p_run = subparsers.add_parser(
        "run",
        help="Execute the full benchmark suite.",
    )
    p_run.add_argument(
        "--config", "-c",
        default="benchmark_config.json",
        help="Path to benchmark config JSON.",
    )
    p_run.add_argument(
        "--systems",
        nargs="*",
        choices=["cogagent", "agent_om", "llm4acoe", "nlp_w2v"],
        help="Subset of systems to run (default: all configured).",
    )
    p_run.add_argument(
        "--parallel",
        action="store_true",
        help="Run systems in parallel threads.",
    )
    p_run.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if checkpoints exist.",
    )

    # --- evaluate ---
    p_eval = subparsers.add_parser(
        "evaluate",
        help="Evaluate a single generated ontology.",
    )
    p_eval.add_argument(
        "--generated", "-g",
        required=True,
        help="Path to the generated OWL/TTL file.",
    )
    p_eval.add_argument(
        "--gold-standard",
        default="data/seed_ontology/plan-ontology-v1.0.owl",
        help="Path to the gold-standard OWL file.",
    )
    p_eval.add_argument(
        "--test-case",
        required=True,
        help="Path to the test-case JSON metadata.",
    )

    # --- report ---
    p_report = subparsers.add_parser(
        "report",
        help="Generate reports from existing results.",
    )
    p_report.add_argument(
        "--results-dir",
        default="results/benchmarking",
        help="Directory containing result JSON files.",
    )
    p_report.add_argument(
        "--format",
        default="png",
        choices=["png", "pdf", "svg"],
        help="Chart image format (default: png).",
    )

    return parser


def main() -> None:
    """CLI main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    COMMANDS = {
        "init": cmd_init,
        "generate-test-cases": cmd_generate_test_cases,
        "run": cmd_run,
        "evaluate": cmd_evaluate,
        "report": cmd_report,
    }

    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()

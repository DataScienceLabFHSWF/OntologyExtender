#!/usr/bin/env python3
"""Run OntoURL benchmark with our models and strategies.

Usage:
    # Full benchmark (all 15 tasks, zero-shot, gemma4:e2b)
    python scripts/run_ontourl_benchmark.py --model gemma4:e2b

    # Learning tasks only, all strategies
    python scripts/run_ontourl_benchmark.py \\
        --tasks L1 L2 L3 L4 L5 \\
        --strategies vanilla_zero cot engineer multi_turn debate \\
        --model gemma4:31b

    # Quick test run (50 examples per split)
    python scripts/run_ontourl_benchmark.py --max-examples 50

    # Resume interrupted run
    python scripts/run_ontourl_benchmark.py --resume

    # Specific task with few-shot
    python scripts/run_ontourl_benchmark.py \\
        --tasks L2 --strategies vanilla_zero \\
        --model gemma4:e2b
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import structlog

from ontology_hitl.benchmarking.ontourl.loader import (
    OntoURLLoader,
    SPLIT_TASK_MAP,
    TASK_ID_TO_SPLIT,
)
from ontology_hitl.benchmarking.ontourl.evaluator import OntoURLEvaluator
from ontology_hitl.benchmarking.ontourl.strategies import (
    OllamaAdapter,
    VanillaStrategy,
    ChainOfThoughtStrategy,
    OntologyEngineerStrategy,
    MultiTurnStrategy,
    DebateStrategy,
    SelfVerifyStrategy,
    HCOMEStrategy,
)
# Import the 3-round HCOME implementation
from ontology_hitl.benchmarking.ontourl.hcome_strategy import HCOME3RoundStrategy  # type: ignore
from ontology_hitl.benchmarking.ontourl.reporter import OntoURLReporter

logger = structlog.get_logger(__name__)


# ── Strategy factory ─────────────────────────────────────────────────

STRATEGY_REGISTRY: dict[str, type] = {
    "vanilla_zero": VanillaStrategy,
    "vanilla_2shot": VanillaStrategy,
    "vanilla_4shot": VanillaStrategy,
    "cot": ChainOfThoughtStrategy,
    "engineer": OntologyEngineerStrategy,
    "multi_turn": MultiTurnStrategy,
    "debate": DebateStrategy,
    "self_verify": SelfVerifyStrategy,
    "hcome": HCOMEStrategy,
    "hcome_3round": HCOME3RoundStrategy,
}


def create_strategy(name: str, llm: OllamaAdapter) -> object:
    """Create a strategy instance by name."""
    if name == "vanilla_zero":
        return VanillaStrategy(llm, shot_setting="zero_shot")
    elif name == "vanilla_2shot":
        return VanillaStrategy(llm, shot_setting="two_shot")
    elif name == "vanilla_4shot":
        return VanillaStrategy(llm, shot_setting="four_shot")
    elif name == "cot":
        return ChainOfThoughtStrategy(llm)
    elif name == "engineer":
        return OntologyEngineerStrategy(llm)
    elif name == "multi_turn":
        return MultiTurnStrategy(llm)
    elif name == "debate":
        return DebateStrategy(llm)
    elif name == "self_verify":
        return SelfVerifyStrategy(llm)
    elif name == "hcome":
        return HCOMEStrategy(llm)
    elif name == "hcome_3round":
        return HCOME3RoundStrategy(llm)
    else:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY.keys())}")


# ── Main benchmark runner ────────────────────────────────────────────

def run_benchmark(args: argparse.Namespace) -> None:
    """Run the OntoURL benchmark."""
    # Load .env if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Set up LangSmith experiment context
    try:
        from ontology_hitl.agents.base import set_experiment_context, clear_experiment_context
        set_experiment_context(
            experiment_name=f"ontourl_{args.model.split(':')[0]}",
            model=args.model,
            strategy="benchmark",
            extra_tags=["ontourl"],
        )
    except Exception:
        pass

    # Initialize components
    loader = OntoURLLoader(cache_dir=args.cache_dir)
    evaluator = OntoURLEvaluator()
    reporter = OntoURLReporter(output_dir=args.output_dir)
    llm = OllamaAdapter(
        model=args.model,
        ollama_url=args.ollama_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )

    # Determine which splits to run
    if args.tasks:
        split_ids = []
        for tid in args.tasks:
            tid_upper = tid.upper()
            if tid_upper in TASK_ID_TO_SPLIT:
                split_ids.append(TASK_ID_TO_SPLIT[tid_upper])
            elif tid in SPLIT_TASK_MAP:
                split_ids.append(tid)
            else:
                logger.warning("unknown_task", task=tid)
    else:
        split_ids = list(SPLIT_TASK_MAP.keys())

    # Load dataset
    print(f"Loading OntoURL dataset...")
    loader.load()
    summary = loader.summary()
    print(f"Dataset loaded: {summary['total']} total examples across {len(summary['splits'])} splits\n")

    # Initialize W&B if enabled
    wandb_run = None
    try:
        import wandb
        from ontology_hitl.core.config import Settings
        settings = Settings()
        if settings.wandb_enabled:
            model_short = args.model.split(":")[0].split("/")[-1]
            wandb_run = wandb.init(
                project=settings.wandb_project,
                entity=settings.wandb_entity,
                name=f"ontourl_{model_short}",
                config={
                    "benchmark": "OntoURL",
                    "model": args.model,
                    "strategies": args.strategies,
                    "tasks": args.tasks or "all",
                    "max_examples": args.max_examples,
                    "temperature": args.temperature,
                },
                tags=["ontourl", model_short],
                reinit=True,
            )
    except Exception as e:
        logger.warning("wandb_init_failed", error=str(e))

    # Track all results for final comparison
    all_results: dict[str, dict[str, dict[str, float]]] = {}  # model → strategy → split → metrics

    # Run benchmark
    total_start = time.time()
    strategies_to_run = args.strategies or ["vanilla_zero"]

    for strategy_name in strategies_to_run:
        strategy = create_strategy(strategy_name, llm)
        print(f"\n{'='*60}")
        print(f"Strategy: {strategy_name}")
        print(f"{'='*60}")

        for split_id in split_ids:
            task_type, task_enum, capability = SPLIT_TASK_MAP[split_id]

            # Check strategy applicability
            if not strategy.applicable_to(task_type, split_id):
                print(f"  [{split_id}] {task_enum.value}: SKIPPED (not applicable)")
                continue

            # Check for resume
            if args.resume:
                model_safe = args.model.replace("/", "_").replace(":", "_")
                existing_summary = (
                    Path(args.output_dir) / model_safe / strategy_name
                    / f"{split_id}_summary.json"
                )
                if existing_summary.exists():
                    print(f"  [{split_id}] {task_enum.value}: RESUMED (already complete)")
                    with open(existing_summary) as f:
                        saved = json.load(f)
                    all_results.setdefault(args.model, {}).setdefault(
                        strategy_name, {}
                    )[split_id] = saved["metrics"]
                    continue

            # Get examples
            try:
                split = loader.get_split(split_id)
                examples = [dict(ex) for ex in split]
            except KeyError as e:
                print(f"  [{split_id}] {task_enum.value}: SKIPPED ({e})")
                continue

            if args.max_examples:
                examples = examples[:args.max_examples]

            n = len(examples)
            print(f"\n  [{split_id}] {task_enum.value} ({capability.value})")
            print(f"    Examples: {n} | Type: {task_type} | Strategy: {strategy_name}")

            # Run inference
            predictions_raw: list[str] = []
            references: list[str] = []
            prediction_records: list[dict] = []
            errors = 0

            for i, example in enumerate(examples):
                start_t = time.time()
                try:
                    response = strategy.answer(example, task_type, split_id)
                    latency = time.time() - start_t
                except Exception as e:
                    response = ""
                    latency = time.time() - start_t
                    errors += 1
                    if errors <= 3:
                        logger.warning("inference_error", split=split_id, idx=i, error=str(e))

                predictions_raw.append(response)
                ref = (example.get("answer") or "").strip()
                references.append(ref)

                # Build prediction record
                record = {
                    "identifier": example.get("identifier", example.get("id", f"{split_id}_{i}")),
                    "split": split_id,
                    "task": task_enum.value,
                    "strategy": strategy_name,
                    "model": args.model,
                    "question": example.get("question", "")[:500],
                    "reference_answer": ref[:500],
                    "raw_response": response[:1000],
                    "latency_seconds": round(latency, 3),
                    "timestamp": datetime.now().isoformat(),
                }

                # For MCQ, add correctness
                if task_type in ("mc", "bool"):
                    pred = evaluator.extract_prediction(response, task_type)
                    ref_clean = ref.upper() if task_type == "mc" else ref.lower()
                    record["prediction"] = pred
                    record["correct"] = pred == ref_clean

                prediction_records.append(record)

                # Progress indicator
                if (i + 1) % max(1, n // 10) == 0 or i == n - 1:
                    pct = (i + 1) / n * 100
                    avg_lat = sum(r["latency_seconds"] for r in prediction_records) / len(prediction_records)
                    eta = avg_lat * (n - i - 1)
                    print(f"    Progress: {i+1}/{n} ({pct:.0f}%) | Avg latency: {avg_lat:.1f}s | ETA: {eta:.0f}s", end="\r")

            print()  # newline after progress

            # Evaluate
            metrics = evaluator.evaluate_split(predictions_raw, references, task_type)
            print(f"    Results: {metrics}")

            # Save
            reporter.save_predictions(prediction_records, args.model, strategy_name, split_id)
            reporter.save_split_summary(metrics, args.model, strategy_name, split_id, n)

            # Track
            all_results.setdefault(args.model, {}).setdefault(strategy_name, {})[split_id] = metrics

            # Log to W&B
            if wandb_run:
                try:
                    import wandb
                    wandb.log({
                        f"{split_id}/{strategy_name}/{k}": v
                        for k, v in metrics.items()
                        if isinstance(v, (int, float))
                    })
                except Exception:
                    pass

            if errors > 0:
                print(f"    Errors: {errors}/{n}")

    # Final comparison table
    total_time = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"Benchmark complete in {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"{'='*60}\n")

    if all_results:
        table = reporter.generate_comparison_table(all_results)
        print(table)

        # Build capability profile
        for model, strategies in all_results.items():
            for strat_name, split_metrics in strategies.items():
                profile = reporter.build_capability_profile(split_metrics, model)
                print(f"\n{model} ({strat_name}):")
                print(f"  Understanding: {profile.understanding_avg*100:.1f}%")
                print(f"  Reasoning:     {profile.reasoning_avg*100:.1f}%")
                print(f"  Learning:      {profile.learning_avg*100:.1f}%")
                print(f"  Overall:       {profile.overall_avg*100:.1f}%")

    # Clean up
    if wandb_run:
        try:
            import wandb
            wandb.finish()
        except Exception:
            pass

    try:
        from ontology_hitl.agents.base import clear_experiment_context
        clear_experiment_context()
    except Exception:
        pass


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run OntoURL benchmark with Ollama models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--model", default="gemma4:e2b",
        help="Ollama model name (default: gemma4:e2b)",
    )
    parser.add_argument(
        "--tasks", nargs="*", default=None,
        help="Task filter: U1 U2 ... R1 ... L1 L2 L3 L4 L5 (default: all)",
    )
    parser.add_argument(
        "--strategies", nargs="*", default=["vanilla_zero"],
        help="Strategy list (default: vanilla_zero). "
             "Options: vanilla_zero, vanilla_2shot, vanilla_4shot, "
             "cot, engineer, multi_turn, debate, self_verify",
    )
    parser.add_argument(
        "--max-examples", type=int, default=None,
        help="Limit examples per split (for testing)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="results/ontourl",
        help="Output directory (default: results/ontourl/)",
    )
    parser.add_argument(
        "--cache-dir", type=str, default="data/benchmark_datasets/ontourl",
        help="Dataset cache directory",
    )
    parser.add_argument(
        "--ollama-url", type=str, default=None,
        help="Ollama server URL (default: from HITL_OLLAMA_URL or http://localhost:18135)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0,
        help="Generation temperature (default: 0.0)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=512,
        help="Max tokens per response (default: 512)",
    )
    parser.add_argument(
        "--timeout", type=float, default=600.0,
        help="Per-request timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip already-completed (split, strategy, model) runs",
    )

    args = parser.parse_args()

    # Set Ollama URL from env if not specified
    if args.ollama_url is None:
        args.ollama_url = os.getenv("HITL_OLLAMA_URL", "http://localhost:18135")

    run_benchmark(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the full reproduction benchmark suite (easy → hard).

For each target the script:
  1. Downloads the seed and gold ontology files (cached in
     ``data/benchmark_datasets/reproduction/``).
  2. Runs the full multi-agent pipeline with the seed as the starting ontology
     (``HITL_SEED_ONTOLOGY_PATH``).
  3. Scores the agent's output against the gold using precision / recall / F1
     over classes, properties and subclass axioms, plus a logical-consistency
     check.
  4. Writes a JSON results file and a Markdown summary table.

Ablation flags
--------------
--targets          Space-separated subset of target names to run (default: all)
--complexity-max   Maximum :class:`Complexity` level to include (1-4, default 4)
--reasoner         "on", "off", or "both" (default: "both" — runs two passes)
--model            Ollama model override (default: uses HITL_OLLAMA_MODEL)
--output           Path for the JSON results file
--dry-run          Print the plan and download ontologies but skip the pipeline
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import structlog

# Add project root so local imports work when called directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ontology_hitl.tools.ollama_preflight import check_ollama_model
from src.ontology_hitl.benchmarking.reproduction_suite import (
    REGISTRY_ORDERED,
    Complexity,
    ReproductionSuite,
    ReproductionTarget,
)
from src.ontology_hitl.benchmarking.oeo_benchmark import OEOBenchmark

logger = structlog.get_logger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--targets", nargs="*", help="Target names to run (default: all)")
    p.add_argument("--complexity-max", type=int, default=4, choices=[1, 2, 3, 4],
                   help="Maximum complexity tier to include (1=SMOKE, 4=RESEARCH)")
    p.add_argument("--reasoner", choices=["on", "off", "both"], default="both",
                   help="Reasoner gate setting for pipeline runs")
    p.add_argument("--model", default="", help="Ollama model override")
    p.add_argument("--ollama-url", default="", help="Ollama endpoint override")
    p.add_argument("--output", default="results/reproduction_results.json",
                   help="JSON output file for results")
    p.add_argument("--dry-run", action="store_true",
                   help="Download ontologies and print plan; skip pipeline")
    return p.parse_args()


def _run_pipeline(
    target: ReproductionTarget,
    reasoner_enabled: bool,
    model: str,
    ollama_url: str,
) -> tuple[bool, float]:
    """Run the multi-agent pipeline for *target* and return (success, elapsed_s)."""
    exp_name = f"repro_{target.name}_r{'on' if reasoner_enabled else 'off'}"
    env = os.environ.copy()
    env["ONTOLOGY_EXPERIMENT_NAME"] = exp_name
    env["HITL_SEED_ONTOLOGY_PATH"] = str(target.seed_path)
    env["HITL_REASONER_ENABLED"] = "true" if reasoner_enabled else "false"
    if model:
        env["HITL_OLLAMA_MODEL"] = model
    if ollama_url:
        env["HITL_OLLAMA_URL"] = ollama_url

    cmd = [sys.executable, "scripts/run_full_pipeline.py", "--experiment-name", exp_name]
    t0 = time.time()
    result = subprocess.run(cmd, env=env, capture_output=False, text=True)
    elapsed = time.time() - t0
    return result.returncode == 0, elapsed


def _score_run(
    target: ReproductionTarget,
    reasoner_enabled: bool,
    bench: OEOBenchmark,
) -> dict:
    """Score the pipeline output for *target* against its gold."""
    exp_name = f"repro_{target.name}_r{'on' if reasoner_enabled else 'off'}"
    output_dir = Path("data/exports") / exp_name
    # Try common export filenames
    for fname in ("ontology_latest.owl", "ontology_extended.owl", "extended_ontology.owl",
                  "output.owl", "ontology.owl"):
        candidate = output_dir / fname
        if candidate.exists():
            score = bench.score_reproduction(
                generated_path=candidate,
                gold_path=target.gold_path,
                seed_path=target.seed_path,
            )
            return {"output_file": str(candidate), **score.to_dict()}
    return {"output_file": None, "error": f"No output file found in {output_dir}"}


def main() -> None:
    args = parse_args()

    # ── Pre-flight model check ────────────────────────────────────────────────
    if args.model or args.ollama_url:
        model = args.model or os.environ.get("HITL_OLLAMA_MODEL", "")
        url = args.ollama_url or os.environ.get("HITL_OLLAMA_URL", "http://localhost:11434")
        if model:
            result = check_ollama_model(url, model, raise_on_failure=True)
            print(f"✓ {result.message}\n")

    # ── Select targets ────────────────────────────────────────────────────────
    targets = [
        t for t in REGISTRY_ORDERED
        if t.complexity <= args.complexity_max
        and (not args.targets or t.name in args.targets)
    ]
    if not targets:
        print("No targets match the given filters.")
        sys.exit(1)

    print(f"\nReproduction Benchmark Suite — {len(targets)} target(s)\n")
    print(f"{'Name':<12} {'Complexity':<14} {'Description'}")
    print("-" * 70)
    for t in targets:
        print(f"{t.name:<12} {t.complexity.name:<14} {t.description[:50]}…")
    print()

    # ── Prepare (download + split) ───────────────────────────────────────────
    suite = ReproductionSuite(targets=targets)
    print("Preparing ontology files (downloading + creating splits)…")
    suite.prepare_all(timeout=180)
    print("Done.\n")

    if args.dry_run:
        print("=== Dry run: plan only ===")
        for row in suite.delta_summary():
            print(json.dumps(row, indent=2))
        sys.exit(0)

    # ── Reasoner conditions ───────────────────────────────────────────────────
    reasoner_conditions: list[bool]
    if args.reasoner == "on":
        reasoner_conditions = [True]
    elif args.reasoner == "off":
        reasoner_conditions = [False]
    else:
        reasoner_conditions = [False, True]  # off first → on second (natural ablation)

    # ── Run ───────────────────────────────────────────────────────────────────
    all_results: list[dict] = []
    bench = OEOBenchmark()

    for target in targets:
        if not (target.seed_path.exists() and target.gold_path.exists()):
            logger.warning("repro_skip_not_prepared", target=target.name)
            continue

        delta = suite.delta(target)
        delta_summary = delta.to_dict()["summary"]

        for reasoner_on in reasoner_conditions:
            tag = f"{target.name}/reasoner={'on' if reasoner_on else 'off'}"
            print(f"▶ {tag}")

            success, elapsed = _run_pipeline(
                target, reasoner_on, args.model, args.ollama_url
            )
            score_data = _score_run(target, reasoner_on, bench) if success else {
                "output_file": None, "error": "pipeline_failed"
            }

            all_results.append({
                "target": target.name,
                "complexity": target.complexity.name,
                "reasoner_enabled": reasoner_on,
                "model": args.model or os.environ.get("HITL_OLLAMA_MODEL", ""),
                "pipeline_success": success,
                "elapsed_s": round(elapsed, 1),
                "gold_delta": delta_summary,
                "score": score_data,
            })
            status = "✓" if success else "✗"
            print(f"  {status} {elapsed:.0f}s")

    # ── Write results ─────────────────────────────────────────────────────────
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults written to {output_path}")

    # ── Markdown summary table ────────────────────────────────────────────────
    md_path = output_path.with_suffix(".md")
    _write_markdown(all_results, md_path)
    print(f"Summary table written to {md_path}")


def _write_markdown(results: list[dict], path: Path) -> None:
    lines = [
        "# Reproduction Benchmark Results\n",
        "| Target | Complexity | Reasoner | Pipeline | Elapsed | Class F1 | Prop F1 | Subclass F1 | Consistent |",
        "|--------|------------|----------|----------|---------|----------|---------|-------------|------------|",
    ]
    for r in results:
        sc = r.get("score", {})
        cls = sc.get("classes", {})
        prop = sc.get("properties", {})
        sub = sc.get("subclass_axioms", {})
        lines.append(
            f"| {r['target']} "
            f"| {r['complexity']} "
            f"| {'on' if r['reasoner_enabled'] else 'off'} "
            f"| {'✓' if r['pipeline_success'] else '✗'} "
            f"| {r['elapsed_s']}s "
            f"| {cls.get('f1', '—')} "
            f"| {prop.get('f1', '—')} "
            f"| {sub.get('f1', '—')} "
            f"| {sc.get('consistent', '—')} |"
        )
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

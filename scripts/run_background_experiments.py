#!/usr/bin/env python3
"""
Background experiment runner for overnight execution.

Usage:
    python scripts/run_background_experiments.py --suite small_model_experiments.json
    python scripts/run_background_experiments.py --suite ablation_suite.json --datasets wine,plan
    python scripts/run_background_experiments.py --suite all --timeout 14400  # Run everything for 4 hours max
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('background_run.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_experiment_suite(suite_name: str) -> list[dict]:
    """Load experiment suite from JSON config."""
    suite_path = Path(f"experiments/{suite_name}")
    
    if not suite_path.exists():
        raise FileNotFoundError(f"Experiment suite not found: {suite_path}")
    
    with open(suite_path) as f:
        experiments = json.load(f)
    
    logger.info(f"Loaded {len(experiments)} experiments from {suite_name}")
    return experiments


def run_experiment(exp: dict, datasets: list[str] | None = None, timeout_seconds: int = 3600) -> dict:
    """Run a single experiment."""
    exp_name = exp.get("name", "unknown")
    logger.info(f"Starting experiment: {exp_name}")
    
    try:
        # Build command
        cmd = ["python", "scripts/run_full_pipeline.py"]
        
        # Add dataset selection
        if datasets:
            cmd.extend(["--datasets", ",".join(datasets)])
        
        # Add experiment-specific config
        if "model" in exp:
            cmd.extend(["--model", exp["model"]])
        
        if "timeout_seconds" in exp:
            timeout = min(exp["timeout_seconds"], timeout_seconds)
        else:
            timeout = timeout_seconds
        
        # Run with timeout
        start_time = time.time()
        result = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True
        )
        elapsed = time.time() - start_time
        
        # Log results
        if result.returncode == 0:
            logger.info(f"✓ {exp_name} completed in {elapsed:.1f}s")
            return {
                "name": exp_name,
                "status": "success",
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.warning(f"✗ {exp_name} failed with code {result.returncode}")
            logger.debug(f"STDERR: {result.stderr[:500]}")
            return {
                "name": exp_name,
                "status": "failed",
                "elapsed_seconds": elapsed,
                "error": result.stderr[:200],
                "timestamp": datetime.now().isoformat()
            }
    
    except subprocess.TimeoutExpired:
        logger.warning(f"✗ {exp_name} timed out after {timeout}s")
        return {
            "name": exp_name,
            "status": "timeout",
            "timeout_seconds": timeout,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"✗ {exp_name} error: {str(e)}")
        return {
            "name": exp_name,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


def run_background_suite(
    suite_names: list[str],
    datasets: list[str] | None = None,
    max_duration_seconds: int = 86400,  # 24 hours
    parallel: bool = False
):
    """Run multiple experiment suites."""
    
    all_results = []
    start_time = time.time()
    
    # Load all experiments
    all_experiments = []
    for suite_name in suite_names:
        try:
            exps = load_experiment_suite(suite_name)
            all_experiments.extend(exps)
        except FileNotFoundError as e:
            logger.error(f"Could not load {suite_name}: {e}")
    
    logger.info(f"Running {len(all_experiments)} total experiments (max {max_duration_seconds}s)")
    
    # Run experiments
    for i, exp in enumerate(all_experiments, 1):
        # Check if we've exceeded max duration
        elapsed = time.time() - start_time
        if elapsed > max_duration_seconds * 0.9:  # Stop at 90% of max to allow cleanup
            logger.warning(f"Approaching max duration limit. Stopping after {i-1}/{len(all_experiments)} experiments.")
            break
        
        remaining_time = max_duration_seconds - elapsed
        result = run_experiment(exp, datasets=datasets, timeout_seconds=int(remaining_time))
        all_results.append(result)
        
        logger.info(f"Progress: {i}/{len(all_experiments)} | Elapsed: {elapsed/60:.1f}m")
    
    # Save results
    results_file = f"background_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump({
            "suite": suite_names,
            "datasets": datasets or ["all"],
            "total_duration_seconds": time.time() - start_time,
            "experiments_run": len(all_results),
            "results": all_results
        }, f, indent=2)
    
    logger.info(f"Results saved to {results_file}")
    
    # Summary
    successful = sum(1 for r in all_results if r['status'] == 'success')
    failed = sum(1 for r in all_results if r['status'] in ('failed', 'error'))
    timeout = sum(1 for r in all_results if r['status'] == 'timeout')
    
    logger.info(f"\n{'='*60}")
    logger.info(f"BACKGROUND RUN COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total experiments: {len(all_results)}")
    logger.info(f"  ✓ Successful: {successful}")
    logger.info(f"  ✗ Failed: {failed}")
    logger.info(f"  ⏱ Timeout: {timeout}")
    logger.info(f"Total time: {(time.time() - start_time)/60:.1f} minutes")
    logger.info(f"{'='*60}\n")
    
    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run experiment suites in the background"
    )
    parser.add_argument(
        "--suite",
        action="append",
        dest="suites",
        default=[],
        help="Experiment suite to run (can specify multiple times)"
    )
    parser.add_argument(
        "--datasets",
        type=str,
        default="",
        help="Comma-separated list of datasets (wine,plan,etc)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=86400,
        help="Max duration in seconds (default: 24 hours)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all available experiment suites"
    )
    
    args = parser.parse_args()
    
    # Determine which suites to run
    if args.all:
        suites = [
            "small_model_experiments.json",
            "ablation_suite.json"
        ]
    elif args.suites:
        suites = [s if s.endswith('.json') else f"{s}.json" for s in args.suites]
    else:
        parser.print_help()
        sys.exit(1)
    
    # Parse datasets
    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()] or None
    
    # Run
    try:
        run_background_suite(
            suites,
            datasets=datasets,
            max_duration_seconds=args.timeout
        )
    except KeyboardInterrupt:
        logger.info("Background run interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

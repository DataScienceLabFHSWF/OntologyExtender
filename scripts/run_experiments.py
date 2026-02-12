#!/usr/bin/env python3
"""Run ontology extension experiments with different debate strategies.

This script allows running the full pipeline with different debate strategies
and comparing their performance across multiple metrics.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class ExperimentConfig(BaseModel):
    """Configuration for a single experiment run."""

    name: str
    model: str = ""  # Model name for grouping parallel experiments
    strategy_overrides: Dict[str, str]  # phase -> strategy mapping
    description: str = ""
    structured_output: bool = False
    method: str = ""  # "llm_only" for LLM-only experiments
    strategy: str = ""  # Strategy for LLM-only experiments
    timeout_seconds: int = 0  # Timeout for LLM-only experiments
    temperature: float = 0.5  # Temperature for LLM-only experiments


class ExperimentResult(BaseModel):
    """Results from a single experiment run."""

    experiment_name: str
    strategy_overrides: Dict[str, str]
    success: bool
    error_message: Optional[str] = None
    metrics: Dict = {}
    classes_added: int = 0
    cq_coverage: float = 0.0
    entity_coverage: float = 0.0
    execution_time_seconds: float = 0.0


class ExperimentRunner:
    """Run ontology extension experiments with different strategies."""

    def __init__(self, base_dir: Path, results_dir: Path):
        self.base_dir = base_dir
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def clean_workspace(self, experiment_name: str = ""):
        """Clean intermediate files for a fresh run without destroying other experiments."""
        logger.info("cleaning_workspace", experiment=experiment_name)

        # Only clean the v1 working directory (used by feedback loop)
        # Never touch experiment-specific archived directories
        v1_dir = self.base_dir / "data" / "iterations" / "v1"
        if v1_dir.exists():
            shutil.rmtree(v1_dir)
        v1_dir.mkdir(parents=True, exist_ok=True)

        # Clean the flat exports dir (working area), but not experiment subdirs
        exports_dir = self.base_dir / "data" / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        for item in exports_dir.iterdir():
            if item.is_file():  # Only remove files, keep experiment subdirs
                item.unlink()

    def modify_strategy_config(self, overrides: Dict[str, str]):
        """Temporarily modify the debate strategy configuration."""
        moderator_file = self.base_dir / "src" / "ontology_hitl" / "agents" / "moderator.py"

        # Read current content
        with open(moderator_file, 'r') as f:
            content = f.read()

        # Create backup
        backup_file = moderator_file.with_suffix('.bak')
        with open(backup_file, 'w') as f:
            f.write(content)

        # Apply overrides to strategy_map
        modified_content = content
        for phase, strategy in overrides.items():
            # Find the line that sets the strategy for this phase
                pattern = rf'Phase\.{phase.upper()}: DebateStrategy\.'
                if pattern in modified_content:
                    # Replace the strategy
                    import re
                    modified_content = re.sub(
                        rf'(Phase\.{phase.upper()}: DebateStrategy\.)[A-Z_]+',
                        rf'\1{strategy.upper()}',
                )

        # Write modified content
        with open(moderator_file, 'w') as f:
            f.write(modified_content)

        return backup_file

    def restore_strategy_config(self, backup_file: Path):
        """Restore the original strategy configuration."""
        moderator_file = self.base_dir / "src" / "ontology_hitl" / "agents" / "moderator.py"
        shutil.move(str(backup_file), str(moderator_file))

    def archive_experiment_data(self, experiment_name: str):
        """Copy iteration data from v1 working dir to experiment-specific archive."""
        v1_dir = self.base_dir / "data" / "iterations" / "v1"
        archive_dir = self.base_dir / "data" / "iterations" / experiment_name
        archive_dir.mkdir(parents=True, exist_ok=True)

        if v1_dir.exists():
            for item in v1_dir.iterdir():
                dest = archive_dir / item.name
                if item.is_file():
                    shutil.copy2(str(item), str(dest))
                elif item.is_dir():
                    if dest.exists():
                        shutil.rmtree(str(dest))
                    shutil.copytree(str(item), str(dest))

        # Also copy convergence report from exports to experiment subdir
        convergence_src = self.base_dir / "data" / "exports" / "convergence_report.json"
        exports_archive = self.base_dir / "data" / "exports" / experiment_name
        exports_archive.mkdir(parents=True, exist_ok=True)

        if convergence_src.exists():
            shutil.copy2(str(convergence_src), str(exports_archive / "convergence_report.json"))

        logger.info("archived_experiment_data",
                    experiment=experiment_name,
                    iterations_dir=str(archive_dir),
                    exports_dir=str(exports_archive))

    def run_pipeline(self, experiment_name: str = "", model: str = "") -> tuple[bool, str, float]:
        """Run the full pipeline and return success status and execution time."""
        import time
        start_time = time.time()
        timeout_seconds = self._get_timeout_for_model(model)

        try:
            # Set environment variable for experiment-specific output directory
            env = os.environ.copy()
            if experiment_name:
                env["ONTOLOGY_EXPERIMENT_NAME"] = experiment_name
                
            cmd = [sys.executable, "scripts/run_full_pipeline.py"]
            if experiment_name:
                cmd.extend(["--experiment-name", experiment_name])
                
            result = subprocess.run(
                cmd,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_seconds
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                logger.info("pipeline_success", execution_time=execution_time)
                return True, result.stdout + result.stderr, execution_time
            else:
                logger.error("pipeline_failed", returncode=result.returncode,
                           stderr=result.stderr)
                return False, result.stderr, execution_time

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            logger.error("pipeline_timeout", execution_time=execution_time,
                        timeout=timeout_seconds, model=model)
            return False, f"Pipeline timed out after {timeout_seconds // 60} minutes", execution_time

    def extract_metrics(self, experiment_name: str = "") -> Dict:
        """Extract metrics from the completed run."""
        metrics = {}

        # Determine output directories
        if experiment_name:
            output_dir = f"data/exports/{experiment_name}"
            iteration_dir = f"data/iterations/{experiment_name}"
        else:
            output_dir = "data/exports"
            iteration_dir = "data/iterations/v1"

        # Try to read convergence report
        convergence_file = self.base_dir / output_dir / "convergence_report.json"
        if convergence_file.exists():
            try:
                with open(convergence_file, 'r') as f:
                    data = json.load(f)
                    summary = data.get('summary', {})
                    metrics.update({
                        'classes_added_total': summary.get('classes_added_total', 0),
                        'cq_coverage_final': summary.get('cq_coverage', {}).get('final', 0.0),
                        'entity_coverage_final': summary.get('entity_coverage', {}).get('final', 0.0),
                        'acceptance_rate_avg': summary.get('acceptance_rate_avg', 0.0),
                    })
            except Exception as e:
                logger.warning("failed_to_read_convergence", error=str(e))

        # Try to read iteration summary
        iteration_file = self.base_dir / iteration_dir / "iteration_summary.json"
        if iteration_file.exists():
            try:
                with open(iteration_file, 'r') as f:
                    data = json.load(f)
                    metrics.update({
                        'new_classes': data.get('new_classes_count', 0),
                        'cq_coverage_pct': data.get('cq_coverage_pct', 0.0),
                        'entity_coverage_pct': data.get('entity_coverage_pct', 0.0),
                    })
            except Exception as e:
                logger.warning("failed_to_read_iteration_summary", error=str(e))

        return metrics

    def run_experiment_thread_safe(self, config: ExperimentConfig) -> ExperimentResult:
        """Run a single experiment with thread-safe isolation."""
        import threading

        thread_id = threading.current_thread().ident
        # Use original clean experiment name, not thread-suffixed
        experiment_name = config.name
        # Create thread-specific working directory name for isolation
        temp_dir_name = f"v1_thread_{thread_id}"

        logger.info("starting_thread_safe_experiment",
                   name=config.name,
                   thread=threading.current_thread().name,
                   temp_dir=temp_dir_name)

        try:
            # Create thread-specific working directory
            temp_iterations_dir = self.base_dir / "data" / "iterations" / temp_dir_name
            temp_iterations_dir.mkdir(parents=True, exist_ok=True)

            # Copy seed data to thread-specific location
            v1_dir = self.base_dir / "data" / "iterations" / "v1"
            if v1_dir.exists():
                for item in v1_dir.iterdir():
                    dest = temp_iterations_dir / item.name
                    if item.is_file():
                        shutil.copy2(str(item), str(dest))

            # Apply strategy overrides with thread-safe locking
            backup_file = None
            if config.strategy_overrides:
                # Use file locking to make strategy config modification thread-safe
                import fcntl
                moderator_file = self.base_dir / "src" / "ontology_hitl" / "agents" / "moderator.py"

                with open(moderator_file, 'r+') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
                    try:
                        content = f.read()
                        backup_content = content

                        # Apply overrides
                        modified_content = content
                        for phase, strategy in config.strategy_overrides.items():
                            import re
                            modified_content = re.sub(
                                rf'(Phase\.{phase.upper()}: DebateStrategy\.)[A-Z_]+',
                                rf'\1{strategy.upper()}',
                                modified_content
                            )

                        # Write modified content
                        f.seek(0)
                        f.write(modified_content)
                        f.truncate()
                        backup_file = (moderator_file, backup_content)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock

            # Set environment variable for experiment-specific output and model config
            env = os.environ.copy()
            env["ONTOLOGY_EXPERIMENT_NAME"] = experiment_name
            if config.model:
                env["HITL_OLLAMA_MODEL"] = config.model
            if config.temperature:
                env["HITL_LLM_TEMPERATURE"] = str(config.temperature)

            # Run pipeline with thread-specific environment
            success, output, execution_time = self.run_pipeline_with_env(experiment_name, env)

            # Archive results if successful
            if success:
                self.archive_experiment_data_thread_safe(experiment_name, temp_iterations_dir)

            # Extract metrics
            metrics = {}
            if success:
                metrics = self.extract_metrics(experiment_name)

            result = ExperimentResult(
                experiment_name=config.name,  # Use original name for results
                strategy_overrides=config.strategy_overrides,
                success=success,
                error_message=None if success else output,
                metrics=metrics,
                classes_added=metrics.get('classes_added_total', 0),
                cq_coverage=metrics.get('cq_coverage_final', 0.0),
                entity_coverage=metrics.get('entity_coverage_final', 0.0),
                execution_time_seconds=execution_time,
            )

            logger.info("thread_safe_experiment_completed",
                       name=config.name,
                       success=success,
                       execution_time=execution_time,
                       thread=threading.current_thread().name)

            return result

        finally:
            # Restore strategy config
            if backup_file:
                moderator_file, backup_content = backup_file
                with open(moderator_file, 'w') as f:
                    f.write(backup_content)

            # Clean up thread-specific directory
            if temp_iterations_dir.exists():
                shutil.rmtree(str(temp_iterations_dir))

    def _get_timeout_for_model(self, model: str) -> int:
        """Return subprocess timeout in seconds based on model size.

        Ollama serialises inference requests internally.  When multiple
        experiments hit the same endpoint the effective wait time per
        request multiplies, so larger models need generous timeouts.
        """
        model_lower = (model or "").lower()
        if any(k in model_lower for k in ("qwen", "79b", "72b", "70b")):
            return 5400   # 90 min for large models
        elif any(k in model_lower for k in ("nemotron", "14b", "8b")):
            return 3600   # 60 min for medium models
        else:
            return 1800   # 30 min for small models

    def run_pipeline_with_env(self, experiment_name: str, env: dict) -> tuple[bool, str, float]:
        """Run the pipeline with custom environment variables."""
        import time
        start_time = time.time()

        # Derive timeout from the model being used
        model = env.get("HITL_OLLAMA_MODEL", "")
        timeout_seconds = self._get_timeout_for_model(model)

        try:
            # Explicitly set W&B environment variables for subprocess
            env["HITL_WANDB_ENABLED"] = "true"
            env["HITL_WANDB_ENTITY"] = "dsfhswf"
            env["HITL_WANDB_PROJECT"] = "ontology-hitl"
            env["HITL_WANDB_API_KEY"] = "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"

            cmd = [sys.executable, "scripts/run_full_pipeline.py"]
            if experiment_name:
                cmd.extend(["--experiment-name", experiment_name])

            logger.info("pipeline_starting", experiment=experiment_name,
                       model=model, timeout=timeout_seconds)

            result = subprocess.run(
                cmd,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_seconds
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                logger.info("pipeline_success", execution_time=execution_time)
                return True, result.stdout + result.stderr, execution_time
            else:
                logger.error("pipeline_failed", returncode=result.returncode,
                           stderr=result.stderr)
                return False, result.stderr, execution_time

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            logger.error("pipeline_timeout", execution_time=execution_time,
                        timeout=timeout_seconds, model=model)
            return False, f"Pipeline timed out after {timeout_seconds // 60} minutes", execution_time

    def archive_experiment_data_thread_safe(self, experiment_name: str, temp_dir: Path):
        """Archive experiment data from thread-specific directory."""
        archive_dir = self.base_dir / "data" / "iterations" / experiment_name
        archive_dir.mkdir(parents=True, exist_ok=True)

        if temp_dir.exists():
            for item in temp_dir.iterdir():
                dest = archive_dir / item.name
                if item.is_file():
                    shutil.copy2(str(item), str(dest))
                elif item.is_dir():
                    if dest.exists():
                        shutil.rmtree(str(dest))
                    shutil.copytree(str(item), str(dest))

        # Also copy convergence report
        convergence_src = self.base_dir / "data" / "exports" / experiment_name / "convergence_report.json"
        if convergence_src.exists():
            shutil.copy2(str(convergence_src), str(archive_dir / "convergence_report.json"))

        logger.info("archived_thread_safe_experiment_data",
                    experiment=experiment_name,
                    archive_dir=str(archive_dir))

        # Also copy convergence report
        convergence_src = self.base_dir / "data" / "exports" / experiment_name / "convergence_report.json"
        if convergence_src.exists():
            shutil.copy2(str(convergence_src), str(archive_dir / "convergence_report.json"))

        logger.info("archived_thread_safe_experiment_data",
                    experiment=experiment_name,
                    archive_dir=str(archive_dir))

    def _run_command(self, command: str) -> str:
        """Run a shell command and return output."""
        result = subprocess.run(command, shell=True, cwd=self.base_dir,
                              capture_output=True, text=True)
        return result.stdout.strip()

    def group_experiments_by_model(self, experiments: List[ExperimentConfig]) -> Dict[str, List[ExperimentConfig]]:
        """Group experiments by model to enable parallel execution."""
        groups = defaultdict(list)

        for exp in experiments:
            # Extract model family for grouping
            model = exp.model.lower()
            if "llama3.2:3b" in model or "llama3.2" in model:
                group_key = "small"
            elif "nemotron" in model:
                group_key = "medium"  # nemotron-3-nano is medium-sized
            elif "qwen" in model or "79b" in model or "72b" in model or "70b" in model:
                group_key = "large"
            else:
                group_key = "medium"  # Default to medium for unknown models

            groups[group_key].append(exp)

        return dict(groups)

    def run_llm_only_experiment(self, config: ExperimentConfig) -> ExperimentResult:
        """Run an LLM-only experiment."""
        import time
        import os
        start_time = time.time()

        try:
            # Set environment variable for experiment-specific output and model config
            env = os.environ.copy()
            env["ONTOLOGY_EXPERIMENT_NAME"] = config.name
            if config.model:
                env["HITL_OLLAMA_MODEL"] = config.model
            if hasattr(config, 'temperature') and config.temperature:
                env["HITL_LLM_TEMPERATURE"] = str(config.temperature)
            
            # Explicitly set W&B environment variables for subprocess
            env["HITL_WANDB_ENABLED"] = "true"
            env["HITL_WANDB_ENTITY"] = "dsfhswf"
            env["HITL_WANDB_PROJECT"] = "ontology-hitl"
            env["HITL_WANDB_API_KEY"] = "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"

            # Set up command for LLM-only baseline
            cmd = [
                sys.executable, "scripts/llm_only_baseline.py",
                "--model", config.model,
                "--strategy", config.strategy,
                "--output", f"data/exports/{config.name}",
                "--experiment-name", config.name
            ]

            # Add timeout if specified
            if config.timeout_seconds > 0:
                cmd.extend(["--timeout", str(config.timeout_seconds)])

            # Add temperature if specified
            if hasattr(config, 'temperature'):
                cmd.extend(["--temperature", str(config.temperature)])

            result = subprocess.run(
                cmd,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                env=env,
                timeout=config.timeout_seconds or 1800  # Default 30 min timeout
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                logger.info("llm_experiment_success", name=config.name, execution_time=execution_time)
                return ExperimentResult(
                    experiment_name=config.name,
                    strategy_overrides=config.strategy_overrides,
                    success=True,
                    error_message=None,
                    metrics={},
                    classes_added=0,  # Will be extracted from output
                    cq_coverage=0.0,
                    entity_coverage=0.0,
                    execution_time_seconds=execution_time,
                )
            else:
                logger.error("llm_experiment_failed", name=config.name, returncode=result.returncode, stderr=result.stderr)
                return ExperimentResult(
                    experiment_name=config.name,
                    strategy_overrides=config.strategy_overrides,
                    success=False,
                    error_message=result.stderr,
                    metrics={},
                    classes_added=0,
                    cq_coverage=0.0,
                    entity_coverage=0.0,
                    execution_time_seconds=execution_time,
                )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            logger.error("llm_experiment_timeout", name=config.name, execution_time=execution_time)
            return ExperimentResult(
                experiment_name=config.name,
                strategy_overrides=config.strategy_overrides,
                success=False,
                error_message=f"Experiment timed out after {config.timeout_seconds or 1800} seconds",
                metrics={},
                classes_added=0,
                cq_coverage=0.0,
                entity_coverage=0.0,
                execution_time_seconds=execution_time,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error("llm_experiment_error", name=config.name, error=str(e))
            return ExperimentResult(
                experiment_name=config.name,
                strategy_overrides=config.strategy_overrides,
                success=False,
                error_message=str(e),
                metrics={},
                classes_added=0,
                cq_coverage=0.0,
                entity_coverage=0.0,
                execution_time_seconds=execution_time,
            )


def create_default_experiments() -> List[ExperimentConfig]:
    """Create a set of default experiments to run."""
    return [
        ExperimentConfig(
            name="baseline_consensus",
            strategy_overrides={},
            description="Default consensus-building strategy for all phases"
        ),
        ExperimentConfig(
            name="dialectical_focused",
            strategy_overrides={
                "hierarchy": "dialectical",
                "properties": "dialectical",
            },
            description="Use dialectical strategy for structural phases"
        ),
        ExperimentConfig(
            name="socratic_focused",
            strategy_overrides={
                "scope": "socratic",
                "terms": "socratic",
            },
            description="Use Socratic strategy for conceptual phases"
        ),
        ExperimentConfig(
            name="delphi_consensus",
            strategy_overrides={
                "facets": "delphi",
                "instances": "delphi",
            },
            description="Use Delphi method for detailed specification phases"
        ),
        ExperimentConfig(
            name="abductive_instances",
            strategy_overrides={
                "instances": "abductive",
            },
            description="Use abductive reasoning for instance generation"
        ),
        ExperimentConfig(
            name="mixed_strategy",
            strategy_overrides={
                "scope": "socratic",
                "reuse": "consensus_building",
                "terms": "socratic",
                "hierarchy": "dialectical",
                "properties": "dialectical",
                "facets": "delphi",
                "instances": "abductive",
            },
            description="Use different strategies optimized for each phase"
        ),
    ]


def main():
    parser = argparse.ArgumentParser(description="Run ontology extension experiments")
    parser.add_argument("--experiments", type=Path,
                       help="JSON file with experiment configurations")
    parser.add_argument("--output", type=Path, default=Path("experiment_results.json"),
                       help="Output file for results")
    parser.add_argument("--use-defaults", action="store_true",
                       help="Use default experiment configurations")
    parser.add_argument("--parallel", action="store_true",
                       help="Run experiments in parallel by model group")
    parser.add_argument("--max-workers", type=int, default=3,
                       help="Maximum number of parallel workers (default: 3)")
    parser.add_argument("--interleave-models", action="store_true",
                       help="Interleave experiments across model groups (round-robin). "
                            "Default is sequential: finish all small, then medium, then large. "
                            "Only use interleaved mode if Ollama can serve multiple models concurrently.")
    parser.add_argument("--resume", action="store_true",
                       help="Skip experiments that already succeeded in a previous run. "
                            "Reads the --output file and keeps successful results, "
                            "only re-running failed or missing experiments.")

    args = parser.parse_args()

    # Setup logging
    import logging
    logging.basicConfig(level=logging.INFO)

    # Load experiment configurations
    if args.use_defaults:
        experiments = create_default_experiments()
    elif args.experiments:
        with open(args.experiments, 'r') as f:
            data = json.load(f)
            experiments = [ExperimentConfig(**exp) for exp in data]
    else:
        print("Error: Must specify --experiments file or --use-defaults")
        sys.exit(1)

    # Setup experiment runner
    base_dir = Path.cwd()
    results_dir = base_dir / "experiment_results"
    runner = ExperimentRunner(base_dir, results_dir)

    # Resume: load previous results and skip successful experiments
    prior_results = []
    skipped_names = set()
    if args.resume and args.output.exists():
        with open(args.output, 'r') as f:
            prior_results = json.load(f)
        skipped_names = {
            r['experiment_name'] for r in prior_results if r.get('success')
        }
        if skipped_names:
            experiments = [e for e in experiments if e.name not in skipped_names]
            print(f"⏩ Resuming: skipping {len(skipped_names)} already-successful experiments")
            for name in sorted(skipped_names):
                print(f"   ✔ {name}")
            print(f"   {len(experiments)} experiments remaining\n")
        if not experiments:
            print("✅ All experiments already completed successfully!")
            sys.exit(0)

    if args.parallel:
        # Group experiments by model for parallel execution
        experiment_groups = runner.group_experiments_by_model(experiments)
        total_experiments = len(experiments)

        # Sequential-models mode (default): run one model group at a time
        # to avoid Ollama request queuing across different model sizes.
        # Ollama serialises inference and must swap models in/out of GPU
        # memory — running different models concurrently causes massive
        # slowdowns and timeouts.
        group_order = ["small", "medium", "large"]
        ordered_groups = [(g, experiment_groups[g]) for g in group_order if g in experiment_groups]
        # Add any groups not in the predefined order
        for g, exps in experiment_groups.items():
            if g not in group_order:
                ordered_groups.append((g, exps))

        print(f"🚀 Running {total_experiments} experiments across {len(ordered_groups)} model groups")
        print(f"   Mode: {'sequential models' if not args.interleave_models else 'interleaved (round-robin)'}")
        for group_name, group_experiments in ordered_groups:
            print(f"   • {group_name}: {len(group_experiments)} experiments")

        all_results = []
        completed_experiments = 0

        if not args.interleave_models:
            # DEFAULT: Run each model group fully before moving to the next.
            # Within a group, experiments run in parallel up to max_workers.
            for group_name, group_experiments in ordered_groups:
                print(f"\n{'='*60}")
                print(f"📦 Model group: {group_name} ({len(group_experiments)} experiments, "
                      f"{args.max_workers} workers)")
                print(f"{'='*60}")

                with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
                    futures = {}
                    for config in group_experiments:
                        if config.method == "llm_only":
                            future = executor.submit(runner.run_llm_only_experiment, config)
                        else:
                            future = executor.submit(runner.run_experiment_thread_safe, config)
                        futures[future] = config

                    for future in as_completed(futures.keys()):
                        config = futures[future]
                        try:
                            result = future.result()
                            all_results.append(result.model_dump())
                            completed_experiments += 1

                            print(f"   ✅ {config.name} ({group_name}) completed ({completed_experiments}/{total_experiments})")
                            if result.success:
                                print(f"      📊 Classes: {result.classes_added}, Time: {result.execution_time_seconds:.1f}s")
                            else:
                                print(f"      ❌ Failed: {result.error_message[:100]}...")

                        except Exception as e:
                            print(f"   ❌ {config.name} failed with exception: {e}")
                            error_result = ExperimentResult(
                                experiment_name=config.name,
                                strategy_overrides=config.strategy_overrides,
                                success=False,
                                error_message=str(e),
                                metrics={},
                                classes_added=0,
                                cq_coverage=0.0,
                                entity_coverage=0.0,
                                execution_time_seconds=0.0,
                            )
                            all_results.append(error_result.model_dump())
                            completed_experiments += 1

                        # Save intermediate results
                        with open(args.output, 'w') as f:
                            json.dump(all_results, f, indent=2)

        else:
            # INTERLEAVED: Original round-robin across model groups.
            # Use this only if Ollama can handle concurrent model serving.
            print(f"\n⚡ Using {args.max_workers} parallel workers (round-robin across groups)...")
            from collections import deque
            group_queues = {name: deque(group) for name, group in experiment_groups.items()}
            active_futures = {}

            with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
                while completed_experiments < total_experiments:
                    for group_name, queue in group_queues.items():
                        if queue and len(active_futures) < args.max_workers:
                            config = queue.popleft()
                            if config.method == "llm_only":
                                future = executor.submit(runner.run_llm_only_experiment, config)
                            else:
                                future = executor.submit(runner.run_experiment_thread_safe, config)
                            active_futures[future] = (group_name, config)

                    if active_futures:
                        for future in as_completed(active_futures.keys()):
                            group_name, config = active_futures[future]
                            del active_futures[future]

                            try:
                                result = future.result()
                                all_results.append(result.model_dump())
                                completed_experiments += 1

                                print(f"   ✅ {config.name} ({group_name}) completed ({completed_experiments}/{total_experiments})")
                                if result.success:
                                    print(f"      📊 Classes: {result.classes_added}, Time: {result.execution_time_seconds:.1f}s")
                                else:
                                    print(f"      ❌ Failed: {result.error_message[:100]}...")

                            except Exception as e:
                                print(f"   ❌ {config.name} failed with exception: {e}")
                                error_result = ExperimentResult(
                                    experiment_name=config.name,
                                    strategy_overrides=config.strategy_overrides,
                                    success=False,
                                    error_message=str(e),
                                    metrics={},
                                    classes_added=0,
                                    cq_coverage=0.0,
                                    entity_coverage=0.0,
                                    execution_time_seconds=0.0,
                                )
                                all_results.append(error_result.model_dump())
                                completed_experiments += 1

                            with open(args.output, 'w') as f:
                                json.dump(all_results, f, indent=2)
                    else:
                        import time
                        time.sleep(0.1)

        print(f"\n🎉 All {total_experiments} experiments completed!")

    else:
        # Original sequential execution
        results = []
        for i, config in enumerate(experiments, 1):
            print(f"\n🧪 Running Experiment {i}/{len(experiments)}: {config.name}")
            print(f"   {config.description}")
            print(f"   Strategy overrides: {config.strategy_overrides}")

            if config.method == "llm_only":
                result = runner.run_llm_only_experiment(config)
            else:
                result = runner.run_experiment_thread_safe(config)
            results.append(result.model_dump())

            # Save intermediate results
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)

            print(f"   ✅ Success: {result.success}")
            if result.success:
                print(f"   📊 Classes added: {result.classes_added}")
                print(f"   📊 CQ Coverage: {result.cq_coverage:.1%}")
                print(f"   ⏱️  Execution time: {result.execution_time_seconds:.1f}s")

        all_results = results

    # Merge prior successful results back in when resuming
    if prior_results and skipped_names:
        # Keep prior successes, replace prior failures with new results
        new_names = {r['experiment_name'] for r in all_results}
        merged = [r for r in prior_results if r.get('success') and r['experiment_name'] not in new_names]
        merged.extend(all_results)
        all_results = merged

    # Save final merged results
    with open(args.output, 'w') as f:
        json.dump(all_results, f, indent=2)

    # Print summary
    print(f"\n📊 Experiment Summary ({len(all_results)} experiments)")
    print("=" * 60)

    successful = [r for r in all_results if r['success']]
    if successful:
        avg_classes = sum(r['classes_added'] for r in successful) / len(successful)
        avg_cq = sum(r['cq_coverage'] for r in successful) / len(successful)
        avg_time = sum(r['execution_time_seconds'] for r in successful) / len(successful)

        print(f"Successful experiments: {len(successful)}/{len(all_results)}")
        print(f"Average classes added: {avg_classes:.1f}")
        print(f"Average CQ coverage: {avg_cq:.1%}")
        print(f"Average execution time: {avg_time:.1f}s")

        # Find best performers
        best_classes = max(successful, key=lambda x: x['classes_added'])
        best_cq = max(successful, key=lambda x: x['cq_coverage'])

        print(f"\n🏆 Best by classes added: {best_classes['experiment_name']} ({best_classes['classes_added']})")
        print(f"🏆 Best by CQ coverage: {best_cq['experiment_name']} ({best_cq['cq_coverage']:.1%})")

    print(f"\n📄 Detailed results saved to: {args.output}")


if __name__ == "__main__":
    main()
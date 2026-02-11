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
from pathlib import Path
from typing import Dict, List, Optional

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class ExperimentConfig(BaseModel):
    """Configuration for a single experiment run."""

    name: str
    strategy_overrides: Dict[str, str]  # phase -> strategy mapping
    description: str = ""


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
            pattern = f'Phase.{phase.upper()}: DebateStrategy.'
            if pattern in modified_content:
                # Replace the strategy
                import re
                modified_content = re.sub(
                    f'(Phase.{phase.upper()}: DebateStrategy\.)[A-Z_]+',
                    f'\\1{strategy.upper()}',
                    modified_content
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

    def run_pipeline(self, experiment_name: str = "") -> tuple[bool, str, float]:
        """Run the full pipeline and return success status and execution time."""
        import time
        start_time = time.time()

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
                timeout=1800  # 30 minute timeout
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
            logger.error("pipeline_timeout", execution_time=execution_time)
            return False, "Pipeline timed out after 30 minutes", execution_time

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

    def run_experiment(self, config: ExperimentConfig) -> ExperimentResult:
        """Run a single experiment with the given configuration."""
        logger.info("starting_experiment", name=config.name,
                   overrides=config.strategy_overrides)

        # Clean workspace (only v1 working dir, preserves previous experiment archives)
        self.clean_workspace(config.name)

        # Apply strategy overrides
        backup_file = None
        if config.strategy_overrides:
            backup_file = self.modify_strategy_config(config.strategy_overrides)

        try:
            # Run pipeline (always writes to data/iterations/v1 then we archive)
            success, output, execution_time = self.run_pipeline(config.name)

            # Archive iteration data to experiment-specific directory
            if success:
                self.archive_experiment_data(config.name)

            # Extract metrics if successful
            metrics = {}
            if success:
                metrics = self.extract_metrics(config.name)

            result = ExperimentResult(
                experiment_name=config.name,
                strategy_overrides=config.strategy_overrides,
                success=success,
                error_message=None if success else output,
                metrics=metrics,
                classes_added=metrics.get('classes_added_total', 0),
                cq_coverage=metrics.get('cq_coverage_final', 0.0),
                entity_coverage=metrics.get('entity_coverage_final', 0.0),
                execution_time_seconds=execution_time,
            )

            logger.info("experiment_completed",
                       name=config.name,
                       success=success,
                       classes_added=result.classes_added,
                       execution_time=execution_time)

            return result

        finally:
            # Restore original config
            if backup_file:
                self.restore_strategy_config(backup_file)

    def _run_command(self, command: str) -> str:
        """Run a shell command and return output."""
        result = subprocess.run(command, shell=True, cwd=self.base_dir,
                              capture_output=True, text=True)
        return result.stdout.strip()


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

    # Run experiments
    results = []
    for i, config in enumerate(experiments, 1):
        print(f"\n🧪 Running Experiment {i}/{len(experiments)}: {config.name}")
        print(f"   {config.description}")
        print(f"   Strategy overrides: {config.strategy_overrides}")

        result = runner.run_experiment(config)
        results.append(result.model_dump())

        # Save intermediate results
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"   ✅ Success: {result.success}")
        if result.success:
            print(f"   📊 Classes added: {result.classes_added}")
            print(f"   📊 CQ Coverage: {result.cq_coverage:.1%}")
            print(f"   ⏱️  Execution time: {result.execution_time_seconds:.1f}s")

    # Print summary
    print(f"\n📊 Experiment Summary ({len(results)} experiments)")
    print("=" * 60)

    successful = [r for r in results if r['success']]
    if successful:
        avg_classes = sum(r['classes_added'] for r in successful) / len(successful)
        avg_cq = sum(r['cq_coverage'] for r in successful) / len(successful)
        avg_time = sum(r['execution_time_seconds'] for r in successful) / len(successful)

        print(f"Successful experiments: {len(successful)}/{len(results)}")
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
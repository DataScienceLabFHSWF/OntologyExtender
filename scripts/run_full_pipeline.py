#!/usr/bin/env python3
"""Run the complete Ontology Extension Pipeline.

This script runs the full workflow:
1. Multi-agent debate pipeline (feedback loop)
2. Extract proposals from iteration results
3. Auto-accept all proposals (for testing)
4. Export extended ontology and CQs
5. Run validation and evaluation
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from ontology_hitl.core.config import Settings


def infer_seed_ontology_from_experiment(experiment_name: str) -> str | None:
    """Infer a reproduction benchmark seed ontology from an experiment name."""
    if not experiment_name.startswith("repro_") or "_r" not in experiment_name:
        return None
    target = experiment_name[len("repro_"):experiment_name.index("_r")]
    if not target:
        return None
    candidate_dir = Path("data/benchmark_datasets/reproduction") / target
    if not candidate_dir.exists():
        return None
    for pattern in ("*seed*.ttl", "*seed*.owl", "*seed*.rdf", "*seed*.xml"):
        matches = sorted(candidate_dir.glob(pattern))
        if matches:
            return str(matches[0])
    return None


def write_skip_evaluation_report(before_path: Path, after_path: Path, output_path: Path) -> None:
    report = {
        "before_file": str(before_path),
        "after_file": str(after_path),
        "metrics": [],
        "summary": {"improved": 0, "degraded": 0, "unchanged": 0},
        "notes": "Skipped evaluation because competency question files were passed instead of KG metrics JSON.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)


def is_json_list(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with open(path) as f:
            data = json.load(f)
        return isinstance(data, list)
    except Exception:
        return False


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"COMMAND: {' '.join(cmd)}")
    print('='*60)

    try:
        result = subprocess.run(cmd, capture_output=False, text=True, cwd=Path.cwd())
        if result.returncode != 0:
            print(f"ERROR: Command failed with exit code {result.returncode}")
            if result.stderr:
                print(f"STDERR: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"ERROR: Failed to run command: {e}")
        return False

def main():
    """Run the complete pipeline."""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Run the complete ontology extension pipeline")
    parser.add_argument("--experiment-name", default="", help="Experiment name for wandb run naming")
    args = parser.parse_args()
    
    # Use experiment-specific output directory if experiment name provided
    experiment_name = args.experiment_name or os.environ.get("ONTOLOGY_EXPERIMENT_NAME", "")
    if experiment_name:
        output_dir = f"data/exports/{experiment_name}"
        iteration_dir = f"data/iterations/{experiment_name}"
        print(f"Using experiment-specific output directory: {output_dir}")
    else:
        output_dir = "data/exports"
        iteration_dir = "data/iterations/v1"
    
    print("ONTOLOGY EXTENSION PIPELINE - FULL WORKFLOW")
    print("=" * 60)

    # Step 0: load settings so environment overrides like HITL_SEED_ONTOLOGY_PATH
    settings = Settings()
    seed_ontology = os.environ.get("HITL_SEED_ONTOLOGY_PATH", "") or settings.seed_ontology_path
    if not os.environ.get("HITL_SEED_ONTOLOGY_PATH") and experiment_name:
        inferred_seed = infer_seed_ontology_from_experiment(experiment_name)
        if inferred_seed:
            seed_ontology = inferred_seed
            print(f"Inferred reproduction seed ontology from experiment name: {seed_ontology}")

    # Ensure the feedback loop subprocess inherits the selected seed ontology
    os.environ["HITL_SEED_ONTOLOGY_PATH"] = seed_ontology
    print(f"Using seed ontology: {seed_ontology}")

    # Step 1: Run the feedback loop (multi-agent debate)
    cmd = [
        sys.executable, "scripts/run_feedback_loop.py",
        "--mode", "standalone",
        "--max-iterations", "1",
        "--auto-review"
    ]
    if args.experiment_name:
        cmd.extend(["--experiment-name", args.experiment_name])
        
    if not run_command(cmd, "Multi-agent debate pipeline"):
        return False

    # Step 2: Extract proposals from iteration results
    cmd = [sys.executable, "scripts/create_proposals_from_iteration.py"]
    if experiment_name:
        cmd.extend(["--experiment-name", experiment_name])
        
    if not run_command(cmd, "Extract proposals from iteration outputs"):
        return False

    # Step 3: Export the extended ontology
    export_cmd = [
        sys.executable, "scripts/export_ontology.py",
        "--decisions", f"{iteration_dir}/decisions.json",
        "--proposals", f"{iteration_dir}/proposals.json",
        "--seed", seed_ontology,
        "--output-owl", f"{output_dir}/ontology_latest.owl",
        "--output-cq", f"{output_dir}/cq_latest.json"
    ]
    if experiment_name:
        export_cmd.extend(["--experiment-name", experiment_name])
        
    if not run_command(export_cmd, "Export extended ontology and competency questions"):
        return False

    # Step 4: Run evaluation on the new ontology
    before_path = Path("data/evaluation/competency_questions.json")
    after_path = Path(f"{output_dir}/cq_latest.json")
    eval_output = Path(f"{iteration_dir}/evaluation_report.json")

    if is_json_list(before_path) or is_json_list(after_path):
        print("WARNING: Evaluation input files are lists, skipping metric comparison.")
        write_skip_evaluation_report(before_path, after_path, eval_output)
    else:
        if not run_command([
            sys.executable, "scripts/evaluate_iteration.py",
            "--before", str(before_path),
            "--after", str(after_path),
            "--output", str(eval_output)
        ], "Evaluate improvement in competency question coverage"):
            return False

    # Step 5: Check what files were created
    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE - CHECKING OUTPUT FILES")
    print('='*60)

    files_to_check = [
        f"{output_dir}/ontology_latest.owl",
        f"{output_dir}/cq_latest.json",
        f"{output_dir}/convergence_report.json",
        f"{iteration_dir}/proposals.json",
        f"{iteration_dir}/decisions.json",
        f"{iteration_dir}/evaluation_report.json"
    ]

    for file_path in files_to_check:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size
            print(f"✓ {file_path} ({size} bytes)")
        else:
            print(f"✗ {file_path} (MISSING)")

    print(f"\n{'='*60}")
    print("PIPELINE EXECUTION COMPLETE")
    print('='*60)

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
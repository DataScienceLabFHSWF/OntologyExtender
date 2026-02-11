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
import subprocess
import sys
from pathlib import Path

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
        "--output-owl", f"{output_dir}/ontology_latest.owl",
        "--output-cq", f"{output_dir}/cq_latest.json"
    ]
    if experiment_name:
        export_cmd.extend(["--experiment-name", experiment_name])
        
    if not run_command(export_cmd, "Export extended ontology and competency questions"):
        return False

    # Step 4: Run evaluation on the new ontology
    if not run_command([
        sys.executable, "scripts/evaluate_iteration.py",
        "--before", "data/evaluation/competency_questions.json",
        "--after", f"{output_dir}/cq_latest.json",
        "--output", f"{iteration_dir}/evaluation_report.json"
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
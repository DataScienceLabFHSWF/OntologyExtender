#!/usr/bin/env python3
"""Run large model baseline strategy experiments."""

import json
import subprocess
import sys
from pathlib import Path

def run_large_model_baselines():
    """Run all baseline strategies with the large model (qwen3-next)."""

    strategies = ["naive", "modular", "iterative", "adaptive"]
    results = {}

    print("🚀 Testing Large Model (qwen3-next) Baseline Strategies")
    print("=" * 60)

    for strategy in strategies:
        print(f"\n🎯 Testing: {strategy.upper()}")
        print("-" * 40)

        try:
            # Create output directory
            output_dir = Path(f"data/exports/large_{strategy}")
            output_dir.mkdir(parents=True, exist_ok=True)

            # Run the baseline script
            cmd = [
                sys.executable,
                "scripts/llm_only_baseline.py",
                "--model", "qwen3-next:latest",
                "--strategy", strategy,
                "--output", str(output_dir / "ontology_latest.owl"),
                "--experiment-name", f"large_{strategy}"
            ]

            print(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=Path("/home/fneubuerger/OntologyExtender"),
                capture_output=True,
                text=True,
                timeout=1200  # 20 minutes total timeout
            )

            if result.returncode == 0:
                print("✅ SUCCESS")
                results[strategy] = {
                    "status": "success",
                    "stdout": result.stdout[-500:],  # Last 500 chars
                    "stderr": result.stderr[-500:] if result.stderr else ""
                }

                # Check if ontology file was created
                ontology_file = output_dir / "ontology_latest.owl"
                if ontology_file.exists():
                    size = ontology_file.stat().st_size
                    print(f"📄 Ontology created: {size} bytes")
                else:
                    print("⚠️  Ontology file not found")

            else:
                print(f"❌ FAILED (exit code: {result.returncode})")
                results[strategy] = {
                    "status": "failed",
                    "exit_code": result.returncode,
                    "stdout": result.stdout[-1000:],
                    "stderr": result.stderr[-1000:] if result.stderr else ""
                }

        except subprocess.TimeoutExpired:
            print("⏰ TIMEOUT (20 minutes)")
            results[strategy] = {"status": "timeout"}
        except Exception as e:
            print(f"💥 ERROR: {e}")
            results[strategy] = {"status": "error", "error": str(e)}

    # Save results
    with open("large_model_baseline_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    print("\n📊 LARGE MODEL BASELINE RESULTS")
    print("=" * 50)
    for strategy in strategies:
        result = results[strategy]
        status = result["status"]
        if status == "success":
            print(f"✅ {strategy:<12} SUCCESS")
        else:
            print(f"❌ {strategy:<12} {status.upper()}")

    print(f"\n📁 Detailed results saved to large_model_baseline_results.json")

    # Success count
    successful = sum(1 for r in results.values() if r["status"] == "success")
    print(f"\n🎯 {successful}/{len(strategies)} strategies completed successfully")

if __name__ == "__main__":
    run_large_model_baselines()
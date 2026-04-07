#!/bin/bash
# Run comparison between Vanilla (Standard) and HCOME (LLM4ACOE/LC3) strategies

MODEL="gemma4:e2b"  # Adjust model as needed
OUTPUT_DIR="results/lc3_comparison"

echo "Starting LC3 Comparison Benchmark..."
echo "Model: $MODEL"
echo "Output Directory: $OUTPUT_DIR"

# 1. Run Vanilla Baseline (Zero-shot)
echo "----------------------------------------------------------------"
echo "Running Vanilla Baseline..."
python scripts/run_ontourl_benchmark.py \
    --model $MODEL \
    --strategies vanilla_zero \
    --output-dir $OUTPUT_DIR/vanilla

# 2. Run HCOME / LC3 Strategy
echo "----------------------------------------------------------------"
echo "Running HCOME (LC3) Strategy..."
python scripts/run_ontourl_benchmark.py \
    --model $MODEL \
    --strategies hcome \
    --output-dir $OUTPUT_DIR/hcome

# 3. Generate Comparison Report
echo "----------------------------------------------------------------"
echo "Generating Comparison Report..."
python scripts/run_model_comparison.py \
    --baseline $OUTPUT_DIR/vanilla \
    --candidate $OUTPUT_DIR/hcome \
    --output $OUTPUT_DIR/report.md

echo "Done! Report saved to $OUTPUT_DIR/report.md"

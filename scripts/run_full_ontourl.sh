#!/usr/bin/env bash
# Full OntoURL benchmark: 3 models × all strategies × all tasks
# Resume-safe: skips already-completed (model, strategy, split) combinations.
# Run from project root:  bash scripts/run_full_ontourl.sh
#
# Estimated total wall-clock: 3-5 days on 2×H200
# Progress is saved after every split (JSONL + summary JSON) to results/ontourl/

set -euo pipefail
cd "$(dirname "$0")/.."

# Activate virtual environment
if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
fi

OUTPUT_DIR="results/ontourl"
OLLAMA_URL="${HITL_OLLAMA_URL:-http://localhost:18135}"
LOG_DIR="logs/ontourl"
mkdir -p "$LOG_DIR"

MODELS=(
    "gemma4:e2b"
    "gemma4:e4b"
    "nemotron-3-nano"
    "gemma4:31b"
)

# All strategies — runner automatically skips inapplicable ones per task
STRATEGIES="vanilla_zero cot engineer self_verify multi_turn debate"

# Order tasks: Understanding (MCQ, fast) → Reasoning (MCQ/bool, fast) → Learning (generative, slower)
TASKS="U1 U2 U3 U4 U5 R1 R2 R3 R4 R5 L1 L2 L3 L4 L5"

echo "=========================================="
echo "OntoURL Full Benchmark"
echo "=========================================="
echo "Models:     ${MODELS[*]}"
echo "Strategies: $STRATEGIES"
echo "Tasks:      $TASKS"
echo "Output:     $OUTPUT_DIR"
echo "Ollama:     $OLLAMA_URL"
echo "Started:    $(date)"
echo "=========================================="

for MODEL in "${MODELS[@]}"; do
    MODEL_SAFE="${MODEL//\//_}"
    MODEL_SAFE="${MODEL_SAFE//:/_}"
    LOGFILE="$LOG_DIR/ontourl_${MODEL_SAFE}_$(date +%Y%m%d_%H%M%S).log"

    echo ""
    echo "──────────────────────────────────────────"
    echo "Model: $MODEL"
    echo "Log:   $LOGFILE"
    echo "──────────────────────────────────────────"

    python scripts/run_ontourl_benchmark.py \
        --model "$MODEL" \
        --tasks $TASKS \
        --strategies $STRATEGIES \
        --output-dir "$OUTPUT_DIR" \
        --ollama-url "$OLLAMA_URL" \
        --temperature 0.0 \
        --max-tokens 512 \
        --timeout 600 \
        --resume \
        2>&1 | tee "$LOGFILE"

    echo ""
    echo "✓ $MODEL completed at $(date)"
done

echo ""
echo "=========================================="
echo "All models complete at $(date)!"
echo "Results in: $OUTPUT_DIR"
echo "=========================================="

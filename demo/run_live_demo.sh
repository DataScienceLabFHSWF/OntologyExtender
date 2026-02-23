#!/bin/bash
# run_live_demo.sh — Live presentation demo
#
# Shows both CogAgent (our system) and HCOME (LC3 baseline)
# side-by-side on the same ontology task.
#
# Usage:
#   ./demo/run_live_demo.sh                     # default: Pizza
#   ./demo/run_live_demo.sh "Alzheimer Disease"  # custom topic
#   ./demo/run_live_demo.sh "Pizza" cogagent     # our system only
#   ./demo/run_live_demo.sh "Pizza" hcome        # LC3 only

TOPIC="${1:-Pizza}"
MODE="${2:-both}"
MODEL="${MODEL:-llama3.2:3b}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:18135}"

echo "Starting CogAgent Discussion Demo..."
echo "  Topic: $TOPIC"
echo "  Mode:  $MODE"
echo "  Model: $MODEL"
echo ""

.venv/bin/python demo/simulate_discussion.py \
    --mode "$MODE" \
    --topic "$TOPIC" \
    --model "$MODEL" \
    --ollama-url "$OLLAMA_URL"

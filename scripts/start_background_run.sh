#!/bin/bash
# Launch background experiments overnight with proper isolation

set -e

export ONTOLOGY_EXPERIMENT_NAME=""
export PYTHONUNBUFFERED=1

# Create log directory
mkdir -p logs/background_runs

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/background_runs/background_${TIMESTAMP}.log"
PID_FILE="logs/background_runs/background_${TIMESTAMP}.pid"

echo "Starting background experiment suite..."
echo "Timestamp: $TIMESTAMP"
echo "Log file: $LOG_FILE"
echo "PID file: $PID_FILE"
echo ""

# Activate virtualenv
source .venv/bin/activate

# Run background experiments with nohup
nohup python scripts/run_background_experiments.py \
  --suite small_model_experiments.json \
  --suite ablation_suite.json \
  --datasets wine,plan \
  --timeout 43200 \
  > "$LOG_FILE" 2>&1 &

BG_PID=$!
echo $BG_PID > "$PID_FILE"

echo "✓ Background run started with PID $BG_PID"
echo "Monitor with: tail -f $LOG_FILE"
echo "Stop with: kill $BG_PID"
echo ""
echo "Expected completion time: ~12 hours"

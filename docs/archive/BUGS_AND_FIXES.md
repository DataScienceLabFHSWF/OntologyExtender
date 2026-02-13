# Known Bugs & Fixes Log

This document tracks bugs discovered during experiment runs and the
fixes applied. It serves as context for developers working on the
experiment pipeline.

---

## Bug 1: Experiment Data Overwritten Between Runs

**Discovered**: 2026-02-11, during first full experiment run (6 strategies × llama3.2:3b)

**Symptom**: All 6 experiments completed the feedback loop (wandb showed
7-10 classes added per run), but ALL failed at the export step with
`FileNotFoundError: data/iterations/{experiment_name}/proposals.json`.

**Root Cause**: The `ExperimentRunner.clean_workspace()` method called
`shutil.rmtree(data/iterations/)` between experiments, which deleted
**all** iteration subdirectories — including the experiment-specific ones
that the previous experiments wrote to.

The data flow was:
1. Experiment "baseline_consensus" → orchestrator writes to `data/iterations/baseline_consensus/`
2. Experiment "dialectical_focused" starts → `clean_workspace()` deletes `data/iterations/` (including baseline's data)
3. Orchestrator writes to `data/iterations/dialectical_focused/`
4. Export step looks for `data/iterations/dialectical_focused/proposals.json` → but `create_proposals_from_iteration.py` looked at wrong dir

**Fix Applied**:
- Made `clean_workspace()` only clear `data/iterations/v1/` (the working directory) instead of the entire `data/iterations/` tree
- Made `_save_report()` in `loop_orchestrator.py` write convergence report to experiment-specific subdirectory
- Ensured all scripts pass `--experiment-name` through the full call chain

**Files Changed**:
- `scripts/run_experiments.py` — added `archive_experiment_data()` method
- `src/ontology_hitl/core/loop_orchestrator.py` — experiment-aware `_save_report()`
- `scripts/run_full_pipeline.py` — experiment-specific output directories
- `scripts/create_proposals_from_iteration.py` — accepts `--experiment-name`

---

## Bug 2: Missing HITL_OLLAMA_MODEL in .env

**Discovered**: 2026-02-11

**Symptom**: The config default `ollama_model: str = "llama3.2:3b"` was
used instead of the .env's `OLLAMA_LLM_MODEL=qwen3:next` because the
.env key doesn't have the `HITL_` prefix.

**Root Cause**: The `Settings` class uses `env_prefix="HITL_"`, so it
looks for `HITL_OLLAMA_MODEL`, not `OLLAMA_LLM_MODEL`. The .env has the
KGB-style key `OLLAMA_LLM_MODEL=qwen3:next` but no `HITL_OLLAMA_MODEL`.

**Impact**: All experiments ran with llama3.2:3b (the hardcoded default)
regardless of .env settings. This was actually **correct** for the first
experiment run (which was testing the small model), but would be wrong
for large-model experiments.

**Fix**: The model comparison runner overrides via subprocess environment,
so this is handled correctly for experiments. But the .env should also
be updated for standalone runs.

---

## Bug 3: Terminal Buffer Pollution

**Discovered**: 2026-02-11

**Symptom**: Running new commands in the terminal showed output from
previous `experiment_log.txt` instead of the new command's output.

**Root Cause**: The nohup experiment runner was writing to
`experiment_log.txt` while subsequent terminal commands were running in
the same shell session that had the old output buffered.

**Mitigation**: Use background terminals (`isBackground=true`) for
long-running processes and fresh terminals for inspection commands.

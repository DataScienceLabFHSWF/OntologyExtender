# Changelog

All notable changes, experiments and fixes.

## 2026-06-16 — Logical Reasoner agent + OEO reproduction benchmark

Summary
- Added a shared OWL **consistency-checking core** (`reasoning/consistency.py`)
  built on `owlrl` (OWL-RL/RDFS deductive closure) with optional `owlready2`/
  HermiT DL reasoning when Java is present. Detects unsatisfiable classes,
  disjointness violations, subclass cycles and domain/range conflicts; runs on
  a copy of the graph and never mutates the input.
- Added a fourth debate agent, the **Reasoner** ("Logician",
  `agents/reasoner.py`, `AgentRole.REASONER`). Its verdict is *deterministic*
  and binding — since consensus requires every reviewer to approve, a logically
  inconsistent proposal can no longer be accepted. Wired into `AgentTeam`
  (gated by `HITL_REASONER_ENABLED`, default on) and feeds remediation notes
  back into the engineer's revision loop.
- Added the **OEO reproduction benchmark** (`benchmarking/oeo_benchmark.py`,
  `oeo_cq_loader.py`): parses OEO `.omn` Manchester-syntax competency-question
  entailment tests, diffs two ontology versions, and scores how well the
  pipeline recovers the human-authored delta (precision/recall/F1). CQ
  entailment is evaluated with a DL reasoner when `owlready2` is available, and
  explicitly skipped (not faked) otherwise.
- New CLI `scripts/run_oeo_benchmark.py` with `delta`/`score`/`cqs`
  subcommands.

Key files changed
- `src/ontology_hitl/reasoning/{__init__,consistency}.py` — new reasoning core
- `src/ontology_hitl/agents/reasoner.py` — new Reasoner agent
- `src/ontology_hitl/agents/{base,team,__init__}.py` — `REASONER` role + wiring
- `src/ontology_hitl/core/config.py` — `reasoner_enabled`,
  `reasoner_llm_explanations`
- `src/ontology_hitl/benchmarking/{oeo_benchmark,oeo_cq_loader,__init__}.py`
- `scripts/run_oeo_benchmark.py` — new benchmark CLI
- `tests/{reasoning,agents,benchmarking}/` — 33 new tests, all passing

Notes / follow-ups
- Existing ablation configs (`experiments/*.json`) do not vary the agent set;
  they assume the default team. With the Reasoner enabled by default, prior
  ablation numbers reflect a *3-agent* team. To get clean before/after
  comparisons, re-run with `HITL_REASONER_ENABLED=false` (pre-Reasoner
  baseline) and `=true` (new behaviour), or add a `reasoner_enabled` field to
  the experiment JSON.

## 2026-06-16 — Gemma 4 experiments + experiment-schema fields

Summary
- Added `experiments/gemma4_experiments.json`: 10 configs across Gemma 4
  size tiers (`gemma4:e2b`, `gemma4:e4b`, `gemma4:31b`) mirroring the
  baseline/dialectical/socratic/mixed strategy set. They target the shared
  `ollama-kgbuilder` container (`http://localhost:18134`), which is where the
  gemma4/nemotron models are pre-pulled.
- Extended the experiment schema (`ExperimentConfig` in
  `scripts/run_experiments.py` and `ModelExperimentConfig` in
  `scripts/run_model_comparison.py`) with two optional fields:
  - `ollama_url` — per-experiment Ollama endpoint override
    (sets `HITL_OLLAMA_URL`); lets a config pick a specific container/model host.
  - `reasoner_enabled` — per-experiment Reasoner toggle
    (sets `HITL_REASONER_ENABLED`); makes the Reasoner on/off ablation a
    first-class config option instead of a manual env var.
- Documented the gemma4 container and the override in `.env.example`,
  `README.md` (Models + Experiments) and below.

Key files changed
- `experiments/gemma4_experiments.json` — new
- `scripts/run_experiments.py` — `ollama_url`, `reasoner_enabled` wiring
- `scripts/run_model_comparison.py` — same fields in both env blocks
- `.env.example`, `README.md` — gemma4 + override docs

Container map (observed on this host)
- `ollama-ontology` :18135 — qwen3:8b, qwen3-embedding (repo default)
- `ollama-kgbuilder` :18134 — gemma4:31b/e4b/e2b, nemotron-3-nano:30b/4b,
  qwen3:8b, qwen3-embedding

Security note
- `scripts/run_experiments.py` contains a hardcoded W&B API key
  (`HITL_WANDB_API_KEY = "wandb_v1_..."`). This is a committed secret that
  should be rotated and moved to an environment variable.

## 2026-02-16 — SAR reproduction, HITL metrics, tests, experiments

Summary
- Reproduced LLM4ACOE's SAR ingestion and indexing locally into a dedicated
  Qdrant collection `sar_documents` (chunking: 750 tokens, overlap: 0).
- Fixed Qdrant upsert point-ID bug (no more zero IDs) and added `--use-uuids`
  option to `scripts/index_sar_to_qdrant.py`.
- Implemented persistent HITL escalation counting:
  - Added `questions_for_review` to `FeedbackMetrics` and `ConvergenceReport`.
  - Logged `questions_for_review` to Weights & Biases per iteration.
- Fixed recursion/cycle bug in subtree-depth validation and added unit test.
- Ran SAR experiments (smoke + 3-iteration seeded, seedless, SAR-only).
- Prepared & started the full model-comparison pipeline for a SAR head‑to‑head.

Key files changed
- `scripts/index_sar_to_qdrant.py` — ID fix, `--use-uuids` option
- `src/ontology_hitl/methodology/validation_rules.py` — cycle-safe subtree depth
- `src/ontology_hitl/core/feedback_protocol.py` — `questions_for_review` metric
- `src/ontology_hitl/core/loop_orchestrator.py` — propagate & log escalation count
- `tests/methodology/test_validation_rules.py` — new cycle test
- Unit tests updated and passing locally (193 tests)

How to reproduce (short)

1) Index SAR documents to Qdrant (integers or UUIDs):

   ```bash
   python scripts/index_sar_to_qdrant.py --collection sar_documents
   python scripts/index_sar_to_qdrant.py --collection sar_documents --use-uuids
   ```

2) Quick smoke (seeded / seedless):

   ```bash
   HITL_QDRANT_COLLECTION=sar_documents HITL_SEED_ONTOLOGY_PATH=Experiments/SAR/safers_ontology_V3.0.owl \
     python scripts/run_feedback_loop.py --mode standalone --max-iterations 3 --auto-review --experiment-name sar_seeded_3iter

   HITL_QDRANT_COLLECTION=sar_documents HITL_SEED_ONTOLOGY_PATH= \
     python scripts/run_feedback_loop.py --mode standalone --max-iterations 3 --auto-review --experiment-name sar_noseed_3iter
   ```

3) Full head-to-head model comparison on SAR (seeded / seedless):

   ```bash
   # Seeded
   HITL_QDRANT_COLLECTION=sar_documents HITL_QDRANT_SOURCE_FILTER=SAR \
     HITL_SEED_ONTOLOGY_PATH=Experiments/SAR/safers_ontology_V3.0.owl \
     python scripts/run_model_comparison.py --run-all --output results/full_comparison_sar_seeded.json \
       --report results/sar_seeded_report.md

   # Seedless
   HITL_QDRANT_COLLECTION=sar_documents HITL_QDRANT_SOURCE_FILTER=SAR \
     HITL_SEED_ONTOLOGY_PATH= \
     python scripts/run_model_comparison.py --run-all --output results/full_comparison_sar_seedless.json \
       --report results/sar_seedless_report.md
   ```

Notes
- `questions_for_review` appears in `data/exports/{experiment}/convergence_report.json` and is logged to W&B as `questions_for_review`.
- Long-running model comparisons should be run with the virtualenv active or with `.venv/bin/python` for reproducibility.

If you want, I can add these reproduction steps into the `EXPERIMENT_PLAN.md` or `EXPERT_GUIDE.md` as well.
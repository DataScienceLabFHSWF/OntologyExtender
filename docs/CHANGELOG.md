# Changelog

All notable changes, experiments and fixes.

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
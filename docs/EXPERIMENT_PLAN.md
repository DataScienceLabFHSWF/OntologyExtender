# Experiment Plan: Model Comparison & Ontology Quality Benchmarking

This document describes the full experiment design for evaluating how
different LLM sizes and debate strategies affect ontology extension quality.

## Research Questions

### RQ1: Does reasoning capability change ontology quality?
**Hypothesis**: A large reasoning model (Qwen3-Next, 79.7B) produces
deeper hierarchies, richer relations, and fewer hallucinated concepts
than a small non-reasoning model (LLaMA 3.2, 3.2B).

### RQ2: Do debate strategies compensate for model limitations?
**Hypothesis**: Structured debate strategies (dialectical, Socratic)
provide **more improvement** for small models than for large models.
In other words, debate acts as "epistemic scaffolding" that partially
compensates for limited reasoning ability.

### RQ3: Which combination produces the best ontology extension?
**Hypothesis**: Large model + mixed strategy per phase produces the
highest-quality ontology, but the gap over small model + mixed strategy
may be smaller than expected if debate strategies are effective scaffolding.

---

## Experimental Setup

### Models Under Test

| Model | Size | Parameters | Reasoning | Timeout |
|-------|------|-----------|-----------|---------|
| `llama3.2:3b` | 2.0 GB | 3.2B | No | 300s |
| `qwen3-next:latest` | 50.4 GB | 79.7B | Yes (chain-of-thought) | 600s |

Both models are served via the same Ollama instance at `localhost:18135`.
Model switching happens per-experiment via the `HITL_OLLAMA_MODEL`
environment variable — no restart required.

### Debate Strategies Under Test

| Strategy | Phases Applied | What It Tests |
|----------|---------------|---------------|
| **baseline** (consensus) | All phases use default | Control group |
| **dialectical** | Hierarchy + Properties | Structured disagreement for structural decisions |
| **socratic** | Scope + Terms | Question-driven probing for conceptual clarity |
| **mixed** | Per-phase optimal | Combined best strategy per Ont-101 phase |

### Experiment Matrix

| # | Experiment Name | Model | Strategy | Research Question |
|---|----------------|-------|----------|-------------------|
| 1 | `small_baseline` | llama3.2:3b | default | RQ1 baseline |
| 2 | `small_dialectical` | llama3.2:3b | dialectical | RQ2 |
| 3 | `small_socratic` | llama3.2:3b | socratic | RQ2 |
| 4 | `small_mixed` | llama3.2:3b | per-phase optimal | RQ2, RQ3 |
| 5 | `large_baseline` | qwen3-next | default | RQ1 baseline |
| 6 | `large_dialectical` | qwen3-next | dialectical | RQ2 |
| 7 | `large_socratic` | qwen3-next | socratic | RQ2 |
| 8 | `large_mixed` | qwen3-next | per-phase optimal | RQ2, RQ3 |

Total: **8 experiments** (2 models × 4 strategies)

---

## Metrics

### Level 1: Pipeline Metrics (Already Implemented)

These are captured automatically by the feedback loop and logged to W&B.

| Metric | Source | W&B? |
|--------|--------|------|
| `classes_added` | convergence_report.json | Yes |
| `entity_coverage` | convergence_report.json | Yes |
| `cq_coverage` | convergence_report.json | Yes |
| `acceptance_rate` | convergence_report.json | Yes |
| `execution_time` | timer in experiment runner | No |
| `total_entities` | convergence_report.json | Yes |

### Level 2: Structural Metrics (To Be Implemented)

These address the specific evaluation gaps identified in the literature.

| Metric | What It Measures | Literature Source | Target Range |
|--------|-----------------|-------------------|-------------|
| `class_count` / `class_count_delta` | Ontology growth | — | > 5 new classes |
| `property_count` / `property_count_delta` | Relational richness | Zhao et al. (2025) | > 5 new properties |
| `hierarchy_depth_max` | Depth of deepest class | Plu et al. (2025) | >= 3 |
| `hierarchy_depth_mean` | Average depth | Plu et al. (2025) | >= 2 |
| `hierarchy_depth_stdev` | Depth variation | Plu et al. (2025) | > 0 (not all same level) |
| `branching_factor_mean` | Avg children per non-leaf | Plu et al. (2025) | 2-5 |
| `leaf_to_internal_ratio` | Abstraction quality | Plu et al. (2025) | < 0.8 |
| `orphan_class_count` | Structural isolation | — | 0 |
| `property_connectivity` | Relations per class | Zhao et al. (2025) | > 0.5 |
| `classes_with_zero_properties` | Under-specified classes | Zhao et al. (2025) | 0 |
| `domain_range_completeness` | Property specification quality | — | > 0.5 |
| `disjointness_axioms` | Ontological rigor | — | > 0 |

### Level 3: CQ-Based Metrics (Partially Implemented)

| Metric | What It Measures | Status |
|--------|-----------------|--------|
| `cq_entity_coverage` | CQ expected entities → OWL classes | Implemented |
| `cq_relation_coverage` | CQ expected relations → OWL properties | **To implement** |
| `cq_sparql_translateability` | Can CQ become valid SPARQL? | **To implement** |

---

## What Will Likely Change with Larger Models?

Based on the literature and the specific design of our system, here is
what we expect to see when switching from llama3.2:3b to qwen3-next:

### 1. Hierarchy Depth Should Increase

**Why**: Reasoning models can maintain longer chains of logical inference.
When the OntologyEngineer proposes a class, a reasoning model is more
likely to correctly identify where it belongs in a multi-level hierarchy
rather than placing it as a direct child of owl:Thing.

**Metric**: `hierarchy_depth_max`, `branching_factor_mean`

**Expected**: +1-2 levels of hierarchy depth; fewer orphan classes.

### 2. Relation Quality Should Improve

**Why**: The dialectical debate requires agents to argue about whether a
relation is necessary or sufficient. A reasoning model can actually follow
the argument logic, while a small model may just generate plausible-sounding
but structurally wrong responses.

**Metric**: `property_count_delta`, `property_connectivity`, `domain_range_completeness`

**Expected**: More properties per class; more complete domain/range specs.

### 3. Fewer Hallucinated Concepts

**Why**: The DomainExpert must check proposals against documents. A
reasoning model is better at distinguishing "this concept appears in
the documents" from "this concept sounds like it could be in the documents."

**Metric**: `acceptance_rate` (higher when fewer hallucinations) + manual review

**Expected**: Higher acceptance rate; fewer rejected proposals.

### 4. Better CQ Coverage

**Why**: Competency questions require understanding what the ontology
needs to be able to answer. A reasoning model can trace the logical
path from CQ → required classes/properties more accurately.

**Metric**: `cq_coverage`, `cq_relation_coverage`

**Expected**: Higher CQ answerability percentage.

### 5. Debate Strategies May Have Diminishing Returns

**Why**: If a reasoning model can already self-correct (via chain-of-thought),
the external pressure from debate strategies may add less value. The
most interesting finding would be if debate strategies help the small
model **more** than the large model — confirming the "scaffolding" hypothesis.

**Metric**: Compare `small_mixed - small_baseline` vs `large_mixed - large_baseline`

**Expected**: The delta is larger for small models.

### 6. Execution Time Will Increase Significantly

**Why**: The large model (79.7B Q4_K_M) is ~25× the size of the small
model (3.2B Q4_K_M). Each LLM call will take proportionally longer.
Since the pipeline makes many LLM calls (7 phases × 3 agents × multiple
debate rounds), total execution time may increase from ~2 minutes to
~30-60 minutes per experiment.

**Metric**: `execution_time_seconds`

**Expected**: 10-30× slowdown per experiment.

---

## File Structure

```
experiments/
├── small_model_experiments.json    # 4 experiments with llama3.2:3b
├── large_model_experiments.json    # 4 experiments with qwen3-next
scripts/
├── run_model_comparison.py         # Model-aware experiment runner (stubs)
results/                            # Created at runtime
├── small_model_results.json
├── large_model_results.json
├── full_comparison.json
├── comparison_report.md
data/
├── iterations/{experiment_name}/   # Per-experiment phase outputs
├── exports/{experiment_name}/      # Per-experiment ontology + CQs
```

---

## How to Run

### Prerequisites
- Ollama running with both models pulled (already done)
- Qdrant with document collection (already done)
- Virtual environment activated

### Run Small Model Experiments
```bash
cd /home/fneubuerger/OntologyExtender
source .venv/bin/activate
nohup python scripts/run_model_comparison.py \
    --experiments experiments/small_model_experiments.json \
    --output results/small_model_results.json \
    > logs/small_model_experiments.log 2>&1 &
```

### Run Large Model Experiments
```bash
nohup python scripts/run_model_comparison.py \
    --experiments experiments/large_model_experiments.json \
    --output results/large_model_results.json \
    > logs/large_model_experiments.log 2>&1 &
```

### Run All + Generate Comparison Report
```bash
nohup python scripts/run_model_comparison.py \
    --run-all \
    --output results/full_comparison.json \
    --report results/comparison_report.md \
    > logs/full_comparison.log 2>&1 &
```

### Monitor Progress
```bash
# Check if still running
ps aux | grep run_model_comparison | grep -v grep

# Follow log output
tail -f logs/small_model_experiments.log

# Check wandb dashboard
# https://wandb.ai/dsfhswf/ontology-hitl
```

### Reproducing the SAR (LLM4ACOE) head-to-head — quick steps (2026-02-16)
This repository now includes the reproduced SAR dataset and helper scripts used
for a head-to-head comparison with LLM4ACOE. Key points:

- SAR documents are indexed into a dedicated Qdrant collection `sar_documents`.
- Chunking uses `chunk_size=750` with zero overlap to match the original pipeline.
- `questions_for_review` (HITL escalation count) is now recorded per iteration
  and appears in `data/exports/{experiment}/convergence_report.json` and W&B.

Index SAR documents to Qdrant (integers or UUIDs):
```bash
python scripts/index_sar_to_qdrant.py --collection sar_documents
# or use UUIDs for stable ids
python scripts/index_sar_to_qdrant.py --collection sar_documents --use-uuids
```

Quick smoke runs (seeded vs seedless):
```bash
HITL_QDRANT_COLLECTION=sar_documents \
  HITL_SEED_ONTOLOGY_PATH=Experiments/SAR/safers_ontology_V3.0.owl \
  python scripts/run_feedback_loop.py --mode standalone --max-iterations 3 --auto-review --experiment-name sar_seeded_3iter

HITL_QDRANT_COLLECTION=sar_documents \
  HITL_SEED_ONTOLOGY_PATH= \
  python scripts/run_feedback_loop.py --mode standalone --max-iterations 3 --auto-review --experiment-name sar_noseed_3iter
```

Full SAR head-to-head (seeded / seedless) — background example:
```bash
nohup bash -lc 'export HITL_QDRANT_COLLECTION=sar_documents; export HITL_QDRANT_SOURCE_FILTER=SAR; export HITL_SEED_ONTOLOGY_PATH=Experiments/SAR/safers_ontology_V3.0.owl; .venv/bin/python scripts/run_model_comparison.py --run-all --output results/full_comparison_sar_seeded.json --report results/sar_seeded_report.md' > logs/experiments/sar_model_comparison_seeded.log 2>&1 &

nohup bash -lc 'export HITL_QDRANT_COLLECTION=sar_documents; export HITL_QDRANT_SOURCE_FILTER=SAR; export HITL_SEED_ONTOLOGY_PATH=""; .venv/bin/python scripts/run_model_comparison.py --run-all --output results/full_comparison_sar_seedless.json --report results/sar_seedless_report.md' > logs/experiments/sar_model_comparison_seedless.log 2>&1 &
```

Where to find outputs & logs
- Per-iteration: `data/iterations/{experiment}/iteration_summary.json` (contains `questions` array)
- Convergence summary: `data/exports/{experiment}/convergence_report.json` (`escalations` + `questions_for_review`)
- Background run logs: `logs/experiments/*.log`
- Final aggregated results & reports: `results/*.json`, `results/*.md`

Notes
- `questions_for_review` is logged to W&B (`questions_for_review`) and included
  in the convergence report to measure human review burden across experiments.
- The SAR collection is separate from the main `documents` collection so you can
  run domain-constrained experiments without affecting production data.


---

## Analysis Plan

After all 8 experiments complete, the comparison report should answer:

1. **Does model size matter?** Compare `small_baseline` vs `large_baseline` on all metrics.
2. **Does debate strategy matter?** For each model, compare baseline vs dialectical vs socratic vs mixed.
3. **Interaction effect?** Is the strategy improvement larger for small models?
4. **Best overall?** Which experiment produced the highest-quality ontology?
5. **Cost/quality tradeoff?** Plot execution time vs quality score.

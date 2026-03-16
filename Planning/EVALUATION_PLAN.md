# Evaluation Plan — Paper B (Ontology Extension)

**Goal**: Produce quantitative results for the conference paper on LLM-driven ontology extension.  
**Owner**: Ole (framework + modular ontology modeling), Ferdinand (experiment runs)  
**Benchmark queue position**: Step 2 (runs after KGB finishes, ~Mar 26–Apr 2)  
**Resource constraint**: Benchmarks run sequentially — only this suite should be running during its window.

---

## Prerequisites

### 1. Services (Docker Compose)

```bash
docker compose up -d
```

| Service | Port | Check |
|---------|------|-------|
| Ollama | 18135→11434 | `curl http://localhost:18135/api/tags` |
| Fuseki | 3031→3030 | `curl http://localhost:3031/$/ping` |

> **Note**: This repo uses port 18135 for Ollama (not 18134 like KGB) — no conflict if both are up, but during benchmarks only this stack should be active.

### 2. Models

Pull all models that will be compared:

```bash
docker exec -it ollama ollama pull qwen3:8b
docker exec -it ollama ollama pull llama3.2:3b
docker exec -it ollama ollama pull nemotron-3-nano
```

For the large model comparison (if time allows):
```bash
docker exec -it ollama ollama pull qwen3-next   # 79.7B — needs ≥80GB VRAM
```

### 3. Dependencies

```bash
pip install -r requirements.txt
```

Verify pySHACL and rdflib are present:
```bash
python -c "import pyshacl; import rdflib; print('OK')"
```

### 4. Data

- Seed ontology in Fuseki: Upload via `http://localhost:3031/dataset.html`
- Test ontology files: `data/ontologies/` (if present)
- SAR ontology: `data/sar/` (if running SAR head-to-head comparison)

---

## Phase 1: Model Comparison Matrix (Core Evaluation)

**Who**: Ferdinand  
**Time**: ~2–3 days  
**Script**: `scripts/run_model_comparison.py`

This is the primary evaluation — comparing LLM performance on ontology extension tasks.

### Run All Experiments

```bash
python scripts/run_model_comparison.py \
  --run-all \
  --output results/model_comparison/ \
  --report
```

This will:
1. Run each model (qwen3:8b, llama3.2:3b, nemotron-3-nano) across all experiment configs
2. Apply timeouts (30/60/90 min per experiment depending on complexity)
3. Generate comparison report in `results/model_comparison/report.md`

### Run Individual Experiments

If you need to re-run specific experiments:

```bash
python scripts/run_model_comparison.py \
  --experiments experiment_1 experiment_3 \
  --output results/model_comparison_partial/
```

### Expected Output

- `results/model_comparison/summary.json` — metrics per model per task
- `results/model_comparison/report.md` — formatted comparison table
- Per-experiment logs in `logs/`

---

## Phase 2: Extension Strategy Comparison (6 Strategies)

**Who**: Ole  
**Time**: ~1 day  
**Script**: `scripts/run_experiments.py`

6 strategies are already defined in the experiment framework. Run all:

```bash
python scripts/run_experiments.py
```

This uses the `ExperimentRunner` class with `ExperimentConfig` models to orchestrate runs.

### Strategies to compare:
1. Direct prompting (baseline)
2. Few-shot examples
3. Chain-of-thought reasoning
4. Ontology-aware prompting (with context from existing ontology)
5. Iterative refinement
6. Hybrid (best combination)

### Metrics per strategy:
- Structural validity (valid OWL axioms generated)
- Semantic accuracy (alignment with ground truth)
- Completeness (% of expected extensions captured)
- Consistency (no logical contradictions introduced)

---

## Phase 3: OntoURL Benchmark (Full Benchmark Suite)

**Who**: Ferdinand (setup + launch), Ole (analysis)  
**Time**: 3–5 days on 2×H200 (or proportionally longer on smaller hardware)  
**Script**: `scripts/run_full_ontourl.sh`

> **⚠ Warning**: This is the longest-running benchmark. Only start when you have a stable multi-day window. Use `nohup` or `tmux`.

### Execution

```bash
# In a tmux session or with nohup
nohup bash scripts/run_full_ontourl.sh > logs/ontourl_full.log 2>&1 &
```

This runs:
- **3 models** × **6 strategies** × **15 tasks** = 270 experiment runs
- Each run: load ontology → generate extension → validate → score

### Monitoring

```bash
tail -f logs/ontourl_full.log
```

### Output
- Per-run results in `results/ontourl/`
- Aggregate metrics: precision, recall, F1 per model per strategy

---

## Phase 4: Structured Benchmark Tool (5-Step Workflow)

**Who**: Ole  
**Time**: ~4 hours  
**Script**: `scripts/run_benchmark.py`

This is a 5-step benchmark workflow for systematic evaluation:

### Step 1: Initialize benchmark environment
```bash
python scripts/run_benchmark.py init \
  --ontology data/ontologies/seed_ontology.owl
```

### Step 2: Generate test cases from ontology
```bash
python scripts/run_benchmark.py generate-test-cases \
  --ontology data/ontologies/seed_ontology.owl \
  --count 50
```

### Step 3: Run extension experiments
```bash
python scripts/run_benchmark.py run \
  --model qwen3:8b \
  --strategy iterative
```

### Step 4: Evaluate results against ground truth
```bash
python scripts/run_benchmark.py evaluate \
  --results results/benchmark/ \
  --ground-truth data/ground_truth/
```

### Step 5: Generate report
```bash
python scripts/run_benchmark.py report \
  --results results/benchmark/ \
  --output results/benchmark_report.md \
  --formats markdown json
```

---

## Phase 5: SAR Domain Comparison (Optional, Strengthens Paper)

**Who**: Ferdinand  
**Time**: ~4 hours

Head-to-head comparison of our approach vs. SAR's ontology extension on the SAR domain:

```bash
# Requires separate Qdrant collection for SAR embeddings
# 1. Load SAR ontology into Fuseki
# 2. Run our pipeline on SAR domain
# 3. Compare output against SAR's published results
```

---

## Output Checklist (What Goes Into the Paper)

| Result | Script | Paper Section |
|--------|--------|---------------|
| Model comparison table (3+ models) | `run_model_comparison.py` | 4.1 Model Comparison |
| Strategy effectiveness (6 strategies) | `run_experiments.py` | 4.2 Strategy Analysis |
| OntoURL benchmark (270 runs) | `run_full_ontourl.sh` | 4.3 OntoURL Benchmark |
| Structural validity scores | `run_benchmark.py evaluate` | 4.2 Strategy Analysis |
| Semantic accuracy vs ground truth | `run_benchmark.py evaluate` | 4.3 OntoURL Benchmark |
| Per-task breakdown | `run_benchmark.py report` | 4.3 OntoURL Benchmark |
| SAR comparison (if done) | manual analysis | 4.4 Case Study |
| Execution time per model | Log files | 4.1 Model Comparison |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Ollama timeout on large ontologies | Increase timeout in `run_model_comparison.py` (default: 30/60/90 min) |
| Fuseki 404 on dataset | Create dataset first at `http://localhost:3031/$/datasets` |
| `run_full_ontourl.sh` hangs | Check GPU memory, reduce to 1 model at a time if needed |
| pySHACL validation fails | Verify ontology is valid OWL — run `rapper -c ontology.owl` first |
| OOM on qwen3-next (79.7B) | Needs ≥80GB VRAM. Skip if hardware insufficient — the 3 smaller models suffice |
| Port conflict with KGB | KGB uses 18134, this uses 18135 — but during benchmarks only run one stack |

---

*Created: 2026-03-16*

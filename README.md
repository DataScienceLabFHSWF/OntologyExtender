# OntologyExtender

**Human-in-the-Loop Ontology Extension** using multi-agent debate and hybrid agentic GraphRAG.

Multiple LLM agents debate what to add to a seed ontology while a human
reviewer keeps the final say. A full hybrid retrieval pipeline
(vector + graph + ontology) feeds live knowledge-graph context into every
step. Benchmarked against published baselines on OntoURL (58K questions, 15
tasks) and compared with LLM4ACOE.

## How It Works

```
Documents ─┐
           ├─→ Gap Analysis ─→ Multi-Agent Debate ─→ Human Review ─→ Extended Ontology
KG (Neo4j) ┘       ▲                   ▲
Fuseki TBox ───────┘                   │
Qdrant Vectors ────────────────────────┘
```

1. **Gap Analysis** — Live graph + SPARQL comparison finds entities the ontology can't represent
2. **Hybrid Retrieval** — Vector, graph, Cypher and ontology retrieval fused via reciprocal rank fusion
3. **7-Phase Pipeline** — Four agents debate scope, terms, hierarchy, properties, facets, instances
4. **Logical Gate** — A formal Reasoner (OWL-RL/DL) checks every proposal for consistency; an inconsistent extension can never reach consensus
5. **Human Review** — Accept, reject, or revise proposals
6. **Export** — Produce OWL, SHACL constraints, and updated competency questions
7. **Evaluate** — Measure improvement across 6 dimensions. Repeat until convergence.

## Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/DataScienceLabFHSWF/OntologyExtender.git
cd OntologyExtender
cp .env.example .env

# Start everything — Fuseki + Ollama + API + auto model pull
docker compose up -d --build

# API: http://localhost:8003/docs
# Fuseki: http://localhost:3030
```

Container names are prefixed with `ontology-` to avoid conflicts with other stacks.

### Option 2: As Part of KGPlatform

```bash
git clone --recurse-submodules https://github.com/DataScienceLabFHSWF/KGPlatform.git
cd KGPlatform
docker compose up -d  # starts all 3 APIs + shared infra (Ontology API on port 8010)
```

### Option 3: Local Development

```bash
python3 -m venv .venv && source .venv/bin/activate
cp .env.example .env          # configure Ollama URL, model, backends
pip install -e ".[dev]"

# Start Fuseki + Ollama separately, then:
uvicorn ontology_hitl.api.server:app --host 0.0.0.0 --port 8003

# Or run the feedback loop directly:
python scripts/run_feedback_loop.py --mode standalone --max-iterations 4
```

### Individual Steps

```bash
python scripts/run_gap_analysis.py    --checkpoint checkpoint.json --output gap_report.json
python scripts/generate_proposals.py  --gap-report gap_report.json --output proposals.json
python scripts/review_proposals.py    --proposals proposals.json   --output decisions.json
python scripts/export_ontology.py     --decisions decisions.json   --proposals proposals.json \
                                      --output-owl extended.owl    --output-cq updated_cqs.json
python scripts/evaluate_iteration.py  --before before.json --after after.json --output report.json
```

## Architecture

```
src/ontology_hitl/
├── agents/          4 agents + moderator + 5 debate strategies
├── core/            Loop orchestrator, config, data models
├── connectors/      Neo4j · Fuseki · Ollama (LangChain) · Qdrant
├── reasoning/       Shared OWL consistency checker (owlrl / owlready2)
├── retrieval/       Hybrid agentic GraphRAG pipeline (see below)
├── methodology/     Ont-101 pipeline (7 phases), validation
├── discovery/       Gap analysis, entity linking, embedding advisor
├── schema/          OWL export, SHACL, seed protection, versioning
├── evaluation/      CQ evaluator, completeness, quality metrics
├── review/          CLI (Rich/Typer) + web dashboard (Streamlit)
├── sources/         Qdrant document source, CQ generator
├── mapping/         YARRRML/RML mapping rules
└── benchmarking/    OntoURL + OEO reproduction + 6-dimension evaluation
```

### Connectors

| Module | Backend | Notes |
|--------|---------|-------|
| `neo4j.py` | Neo4j (async driver) | k-hop neighbourhood, shortest paths, PPR |
| `fuseki.py` | Apache Fuseki | Async SPARQL (classes, subclasses, synonyms) |
| `ollama.py` | Ollama via LangChain | Chat + embeddings (`ChatOllama` / `OllamaEmbeddings`) |
| `qdrant.py` | Qdrant | Async vector search, returns `DocumentChunk` |

### Hybrid Agentic GraphRAG Pipeline

```
              ┌──── VectorRetriever (Qdrant) ───────┐
QAQuery ──→   ├──── GraphRetriever (Neo4j, 4 modes) ┼──→ RRF Fusion ──→ Reranker ──→ Contexts
              ├──── CypherRetriever (LLM→Cypher)    │
              └──── OntologyRetriever (Fuseki TBox) ─┘
                              ▲
                    AgenticGraphRAG (ReAct, 6 tools)
```

| Module | Purpose |
|--------|---------|
| `vector.py` | Classic RAG: embed question → Qdrant → ranked contexts |
| `graph_retriever.py` | 4 modes: entity-centric, subgraph, path, PPR |
| `cypher.py` | LLM-to-Cypher via LangChain `GraphCypherQAChain` |
| `ontology_context.py` | TBox cache: loads all classes + properties from Fuseki at startup |
| `ontology_retriever.py` | Ontology-guided query expansion (subclasses, synonyms, relations) |
| `path_ranker.py` | Relation-aware path scoring (PathCon / PRA-inspired) |
| `reranker.py` | Cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) |
| `hybrid.py` | Three-way reciprocal rank fusion with adaptive weights |
| `agentic_rag.py` | ReAct agent with 6 tools orchestrating all retrieval |
| `graphrag_gap_analyzer.py` | Live Neo4j + Fuseki gap detection |

### Agents & Debate Strategies

| Agent | Role |
|-------|------|
| **OntologyEngineer** | Propose extensions (Ont-101 methodology) |
| **DomainExpert** | Validate against documents |
| **Critic** | Stress-test structural quality |
| **Reasoner** | Formal logical-consistency gate (deterministic, OWL reasoner — not LLM judgement) |

The **Reasoner** ("Logician") materialises each proposal on top of the seed
ontology, runs an OWL-RL deductive closure (via `owlrl`, with optional
`owlready2`/HermiT DL reasoning when Java is present) and reports
unsatisfiable classes, disjointness violations, subclass cycles and
domain/range conflicts. Its verdict is **deterministic** and binding: because
consensus requires *all* reviewers to approve, a logically inconsistent
extension can never be accepted. Toggle via `HITL_REASONER_ENABLED`.

| Strategy | Phase | Prevents |
|----------|-------|----------|
| Consensus | Reuse (Phase 2) | Authority bias |
| Dialectical | Hierarchy, Properties (4–5) | Premature agreement |
| Socratic | Scope, Terms (1, 3) | Unexamined assumptions |
| Delphi | Facets (Phase 6) | Anchoring + groupthink |
| Abductive | Instances (Phase 7) | Over-engineering |

## Benchmarking

### OntoURL Benchmark (Layer 1–2)

Run 15 standardized ontology tasks with 6 strategy tiers:

```bash
bash scripts/run_full_ontourl.sh
```

Strategies: `vanilla_zero` → `cot` → `engineer` → `self_verify` → `multi_turn` → `debate`

Compare against published baselines (Qwen2.5-3B/72B, LLaMA3.3-70B) and
our reproduced LLM4ACOE HCOME strategies.

### LLM4ACOE Comparison (Layer 3)

Head-to-head with LLM4ACOE (Soularidis et al., 2025):
- **Our turf:** HCOME 3-role method reproduced as OntoURL strategies
- **Their turf:** Our pipeline run on their SAR domain documents

### 6-Dimension Evaluation (Layer 4)

```bash
python scripts/run_benchmark.py evaluate --enable-semantic-matching --enable-owlunit
```

| Metric | Weight | Target |
|--------|--------|--------|
| Semantic Correctness | 0.25 | ≥ 0.92 |
| Hallucination Rate | 0.20 | < 0.05 |
| CQ Coverage | 0.20 | > 0.85 |
| Hierarchy Quality | 0.10 | 0.8–1.0 |
| Domain Compliance | 0.15 | ≥ 0.95 |
| Expert Acceptance | 0.10 | ≥ 0.87 |

Full evaluation rationale: [docs/BENCHMARKING_RATIONALE.md](docs/BENCHMARKING_RATIONALE.md)

### OEO Reproduction Benchmark

Reproduce a published ontology version delta (e.g. Open Energy Ontology) and
score how well the agentic pipeline recovers the human-authored additions:

```bash
# Diff two ontology versions (what classes/properties/axioms were added)
python scripts/run_oeo_benchmark.py delta \
    --old oeo-v1.0.owl --new oeo-v1.1.owl --output delta.json

# Score a generated ontology against the gold version (precision/recall/F1)
python scripts/run_oeo_benchmark.py score \
    --generated generated.owl --gold oeo-v1.1.owl --seed oeo-v1.0.owl \
    --output score.json

# Evaluate OEO competency questions (.omn entailment tests)
python scripts/run_oeo_benchmark.py cqs \
    --cq-dir path/to/oeo/competency_questions --ontology generated.owl \
    --output cqs.json
```

OEO ships its competency questions as OWL Manchester-syntax (`.omn`)
entailment tests (`EquivalentClasses(<expr>, owl:Nothing)`). The loader parses
these and the benchmark evaluates them with a DL reasoner when `owlready2`
(+ Java) is available; without it, CQ evaluation is **explicitly skipped**
rather than reported with a misleading score. The reproduction scorer compares
only the *delta* the pipeline added on top of the seed, not the whole
ontology.

Philosophical traditions as engineering mechanisms:

| Problem | Solution | Mechanism |
|---------|----------|-----------|
| Agents agree too easily | Hegel's dialectics | Forced thesis → antithesis → synthesis |
| Nobody questions assumptions | Socratic method | 5-dimension questioning rotation |
| First reviewer anchors others | Delphi method | Anonymous independent reviews |
| Extensions drift from documents | Gadamer's hermeneutics | Every concept checked against source text |
| Nobody says "stop" | Popper's falsificationism | Critic tries to *break* proposals |
| Complexity only goes up | Peirce's abduction | Simplest extension that explains the gap |

Full derivation: [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)

## Models

| Model | Params | Use | Auto-pulled |
|-------|--------|-----|-------------|
| `qwen3:8b` | 8B | Default API model (reasoning) | Yes (via init container) |
| `llama3.2:3b` | 3.2B | Small non-reasoning baseline for benchmarks | No — pull manually |
| `nemotron-3-nano` | ~8B | Medium model for experiments | No — pull manually |
| `qwen3-next` | 79.7B | Large reasoning model for benchmarks | No — pull manually |
| `gemma4:e2b` / `e4b` / `31b` | 2B / 4B / 31B | Gemma 4 size-tier experiments (on the shared `:18134` container) | Pre-pulled on `ollama-kgbuilder` |
| `qwen3-embedding` | — | Semantic matching fallback | No — pull if needed |

All served locally via Ollama. The standalone container is `ontology-ollama` (port 11437);
inside KGPlatform the instance is `ollama-ontology` (port 18135). The Gemma 4
and Nemotron models live on the shared `ollama-kgbuilder` container
(`http://localhost:18134`) — point at it with `HITL_OLLAMA_URL=http://localhost:18134`.

### Pulling Additional Benchmark Models

```bash
# Standalone
docker exec ontology-ollama ollama pull llama3.2:3b
docker exec ontology-ollama ollama pull nemotron-3-nano
docker exec ontology-ollama ollama pull qwen3-next:latest
docker exec ontology-ollama ollama pull qwen3-embedding

# Inside KGPlatform
docker exec ollama-ontology ollama pull llama3.2:3b
```

Note: the benchmarking pipeline prefers `sentence-transformers` for
semantic matching when available; when unavailable, it falls back to
Ollama `/api/embed` using the configured `semantic_embedding_model`
(default: `qwen3-embedding`). The embedding model is a runtime-only
optional dependency (no Python package required).


## Experiments

All experiments run against the standalone Docker stack. Make sure Ollama has
the required models before starting (see [Models](#models) above).

```bash
# 1. Start standalone stack
docker compose up -d --build

# 2. Pull benchmark models (first time only)
docker exec ontology-ollama ollama pull llama3.2:3b
docker exec ontology-ollama ollama pull nemotron-3-nano
docker exec ontology-ollama ollama pull qwen3-next:latest

# 3. Run comprehensive model comparison (small/medium/large × 4 strategies)
python scripts/run_model_comparison.py \
    --experiments experiments/comprehensive_experiments.json \
    --output results/comprehensive.json \
    --report results/comparison_report.md

# 4. Run debate strategy experiments (parallel)
python scripts/run_experiments.py \
    --experiments experiments/comprehensive_experiments.json \
    --parallel --output results/comprehensive_results.json

# 4b. Gemma 4 size-tier experiments (uses the shared :18134 container)
python scripts/run_experiments.py \
    --experiments experiments/gemma4_experiments.json \
    --parallel --output results/gemma4_results.json

# 5. OntoURL benchmark (15 tasks, all strategies)
python scripts/run_ontourl_benchmark.py --model llama3.2:3b
bash scripts/run_lc3_comparison.sh          # Vanilla vs HCOME comparison

# 6. LLM-only baselines
python scripts/llm_only_baseline.py --model llama3.2:3b --strategy naive
```

### Experiment Configurations

| Config File | Models | Experiments |
|-------------|--------|-------------|
| `experiments/small_model_experiments.json` | llama3.2:3b | 5 (baseline + debate strategies) |
| `experiments/large_model_experiments.json` | qwen3-next | 5 (baseline + debate strategies) |
| `experiments/gemma4_experiments.json` | gemma4:e2b/e4b/31b | 10 (baseline + strategies × 3 sizes) |
| `experiments/llm_only_experiments.json` | all 3 | 12 (4 strategies × 3 models) |
| `experiments/comprehensive_experiments.json` | all 3 | 24 (debate + LLM-only × 3 sizes) |

Each experiment may set `ollama_url` (point at a specific Ollama container,
e.g. the shared gemma4 host on `:18134`) and `reasoner_enabled` (toggle the
logical Reasoner on/off for clean before/after ablations). The gemma4 configs
use `"ollama_url": "http://localhost:18134"`.

Details: [docs/EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md)

## Configuration

Key settings in `.env` (copy from `.env.example`):

```bash
# LLM — default model pulled automatically by docker compose
HITL_OLLAMA_MODEL=qwen3:8b

# Override for benchmarking:
# HITL_OLLAMA_MODEL=llama3.2:3b    # small baseline
# HITL_OLLAMA_MODEL=qwen3-next     # large reasoning model

# Semantic matching fallback (when sentence-transformers unavailable)
HITL_SEMANTIC_EMBEDDING_MODEL=qwen3-embedding

# Backends
HITL_NEO4J_URI=bolt://localhost:7687
HITL_NEO4J_USER=neo4j
HITL_NEO4J_PASSWORD=changeme
HITL_FUSEKI_URL=http://localhost:3030
HITL_FUSEKI_DATASET=kgbuilder
HITL_QDRANT_URL=http://localhost:6333
HITL_QDRANT_COLLECTION=kgbuilder

# Retrieval tuning
HITL_VECTOR_TOP_K=10
HITL_FUSION_WEIGHT_VECTOR=0.4
HITL_FUSION_WEIGHT_GRAPH=0.4
HITL_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
HITL_GRAPH_MAX_HOPS=2
HITL_PPR_TOP_K=20

HITL_CQ_ANSWERABILITY_TARGET=0.80

# Logical Reasoner gate
HITL_REASONER_ENABLED=true              # formal consistency check in every debate
HITL_REASONER_LLM_EXPLANATIONS=true     # LLM phrases remediation advice for issues
```

CI note: the GitHub Actions CI job can optionally pull the configured Ollama
embedding model if you set the repository-variable `HITL_PULL_OLLAMA_EMBED=true`.

### Tracing (optional)

```bash
LANGSMITH_TRACING=true           # LangSmith LLM call traces
LANGSMITH_API_KEY=<key>
WANDB_PROJECT=ontology-hitl       # W&B experiment tracking
```

## Tests

```bash
python -m pytest tests/ -v                      # all tests (310+)
python -m pytest tests/reasoning/ -v              # logical consistency checker
python -m pytest tests/agents/test_reasoner.py -v  # Reasoner agent gate
python -m pytest tests/benchmarking/test_oeo_benchmark.py -v  # OEO reproduction
python -m pytest tests/test_graphrag.py -v        # graph retrieval layer
python -m pytest tests/test_hybrid_graphrag.py -v  # hybrid agentic pipeline
```

## Development

### Setup with Pre-Commit Hooks

For local development, we recommend setting up pre-commit hooks to validate code automatically:

```bash
pip install pre-commit
pre-commit install
```

This runs linting, formatting, type checking, and documentation validation before each commit.

### Build Documentation

```bash
make docs          # Build HTML documentation to docs/_build/html/
make docs-check    # Validate docs build (for CI)
open docs/_build/html/index.html
```

See [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development workflow
- Code quality standards
- Pre-commit hooks setup
- CI/CD pipeline details
- Pull request process

## Documentation

| Document | Content |
|----------|---------|
| [BENCHMARKING_RATIONALE.md](docs/BENCHMARKING_RATIONALE.md) | 4-layer evaluation strategy, LLM4ACOE comparison plan |
| [BENCHMARKING.md](docs/BENCHMARKING.md) | Metrics, datasets, baselines, CLI usage |
| [PHILOSOPHY.md](docs/PHILOSOPHY.md) | Epistemological foundations, debate strategy derivation |
| [RELATED_WORK.md](docs/RELATED_WORK.md) | Literature review, LLM4ACOE analysis |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module reference, pipeline details |
| [WORKFLOW.md](docs/WORKFLOW.md) | Operational workflow, convergence criteria |
| [EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md) | Model comparison design |
| [EXPERT_GUIDE.md](docs/EXPERT_GUIDE.md) | How to review proposals in HITL sessions |
| [CHANGELOG.md](docs/CHANGELOG.md) | Daily changelog and experiment run notes |

## License

MIT
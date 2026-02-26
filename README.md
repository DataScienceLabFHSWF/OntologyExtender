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
3. **7-Phase Pipeline** — Three agents debate scope, terms, hierarchy, properties, facets, instances
4. **Human Review** — Accept, reject, or revise proposals
5. **Export** — Produce OWL, SHACL constraints, and updated competency questions
6. **Evaluate** — Measure improvement across 6 dimensions. Repeat until convergence.

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
cp .env.example .env          # configure Ollama URL, model, backends
pip install -e ".[dev]"
docker compose up -d           # Ollama, Neo4j, Fuseki, Qdrant

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
├── agents/          3 agents + moderator + 5 debate strategies
├── core/            Loop orchestrator, config, data models
├── connectors/      Neo4j · Fuseki · Ollama (LangChain) · Qdrant
├── retrieval/       Hybrid agentic GraphRAG pipeline (see below)
├── methodology/     Ont-101 pipeline (7 phases), validation
├── discovery/       Gap analysis, entity linking, embedding advisor
├── schema/          OWL export, SHACL, seed protection, versioning
├── evaluation/      CQ evaluator, completeness, quality metrics
├── review/          CLI (Rich/Typer) + web dashboard (Streamlit)
├── sources/         Qdrant document source, CQ generator
├── mapping/         YARRRML/RML mapping rules
└── benchmarking/    OntoURL benchmark + 6-dimension evaluation
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

## Design Rationale

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

| Model | Params | Use |
|-------|--------|-----|
| `llama3.2:3b` | 3.2B | Small baseline |
| `nemotron-3-nano` | ~8B | Practical deployment |
| `qwen3-next` | 79.7B | Maximum capability |
| `qwen3-embedding` | embedding model | Ollama embedding model (used as fallback for semantic matching) |

All served locally via Ollama (`localhost:18135`).

Note: the benchmarking pipeline prefers `sentence-transformers` for
TamingHallucinations semantic matching when available; when not, the
framework falls back to Ollama `/api/embed` using the configured
`semantic_embedding_model` (default: `qwen3-embedding`). Pull the
embedding image into the local Ollama instance with:

```bash
# using the repo's Ollama container
docker exec ollama-ontology-extender ollama pull qwen3-embedding
```

Or use `docker compose up -d` to start the Ollama service and then
`docker exec ... ollama pull ...` as above. The embedding model is a
runtime-only optional dependency (no Python package required).


## Experiments

```bash
# Run all experiments
python scripts/run_experiments.py --experiments experiments/comprehensive_experiments.json \
    --parallel --output results/comprehensive_results.json

# Model comparison
python scripts/run_model_comparison.py --run-all --output results/full_comparison.json
```

Details: [docs/EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md)

## Configuration

Key settings in `.env`:

```bash
# LLM
HITL_OLLAMA_URL=http://localhost:18135
HITL_OLLAMA_MODEL=qwen3-next
HITL_OLLAMA_EMBEDDING_MODEL=nomic-embed-text   # embeddings for vector retrieval
HITL_SEMANTIC_EMBEDDING_MODEL=qwen3-embedding  # Ollama embedding model used as fallback

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
python -m pytest tests/ -v                      # all tests (60+)
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
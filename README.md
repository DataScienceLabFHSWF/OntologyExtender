# OntologyExtender (ontology-hitl)

**Human-in-the-Loop Ontology Extension** for Knowledge Graph Construction.

Multiple LLM agents debate what to add to a seed ontology while a human
reviewer keeps the final say.

## How It Works

```
Documents (Qdrant) → Gap Analysis → Multi-Agent Debate → Human Review → Extended Ontology
```

1. **Gap Analysis** — Find entities in documents that the ontology can't represent.
2. **7-Phase Pipeline** — Three agents debate scope, terms, hierarchy, properties, facets, instances.
3. **Human Review** — Accept, reject, or revise what the agents proposed.
4. **Export** — Produce extended OWL, SHACL constraints, and updated competency questions.
5. **Evaluate** — Measure improvement. Repeat until 80%+ coverage.

The seed ontology is the
[AI Planning Ontology](https://github.com/BharathMuppasani/AI-Planning-Ontology)
(`data/seed_ontology/plan-ontology-v1.0.owl` — 18 classes, 26 properties).

## Contributions

### C1. Seed-Based Automatic Ontology Extension (HITL)

Extend a seed ontology from documents while preserving semantic correctness.

| ID | Contribution | Description |
|----|-------------|-------------|
| **C1.1** | Seed Ontology & Competency Questions | Define core classes, relations, constraints, and CQs as a formal starting point |
| **C1.2** | Ontology-Guided Concept Discovery | Automatically propose new classes and relations from document evidence via multi-agent debate |
| **C1.3** | Constraint-Aware Ontology Update | Integrate extensions while enforcing OWL/SHACL constraints and seed protection |
| **C1.4** | Human-in-the-Loop Validation | Review, accept/reject, and refine ontology changes through structured HITL sessions |
| **C1.5** | Ontology Evaluation | Measure CQ coverage, consistency, and change impact across iterations |

## Quick Start

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
cp .env.example .env
pip install -e ".[dev]"
docker compose up -d

# Run
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

## Design Rationale

The system uses **philosophical traditions as engineering mechanisms** to
solve documented failure modes of multi-agent LLM systems:

| Problem | Solution | Mechanism |
|---------|----------|-----------|
| Agents agree too easily | Hegel's dialectics | Forced thesis → antithesis → synthesis |
| Nobody questions assumptions | Socratic method | 5-dimension questioning rotation |
| First reviewer anchors others | Delphi method | Anonymous independent reviews |
| Extensions drift from documents | Gadamer's hermeneutics | Every concept checked against source text |
| Nobody says "stop" | Popper's falsificationism | Critic tries to *break* proposals |
| Complexity only goes up | Peirce's abduction | "Simplest extension that explains the gap" |
| No single metric captures quality | Feyerabend's pluralism | 5 independent quality lenses |

Full derivation: [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)

## Architecture

```
src/ontology_hitl/
├── agents/        3 agents + moderator + 5 debate strategies
├── core/          Loop orchestrator, config, data models
├── methodology/   Ont-101 pipeline (7 phases), validation rules
├── discovery/     Gap analysis, entity linking, embedding advisor, ensemble
├── schema/        OWL export, SHACL generation, seed protection, versioning
├── evaluation/    CQ evaluator, completeness, quality metrics, provenance
├── review/        CLI (Rich/Typer) + web dashboard (Streamlit)
├── sources/       Qdrant document source, CQ generator
├── mapping/       YARRRML/RML mapping rules
└── benchmarking/  Evaluation framework (10 modules)
```

### Agents & Debate Strategies

| Agent | Role | Lens |
|-------|------|------|
| **OntologyEngineer** | Propose extensions | Ont-101 methodology |
| **DomainExpert** | Check against documents | Domain accuracy |
| **Critic** | Stress-test quality | Structural soundness |

| Strategy | Applied In | Prevents |
|----------|-----------|----------|
| Consensus | Phase 2 (Reuse) | Authority bias |
| Dialectical | Phases 4–5 (Hierarchy, Properties) | Premature agreement |
| Socratic | Phases 1, 3 (Scope, Terms) | Unexamined assumptions |
| Delphi | Phase 6 (Facets) | Anchoring + groupthink |
| Abductive | Phase 7 (Instances) | Over-engineering |

### Literature-Inspired Modules

| Module | Source | Function |
|--------|--------|----------|
| A. Seed Protection | Azure DTDL | Extensions via `subClassOf` only — seed is immutable |
| B. Entity Linking | John et al. (2025) | Links to Wikidata, BFO, EMMO, schema.org, SAREF |
| C. Embedding Advisor | Memariani et al. (2025) | Embedding-based parent class recommendations |
| D. Provenance | John et al. (2025) | PROV-O evidence chains |
| E. Ensemble Strategy | Mossakowski (2023+) | Weighted vote: LLM (0.5) + embedding (0.3) + co-occurrence (0.2) |
| F. Feedback Learning | John et al. (2025) | Few-shot learning from HITL accept/reject history |

## Experiments

Compare debate strategies and LLM sizes:

```bash
# Run all experiments (parallel)
python scripts/run_experiments.py --experiments experiments/comprehensive_experiments.json \
    --parallel --output comprehensive_results.json

# Model comparison (small vs large)
python scripts/run_model_comparison.py --run-all --output results/full_comparison.json
```

| Model | Params | Reasoning | Config |
|-------|--------|-----------|--------|
| `llama3.2:3b` | 3.2B | No | `experiments/small_model_experiments.json` |
| `qwen3-next` | 79.7B | Yes | `experiments/large_model_experiments.json` |

Details: [docs/EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md)

## Benchmarking

A 9-dimension evaluation framework integrating five recent papers.
Compares CogAgent against Agent-OM, LLM4ACOE, and NLP-W2V baselines using
core metrics, semantic matching, capability profiling, and unit testing.

```bash
python scripts/run_benchmark.py init --gold-standard data/seed_ontology/plan-ontology-v1.0.owl
python scripts/run_benchmark.py run  --systems cogagent,agent_om,llm4acoe,nlp_w2v
python scripts/run_benchmark.py evaluate --enable-semantic-matching --enable-owlunit
python scripts/run_benchmark.py report --format markdown,latex
```

Details: [docs/BENCHMARKING.md](docs/BENCHMARKING.md)

## Services

| Service | Port | Purpose |
|---------|------|---------|
| `ollama-ontology-extender` | 18135 | Ollama LLM (qwen3-next, GPU) |
| `fuseki-staging` | 3031 | Optional ontology versioning |

## Configuration

Key settings in `.env` (all prefixed `HITL_`):

```bash
HITL_OLLAMA_URL=http://localhost:18135
HITL_OLLAMA_MODEL=qwen3-next
HITL_QDRANT_URL=http://localhost:6333
HITL_QDRANT_COLLECTION=documents
HITL_CQ_ANSWERABILITY_TARGET=0.80
HITL_ENTITY_COVERAGE_TARGET=0.80
```

## Tests

```bash
python -m pytest tests/ -v     # ~144 passing
```

## Documentation

| Document | Audience | Content |
|----------|----------|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Developers | Module reference, pipeline details, testing |
| [docs/BENCHMARKING.md](docs/BENCHMARKING.md) | Researchers | Evaluation framework, metrics, datasets, baselines |
| [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) | Deep dive | Epistemological foundations, debate strategy derivation |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Operators | Step-by-step operational workflow, convergence criteria |
| [docs/EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md) | Researchers | Model comparison design, hypotheses, metrics |
| [docs/RELATED_WORK.md](docs/RELATED_WORK.md) | Researchers | Literature review with references |
| [docs/EXPERT_GUIDE.md](docs/EXPERT_GUIDE.md) | Domain experts | How to review proposals in HITL sessions |
| [docs/INTERFACE_CONTRACT.md](docs/INTERFACE_CONTRACT.md) | Integrators | Schemas for Neo4j, Qdrant, Fuseki, checkpoints |
| [docs/BUGS_AND_FIXES.md](docs/BUGS_AND_FIXES.md) | Developers | Known bugs and applied fixes |

## License

MIT

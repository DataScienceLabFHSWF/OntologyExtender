# OntologyExtender (ontology-hitl)

**Human-in-the-Loop Ontology Extension** for Knowledge Graph Construction.

## What Is This?

This repository implements an iterative, semi-automated workflow for **extending a seed ontology**
(the [AI Planning Ontology](https://github.com/BharathMuppasani/AI-Planning-Ontology))
with domain-specific classes discovered from nuclear decommissioning documents.

The core loop:

1. **Gap Analysis** — compare entities extracted by [KnowledgeGraphBuilder](https://github.com/yourorg/KnowledgeGraphBuilder) against the current ontology and identify uncovered concepts.
2. **Class & Relation Proposals** — use an LLM to generate structured definitions, parent-class assignments, properties, and relations for each gap candidate.
3. **Expert Review (HITL)** — domain experts accept, reject, or revise proposals via an interactive CLI (Rich/Typer).
4. **Ontology Export** — accepted classes are serialized as OWL, with SHACL shapes and updated competency questions (CQs).
5. **Evaluation** — re-run KGB with the extended ontology and measure CQ answerability + entity coverage improvement.
6. **YARRRML Mapping** — generate declarative RDF mapping rules ([YARRRML](https://rml.io/yarrrml/)) for transforming extracted data into the extended ontology.

Each cycle produces a versioned ontology snapshot. The target is **80 %+ CQ answerability** and **80 %+ entity coverage** within 3–4 iterations.

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for Ollama + Fuseki services)
- Seed ontology OWL file in `data/seed_ontology/`

### Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install
cp .env.example .env          # adjust ports/model as needed
pip install -e ".[dev]"

# 3. Start services (Ollama for ontology extension + optional Fuseki)
docker compose up -d
```

### Run an Iteration Cycle

```bash
# Step 1 — Gap analysis (needs KGB extraction checkpoint)
make gap V=v1 CHECKPOINT=../KnowledgeGraphBuilder/output/extraction_checkpoint.json

# Step 2 — Generate class proposals via LLM
make proposals V=v1

# Step 3 — Expert review (interactive CLI)
make review V=v1

# Step 4 — Export extended ontology + CQs
make export V=v1

# Step 5 — Re-run KGB with the extended ontology
cd ../KnowledgeGraphBuilder
python scripts/full_kg_pipeline.py \
  --ontology-path ../OntologyExtender/data/exports/ontology_v1.owl \
  --questions ../OntologyExtender/data/exports/cq_v1.json \
  --max-iterations 1

# Step 6 — Evaluate improvement
make evaluate V=v1
```

### Competency Questions

CQs live in `data/evaluation/competency_questions.json`. Each iteration can add
new CQs; the export step bundles them for KGB.

## Project Structure

```
src/ontology_hitl/
├── core/          Config, data models, protocols, exceptions
├── discovery/     Gap analysis + LLM class/relation generation
├── schema/        Ontology management, SHACL shapes, versioning
├── review/        CLI + optional Streamlit expert review
├── evaluation/    CQ coverage, entity completeness, reporting
└── mapping/       YARRRML rule generation for RDF transformation

scripts/           Step-by-step CLI entry points (gap → proposals → review → export → evaluate)
data/
├── seed_ontology/ Base OWL file
├── evaluation/    Competency questions JSON
├── iterations/    Per-version artifacts (gap reports, proposals, decisions)
└── exports/       Final OWL + CQ outputs consumed by KGB
```

## Interface with KnowledgeGraphBuilder

| Direction | Artifact | Format |
|-----------|----------|--------|
| KGB → here | Extraction checkpoint | JSON (entities, relations, confidence) |
| KGB → here | KG metrics | JSON |
| here → KGB | Extended ontology | OWL (`--ontology-path`) |
| here → KGB | Updated CQs | JSON (`--questions`) |

## Services (Docker Compose)

| Service | Port | Purpose |
|---------|------|---------|
| `ollama-ontology-extender` | `18135` | Dedicated Ollama instance (GPU) for ontology tasks |
| `fuseki-staging` | `3031` | Optional Fuseki for staging graphs (if not sharing KGB's) |

## Success Criteria

| Metric              | Target |
|---------------------|--------|
| CQ Answerability    | 80 %+  |
| Entity Coverage     | 80 %+  |
| Expert Agreement    | 75 %+  |
| Ontology Growth     | 20–30 new classes |

## License

MIT

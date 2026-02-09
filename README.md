# OntologyExtender (ontology-hitl)

**Multi-Agent Ontology Extension** for Knowledge Graph Construction.

## What Is This?

This repository implements an iterative, multi-agent system for **extending a seed ontology**
(the [AI Planning Ontology](https://github.com/BharathMuppasani/AI-Planning-Ontology))
with domain-specific classes discovered from nuclear decommissioning documents.

The system follows the **Ontology 101 methodology** (Noy & McGuinness, 2001) through
a structured collaboration between three AI agents:

- **OntologyEngineer** — proposes ontology artefacts (classes, properties, hierarchy)
- **DomainExpert** — validates proposals against document evidence from Qdrant
- **Critic** — checks structural quality, consistency, and methodology compliance

The pipeline is enriched with **six literature-inspired modules** (A–F) that
address state-of-the-art gaps identified through a systematic literature review:

| Module | Feature | Inspired By |
|--------|---------|-------------|
| **A** | Seed Protection Pattern | Azure DTDL extension-by-inheritance |
| **B** | Entity Linking | John et al. (2025) — HITL Neuro-Symbolic KG |
| **C** | Embedding Advisor (Ollama) | Memariani et al. (2025) — Box Embeddings for Ontologies |
| **D** | Provenance Chain (PROV-O) | John et al. (2025) — evidence traceability |
| **E** | Ensemble Strategy | Mossakowski (2023) — neural-symbolic ensemble |
| **F** | Feedback Learning Loop | John et al. (2025) — SUS 84.17 human feedback |

### Core Workflow

Each iteration runs **seven Ont-101 phases**, each as a structured multi-agent **debate**:

1. **Scope & Competency Questions** — define what the ontology should cover
2. **Reuse Analysis** — identify existing ontologies to reuse
   - **2b. Entity Linking** _(Module B)_ — link terms to Wikidata, BFO, EMMO, schema.org
3. **Term Enumeration** — enumerate important terms from documents
4. **Class Hierarchy** — organise terms into a taxonomic structure
   - **4c. Embedding Advisor** _(Module C)_ — Ollama embeddings recommend parent classes
   - **4e. Ensemble Voting** _(Module E)_ — weighted LLM + embedding + co-occurrence
5. **Property Definition** — define data and object properties
6. **Facet Specification** — specify cardinality, ranges, and constraints
7. **Instance Validation** — verify the ontology against sample instances

Each phase follows the pattern: **propose → review → revise → consensus/escalation**.
Prompts are augmented with HITL feedback history _(Module F)_ and evidence is tracked
throughout via PROV-O provenance records _(Module D)_. The seed ontology is protected
from modification via extension-by-inheritance _(Module A)_.

### Feedback Loop

The system runs as a convergence-driven feedback loop:

```
Documents (Qdrant) → 7-Phase Multi-Agent Pipeline → Extended Ontology
       ↑                    ↑                              ↓
       │            Feedback Learner (F)           Seed Protection (A)
       │            Provenance (D)                 Entity Linking (B)
       │            Embedding Advisor (C)          Ensemble (E)
       │                                                   ↓
       └──── Re-extraction (KGB) ←── OWL + SHACL + CQs ──┘
```

Each cycle produces a versioned ontology snapshot. The target is **80 %+ CQ answerability**
and **80 %+ entity coverage** within 3–4 iterations.

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for Ollama + Fuseki services)
- Seed ontology OWL file in `data/seed_ontology/`
- Document collection indexed in Qdrant

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

### Run the Feedback Loop

```bash
# Standalone mode (uses Qdrant documents directly)
python scripts/run_feedback_loop.py --mode standalone --max-iterations 4

# Coupled mode (with KGB re-extraction after each iteration)
python scripts/run_feedback_loop.py --mode coupled \
    --checkpoint ../KnowledgeGraphBuilder/output/extraction_checkpoint.json \
    --max-iterations 4
```

### Individual Steps (via Make)

```bash
# Gap analysis (needs KGB extraction checkpoint)
make gap V=v1 CHECKPOINT=../KnowledgeGraphBuilder/output/extraction_checkpoint.json

# Generate class proposals via multi-agent debate
make proposals V=v1

# Expert review (interactive CLI for escalated questions only)
make review V=v1

# Export extended ontology + CQs
make export V=v1

# Evaluate improvement
make evaluate V=v1
```

### Competency Questions

CQs live in `data/evaluation/competency_questions.json`. The Ont-101 pipeline
generates CQs in Phase 1 and refines them across iterations.

## Architecture

```
src/ontology_hitl/
├── agents/        Multi-agent system (OntologyEngineer, DomainExpert, Critic, AgentTeam)
├── methodology/   Ont-101 7-phase pipeline, data models, prompts, validation rules
├── core/          Config, feedback protocol, loop orchestrator, data models
├── discovery/     Gap analysis, class/relation generation, entity linker (B),
│                  embedding advisor (C), ensemble strategy (E)
├── schema/        Ontology management, SHACL shapes, versioning, seed protection (A)
├── review/        CLI + optional Streamlit expert review (for HITL escalations)
├── evaluation/    CQ coverage, completeness, reporting, provenance (D),
│                  feedback learner (F)
├── sources/       Qdrant document source, CQ generator
└── mapping/       YARRRML rule generation for RDF transformation

scripts/           CLI entry points (run_feedback_loop, gap, proposals, review, export, evaluate)
data/
├── seed_ontology/ Base OWL file
├── evaluation/    Competency questions JSON
├── iterations/    Per-version artefacts (debate transcripts, proposals, decisions,
│                  entity links, embedding recs, ensemble reports, provenance)
└── exports/       Final OWL + CQ outputs consumed by KGB
```

### Literature-Inspired Modules (A–F)

| Module | File | Description |
|--------|------|-------------|
| **A — Seed Protection** | `schema/seed_manager.py` | Extension-by-inheritance graph management. Never modifies the base ontology; new classes extend seed classes via `rdfs:subClassOf`. |
| **B — Entity Linking** | `discovery/entity_linker.py` | Links proposed classes to Wikidata, BFO, EMMO, schema.org, and SAREF using Ollama embedding similarity + live Wikidata search. |
| **C — Embedding Advisor** | `discovery/embedding_advisor.py` | Uses Ollama `/api/embed` vectors to recommend parent classes by nearest-neighbour search over seed embeddings. Confidence = gap between best and runner-up. |
| **D — Provenance Chain** | `evaluation/provenance.py` | Records evidence citations from agent debates. Exports PROV-O RDF triples and JSON audit trails for transparency. |
| **E — Ensemble Strategy** | `discovery/ensemble_strategy.py` | Weighted voting across three strategies (LLM 0.5, Embedding 0.3, Co-occurrence 0.2). Reports agreement scores and flags split decisions for human review. |
| **F — Feedback Learner** | `evaluation/feedback_learner.py` | Learns from HITL accept/reject decisions. Augments agent prompts with few-shot examples and rejection warnings. Persists memory as JSON across sessions. |

### Multi-Agent Debate Pattern

```
┌─────────────────┐    propose     ┌─────────────┐
│ OntologyEngineer │───────────────▸│             │
│ (proposer)       │◂──────────────│   Debate    │
└─────────────────┘    revise      │             │
                                    │  (per phase)│
┌─────────────────┐    review      │             │
│  DomainExpert    │───────────────▸│             │
│ (doc-grounded)   │               └──────┬──────┘
└─────────────────┘                       │
                                          │ outcome
┌─────────────────┐    review      ┌──────▼──────┐
│     Critic       │───────────────▸│  Consensus  │
│ (quality check)  │               │  Revised    │
└─────────────────┘               │  Escalated  │
                                    └─────────────┘
```

## Interface with KnowledgeGraphBuilder

| Direction | Artifact | Format |
|-----------|----------|--------|
| KGB → here | Extraction checkpoint | JSON (entities, relations, confidence) |
| KGB → here | KG metrics | JSON |
| here → KGB | Extended ontology | OWL (`--ontology-path`) |
| here → KGB | Updated CQs | JSON (`--questions`) |
| Qdrant → here | Document chunks | Vector search (shared collection) |

## Services (Docker Compose)

| Service | Port | Purpose |
|---------|------|---------|
| `ollama-ontology-extender` | `18135` | Dedicated Ollama instance (GPU, qwen3-next 79.7B) |
| `fuseki-staging` | `3031` | Optional Fuseki for staging graphs |

## Success Criteria

| Metric              | Target |
|---------------------|--------|
| CQ Answerability    | 80 %+  |
| Entity Coverage     | 80 %+  |
| Expert Agreement    | 75 %+  |
| Ontology Growth     | 20–30 new classes |

## Configuration (Modules A–F)

All new modules are configurable via environment variables or `.env`:

```bash
# Entity Linking (B)
HITL_ENTITY_LINKING_ENABLED=true
HITL_ENTITY_LINKING_THRESHOLD=0.75

# Embedding Advisor (C)
HITL_EMBEDDING_ADVISOR_ENABLED=true

# Provenance (D)
HITL_PROVENANCE_ENABLED=true

# Ensemble Strategy (E)
HITL_ENSEMBLE_ENABLED=true
HITL_ENSEMBLE_WEIGHT_LLM=0.5
HITL_ENSEMBLE_WEIGHT_EMBEDDING=0.3
HITL_ENSEMBLE_WEIGHT_COOCCURRENCE=0.2

# Feedback Learner (F)
HITL_FEEDBACK_LEARNING_ENABLED=true
HITL_FEEDBACK_MEMORY_PATH=data/feedback_memory.json
HITL_FEEDBACK_MAX_FEW_SHOT=5
```

## Tests

```bash
make test          # ~170 tests (core + literature modules)
make test-verbose  # with full output
```

## License

MIT

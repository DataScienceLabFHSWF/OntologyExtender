# OntologyExtender (ontology-hitl)

**Human-in-the-Loop Ontology Extension** for Knowledge Graph Construction.

## What Is This?

This system **extends a seed ontology** by having multiple LLM agents
debate what to add, while a human reviewer keeps the final say.

The seed ontology is the
[AI Planning Ontology](https://github.com/BharathMuppasani/AI-Planning-Ontology)
(`data/seed_ontology/plan-ontology-v1.0.owl`, 18 classes, 26 properties).
Domain documents live in a Qdrant vector database. The system reads those
documents, identifies gaps in the ontology, proposes extensions, debates
them, and asks you to approve the results.

### Core Workflow

```
Documents (Qdrant) → Gap Analysis → Multi-Agent Debate → Human Review → Extended Ontology
       ↑                                                                          ↓
       └──────────────── Re-extraction (KGB) ←── OWL + SHACL + CQs ──────────────┘
```

Each iteration:

1. **Gap Analysis** — Find entities in documents that the ontology can't represent yet.
2. **7-Phase Pipeline** — Three LLM agents debate scope, terms, hierarchy, properties, etc.
3. **Human Review** — You accept, reject, or revise what the agents proposed.
4. **Export** — Produce extended OWL, SHACL constraints, and updated competency questions.
5. **Evaluate** — Measure improvement. Repeat until 80%+ coverage.

---

## Why the Philosophical Approach?

If you're reading this and wondering *"why does an ontology tool reference
Hegel and Habermas?"* — this section is for you.

### The Problem We're Solving

When you ask an LLM to build an ontology, three things go wrong:

1. **Hallucination amplification.** Agent A proposes a concept. Agent B,
   trained on similar data, thinks it sounds plausible. Agent C sees fake
   consensus and approves. Nobody checked the documents. The concept is
   fabricated — the agents talked each other into it.

2. **Runaway complexity.** Each review round adds more detail. Nobody
   ever says "this is too much." After a few rounds, you have an
   over-engineered ontology with more classes than the domain warrants.

3. **Groupthink.** If all agents share the same training data biases,
   they converge on the same mistakes. Averaging wrong answers doesn't
   make them right.

These are not hypothetical — they are documented failure modes of
multi-agent LLM systems (Du et al. 2023, Ji et al. 2023, Bender &
Koller 2020).

### How Philosophy Gives Us Concrete Solutions

Each philosophical tradition we reference maps directly to a **specific
engineering mechanism** that addresses one of these problems. This is not
decoration — it's the design rationale for why the code works the way it
does.

#### Problem → Philosophical Tradition → Engineering Solution

| Problem | Tradition | What It Actually Does in the Code |
|---------|-----------|-----------------------------------|
| **Agents agree too easily** | Hegel's *dialectics* — knowledge advances through contradiction | Forces a **thesis → antithesis → synthesis** debate structure. The engineer proposes, reviewers must actively *counter* the proposal, and the revision must genuinely resolve the conflict — not just compromise. |
| **Nobody questions assumptions** | Plato's *Socratic method* — examine through targeted questioning | Cycles through 5 dimensions of questioning (What *is* this? How do we *know*? What is it *for*? Is it *well-built*? Does it *fit*?). Each round picks a different angle so the same blind spot isn't examined twice. |
| **First reviewer anchors the rest** | Dalkey & Helmer's *Delphi method* — anonymous expert polling | Agents review independently without seeing each other's opinions. Only the aggregate (approval rate + top issues) is shared. This removes anchoring bias. |
| **Extensions drift from documents** | Gadamer's *hermeneutics* — meaning comes from context | The DomainExpert agent is instructed to check every proposed concept against the actual document text, not against its own training data. If it's not in the documents, it gets rejected. |
| **Nobody says "stop, this is enough"** | Popper's *falsificationism* — a good theory is one you can disprove | The Critic agent explicitly tries to *break* proposals. Can you name something that should NOT be in this class? If you can't, the class is too vague. |
| **Complexity only goes up** | Peirce's *abduction* — infer the simplest explanation | The abductive debate strategy asks: "What is the *simplest* extension that would make this gap expected?" Not "what can we add?" but "what *must* we add?" |
| **No single metric captures quality** | Feyerabend's *methodological pluralism* — no method is universally best | Quality is measured through 5 independent lenses (QA faithfulness, constraint satisfaction, graph structure, semantic alignment, expert review). They sometimes disagree — that's informative, not a bug. |

### How This Connects to Published Research

None of this is purely theoretical. Each mechanism is backed by recent
papers that demonstrate its effectiveness:

| Our Mechanism | Paper | Key Finding |
|---------------|-------|-------------|
| Multi-agent debate | Du et al. (2023) "Improving Factuality through Multiagent Debate" | Debate between LLM agents improved factuality by 15–25% over single-agent baselines |
| Multi-agent debate | Liang et al. (2023) "Encouraging Divergent Thinking through Multi-Agent Debate" | Structured disagreement reduces convergence on wrong answers |
| HITL feedback loop | John et al. (2025) "HITL Workflow for Neuro-Symbolic KG" | Achieved SUS score of 84.17 ("good" usability) for human-reviewed KG construction |
| Embedding-based parent recommendation | Memariani et al. (2025) "Box Embeddings for Extending Ontologies" | Embedding-based methods outperform string matching for ontology alignment |
| Neural-symbolic ensemble | Mossakowski (2023+) DFG project on neural-symbolic integration | Combining LLM, embedding, and structural signals is more robust than any single method |
| Structured agent evaluation | Chan et al. (2023) "ChatEval" | Multi-agent evaluators produce more reliable quality assessments than single evaluators |
| Ontology 101 methodology | Noy & McGuinness (2001) | The 7-phase structure (scope → reuse → terms → hierarchy → properties → facets → instances) is the standard ontology engineering workflow |
| Quality evaluation | Vrandečić (2009), Gangemi et al. (2006) | Multi-dimensional ontology evaluation is necessary because no single metric captures quality |

### The Moderator: Keeping Agents Honest

The Moderator is not an LLM — it's deterministic code.
It does not contribute opinions. It enforces structural rules:

1. **Every proposed concept must cite a document.** No citation → auto-rejection.
2. **Every proposed concept must serve a competency question.** No CQ → scope creep → removed.
3. **Every extension must connect to the seed ontology.** Free-floating concepts = drift.
4. **If all agents agree too easily, inject harder questions.** (Echo chamber detection.)
5. **If revisions only add and never remove, demand simplification.** (Complexity ratchet detection.)

This is the Habermasian idea made concrete: the Moderator doesn't control
*what* gets decided — it ensures the *conditions* under which good
decisions can be made. Think of it as a code review bot that checks
process, not content.

### Summary: Why Not Just Prompt the LLM?

Because a single prompt has no checks and balances. Our approach uses:

- **Three agents** with genuinely different roles (propose / ground-check / stress-test)
- **Five debate strategies** rotated by phase to avoid strategy lock-in
- **A deterministic Moderator** that detects when agents are fooling themselves
- **Six layers of grounding** from document citations to human veto
- **Multi-perspectival quality metrics** that don't collapse into one number

The philosophy isn't there because it sounds impressive. It's there because
each tradition solved a problem of *how to produce reliable knowledge under
uncertainty* — and that's exactly what we're doing when we extend an
ontology with LLMs.

For the full philosophical derivation, see [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md).
For the detailed implementation plan, see [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

---

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for Ollama + Fuseki services)
- Seed ontology OWL file in `data/seed_ontology/` (included: AI Planning Ontology)
- Document collection indexed in Qdrant

### Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install
cp .env.example .env          # adjust ports/model as needed
pip install -e ".[dev]"

# 3. Start services (Ollama for LLM calls + optional Fuseki for ontology storage)
docker compose up -d
```

**Note**: Always activate the virtual environment before running any Python commands:
```bash
source .venv/bin/activate
```

### Run the Feedback Loop

```bash
# Standalone mode (uses Qdrant documents directly, no KGB dependency)
python scripts/run_feedback_loop.py --mode standalone --max-iterations 4

# Coupled mode (with KGB re-extraction after each iteration)
python scripts/run_feedback_loop.py --mode coupled \
    --checkpoint ../KnowledgeGraphBuilder/output/extraction_checkpoint.json \
    --max-iterations 4
```

### Individual Steps

```bash
# Gap analysis (needs extraction checkpoint)
python scripts/run_gap_analysis.py --checkpoint checkpoint.json --output gap_report.json

# Generate proposals
python scripts/generate_proposals.py --gap-report gap_report.json --output proposals.json

# Expert review (interactive CLI)
python scripts/review_proposals.py --proposals proposals.json --output decisions.json

# Export extended ontology
python scripts/export_ontology.py --decisions decisions.json --proposals proposals.json \
    --output-owl extended.owl --output-cq updated_cqs.json

# Evaluate improvement
python scripts/evaluate_iteration.py --before before_metrics.json --after after_metrics.json \
    --output report.json
```

---

## Multi-Agent Debate Strategies

The system selects a debate strategy per pipeline phase. The Moderator
chooses automatically, but you can override via `HITL_DEBATE_STRATEGY`.

| Strategy | When Used | What Agents Do | Prevents |
|----------|-----------|---------------|----------|
| **Consensus** | Reuse analysis (Phase 2) | Equal-voice review — everyone has the same standing | Authority bias |
| **Dialectical** | Hierarchy + Properties (4–5) | Thesis → Antithesis → Synthesis — forced structured disagreement | Premature agreement |
| **Socratic** | Scope + Terms (1, 3) | 5-dimension questioning — rotates through ontological, epistemological, pragmatic, methodological, coherence questions | Unexamined assumptions |
| **Delphi** | Facets (Phase 6) | Anonymous independent reviews → aggregate → iterate | Anchoring + groupthink |
| **Abductive** | Instances (Phase 7) | "What's the *simplest* extension that explains this gap?" | Over-engineering |

### Agent Roles

| Agent | Job | Identity | How It Challenges |
|-------|-----|----------|-------------------|
| **OntologyEngineer** | Propose extensions | Builder — follows Ont-101 methodology | Generates structured proposals |
| **DomainExpert** | Check against documents | Interpreter — checks terms match *actual usage* | "Where does this appear in the documents?" |
| **Critic** | Stress-test quality | Devil's advocate — tries to break proposals | "Can you name something that should NOT be in this class?" |

---

## Architecture

```
src/ontology_hitl/
├── agents/        Multi-agent system
│   ├── base.py                  Agent abstractions, LLM communication
│   ├── ontology_engineer.py     Proposer (7 phase-specific prompts)
│   ├── domain_expert.py         Document-grounded reviewer
│   ├── critic.py                Structural quality reviewer
│   ├── team.py                  Debate orchestration
│   ├── epistemics.py            Philosophical framework
│   ├── debate_strategies.py     5 debate strategies
│   └── moderator.py             Deterministic strategy + drift detection
├── core/          Loop orchestrator, config, data models
├── methodology/   Ont-101 pipeline (7 phases), validation rules
├── discovery/     Gap analysis, class/relation generation, entity linking,
│                  embedding advisor, ensemble strategy
├── schema/        OWL export, SHACL generation, seed protection, versioning
├── evaluation/    CQ evaluator, completeness, quality metrics, provenance, feedback learning
├── review/        CLI (Rich/Typer) + web dashboard (Streamlit)
├── sources/       Qdrant document source, CQ generator
└── mapping/       YARRRML/RML mapping rules

scripts/           CLI entry points
data/
├── seed_ontology/ AI Planning Ontology (plan-ontology-v1.0.owl)
├── evaluation/    Competency questions JSON
├── iterations/    Per-version artefacts
└── exports/       Final OWL + SHACL + CQ outputs
```

### Literature-Inspired Modules

Six modules were added based on state-of-the-art papers:

| Module | Paper | What It Does |
|--------|-------|-------------|
| **A. Seed Protection** (`seed_manager.py`) | Azure DTDL pattern | Locks the seed ontology — extensions only via `subClassOf`, never by modification |
| **B. Entity Linking** (`entity_linker.py`) | John et al. (2025) | Links proposed classes to Wikidata, BFO, EMMO, schema.org, SAREF |
| **C. Embedding Advisor** (`embedding_advisor.py`) | Memariani et al. (2025) | Uses embeddings to recommend parent classes from the seed |
| **D. Provenance** (`provenance.py`) | John et al. (2025) | PROV-O evidence chains — every decision is traceable to a document |
| **E. Ensemble Strategy** (`ensemble_strategy.py`) | Mossakowski (2023+) | Weighted vote: LLM (0.5) + embedding (0.3) + co-occurrence (0.2) |
| **F. Feedback Learning** (`feedback_learner.py`) | John et al. (2025) | Learns from your accept/reject decisions to improve future proposals |

---

## Interface with KnowledgeGraphBuilder

| Direction | Artifact | Format |
|-----------|----------|--------|
| KGB → here | Extraction checkpoint | JSON (entities, relations, confidence) |
| KGB → here | KG metrics | JSON |
| here → KGB | Extended ontology | OWL (`--ontology-path`) |
| here → KGB | Updated CQs | JSON (`--questions`) |
| Qdrant → here | Document chunks | Vector search (shared collection `documents`) |

## Services (Docker Compose)

| Service | Port | Purpose |
|---------|------|---------|
| `ollama-ontology-extender` | `18135` | Ollama LLM (qwen3-next, GPU-accelerated) |
| `fuseki-staging` | `3031` | Optional Fuseki for ontology versioning |

## Configuration

Key settings in `.env`:

```bash
# LLM
HITL_OLLAMA_URL=http://localhost:18135
HITL_OLLAMA_MODEL=qwen3-next

# Qdrant
HITL_QDRANT_URL=http://localhost:6333
HITL_QDRANT_COLLECTION=documents

# Ontology
HITL_FUSEKI_URL=http://localhost:3030
HITL_FUSEKI_DATASET=kgbuilder

# Gap Analysis
HITL_MIN_ENTITY_FREQUENCY=3
HITL_SEMANTIC_SIMILARITY_THRESHOLD=0.65

# Evaluation Targets
HITL_CQ_ANSWERABILITY_TARGET=0.80
HITL_ENTITY_COVERAGE_TARGET=0.80

# Debate Strategy (optional override — Moderator selects per phase by default)
# HITL_DEBATE_STRATEGY=dialectical
```

## Tests

```bash
python -m pytest tests/ -v     # ~144 passing
```

---

## Experiments

The project includes an experiment framework for systematically comparing
debate strategies and LLM models.

### Strategy Experiments

Compare how different debate strategies perform on the same seed ontology
and competency questions:

```bash
# Run all 6 strategy experiments (baseline, dialectical, socratic, delphi, abductive, mixed)
python scripts/run_experiments.py all_experiments.json \
    --results-dir results/strategies

# Run a single experiment
python scripts/run_experiments.py all_experiments.json \
    --experiment baseline_consensus --results-dir results/strategies
```

Each experiment runs a full feedback loop with the specified debate strategy
and logs metrics to Weights & Biases.

### Model Comparison Experiments

Compare small (non-reasoning) vs large (reasoning-capable) LLMs:

| Model | Params | Size | Reasoning | Config |
|-------|--------|------|-----------|--------|
| `llama3.2:3b` | 3.2B | 2.0 GB | No | `experiments/small_model_experiments.json` |
| `qwen3-next:latest` | 79.7B | 50.4 GB | Yes | `experiments/large_model_experiments.json` |

```bash
# Run small-model experiments (4 strategies × llama3.2:3b)
python scripts/run_model_comparison.py --config experiments/small_model_experiments.json

# Run large-model experiments (4 strategies × qwen3-next)
python scripts/run_model_comparison.py --config experiments/large_model_experiments.json

# Run all and generate comparison report
python scripts/run_model_comparison.py --run-all --output results/full_comparison.json

# For long runs, use nohup
nohup bash -c 'source .venv/bin/activate && python scripts/run_model_comparison.py --run-all --output results/full_comparison.json' > logs/model_comparison.log 2>&1 &
```

**Research Questions** (see [docs/EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md)):
1. Does a reasoning-capable LLM produce deeper class hierarchies?
2. Does it achieve higher CQ answerability with fewer iterations?
3. Which debate strategies benefit most from reasoning capabilities?
4. What is the time/quality trade-off between small and large models?

### Experiment Output Structure

```
results/
├── strategies/              # Strategy comparison results
│   └── experiment_results.json
├── full_comparison.json     # Model comparison results
data/
├── iterations/{experiment_name}/   # Per-experiment iteration data
└── exports/{experiment_name}/      # Per-experiment OWL/SHACL/CQ exports
```

### Known Issues

See [docs/BUGS_AND_FIXES.md](docs/BUGS_AND_FIXES.md) for documented bugs
and their fixes (e.g., the experiment data overwrite issue).

---

## Documentation

| Document | Audience | Content |
|----------|----------|---------|
| This README | Everyone | Why + how to run |
| [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) | Deep dive | Full philosophical derivation with sources |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Developers | What's done, what remains, how strategies integrate |
| [docs/IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md) | Developers | Module reference, API examples, testing |
| [docs/EXPERT_GUIDE.md](docs/EXPERT_GUIDE.md) | Domain experts | How to review proposals |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Operators | Step-by-step operational workflow |
| [docs/EXPERIMENT_PLAN.md](docs/EXPERIMENT_PLAN.md) | Researchers | Model comparison design, metrics, expected outcomes |
| [docs/BUGS_AND_FIXES.md](docs/BUGS_AND_FIXES.md) | Developers | Known bugs and applied fixes |

## License

MIT

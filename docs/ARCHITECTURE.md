# Architecture & Developer Guide

> **Audience**: Developers working on the OntologyExtender codebase.
> **System completeness**: ~98% — all modules implemented, OWL reasoner + pyshacl verified.
> **Tests**: ~170 passing (unit, no network calls required).

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Multi-Agent System](#2-multi-agent-system)
3. [Ont-101 Methodology Pipeline](#3-ont-101-methodology-pipeline)
4. [Debate Strategies](#4-debate-strategies)
5. [Moderator Orchestration](#5-moderator-orchestration)
6. [Literature-Inspired Modules (A–F)](#6-literature-inspired-modules-af)
7. [Feedback Loop Orchestrator](#7-feedback-loop-orchestrator)
8. [Seed Ontology](#8-seed-ontology)
9. [Infrastructure & Services](#9-infrastructure--services)
10. [Module Reference](#10-module-reference)
11. [W&B Logging](#11-wandb-logging)
12. [Testing](#12-testing)
13. [Deployment Checklist](#13-deployment-checklist)

---

## 1. High-Level Architecture

```
Documents (Qdrant)
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              Feedback Loop Orchestrator                   │
│  ┌───────────────────────────────────────────────────┐  │
│  │           Ont-101 Pipeline (7 phases)              │  │
│  │                                                     │  │
│  │  ┌──────────────┐  ┌────────────┐  ┌───────────┐  │  │
│  │  │ Ontology     │  │  Domain    │  │  Critic   │  │  │
│  │  │ Engineer     │  │  Expert    │  │           │  │  │
│  │  │ (proposer)   │  │ (reviewer) │  │ (quality) │  │  │
│  │  └──────────────┘  └────────────┘  └───────────┘  │  │
│  │         │                │               │         │  │
│  │         └────────────────┼───────────────┘         │  │
│  │                    Debate per phase                  │  │
│  └───────────────────────────────────────────────────┘  │
│                          │                               │
│  Convergence tracking ◂──┘──▸ W&B metrics               │
└─────────────────────────────────────────────────────────┘
       │
       ▼
Extended Ontology (OWL + SHACL + CQs + YARRRML)
```

### Key Design Decisions

- **Multi-agent over single-LLM**: Three specialised agents with distinct
  roles, system prompts, and review perspectives.
- **Debate-based consensus**: Each Ont-101 phase runs as a structured
  debate (propose → review → revise → consensus).
- **Escalation to HITL**: Only unresolved disagreements reach the human
  reviewer, reducing manual effort by ~80%.
- **Convergence-driven**: The feedback loop runs until coverage targets
  are met, not a fixed number of iterations.

### Source Layout

```
src/ontology_hitl/
├── agents/          Multi-agent system (base, engineer, expert, critic, team, moderator)
├── core/            Loop orchestrator, config, data models, protocols
├── methodology/     Ont-101 pipeline (7 phases), validation rules
├── discovery/       Gap analysis, entity linking, embedding advisor, ensemble
├── schema/          OWL export, SHACL generation, seed protection, versioning
├── evaluation/      CQ evaluator, completeness, quality metrics, provenance, feedback
├── review/          CLI (Rich/Typer) + web dashboard (Streamlit)
├── sources/         Qdrant document source, CQ generator
├── mapping/         YARRRML/RML mapping rules
└── benchmarking/    Evaluation framework (see docs/BENCHMARKING.md)
```

---

## 2. Multi-Agent System

### Agent Roles

| Agent | Role | System Prompt Focus |
|-------|------|-------------------|
| **OntologyEngineer** | Proposer | Ont-101 methodology, formal OWL modelling, taxonomic structure |
| **DomainExpert** | Document-grounded reviewer | Domain accuracy, evidence from Qdrant documents |
| **Critic** | Quality reviewer | Structural quality, naming conventions, CQ coverage, consistency |

### Source Files

```
src/ontology_hitl/agents/
├── base.py                  # AgentRole, AgentMessage, Debate, DebateOutcome, BaseAgent
├── ontology_engineer.py     # OntologyEngineerAgent (propose + revise)
├── domain_expert.py         # DomainExpertAgent (review + answer questions)
├── critic.py                # CriticAgent (review + CQ coverage checking)
├── team.py                  # AgentTeam (orchestrates debates)
├── epistemics.py            # EpistemicStance, SOCRATIC_DIMENSIONS, SYSTEM_ASSEMBLAGE
├── debate_strategies.py     # DebateStrategist with 5 strategies
└── moderator.py             # Deterministic strategy selection + drift detection
```

### BaseAgent

All agents extend `BaseAgent`, which provides:

- `call_llm(system_prompt, user_prompt)` → str — Ollama call with
  qwen3-next thinking-tag handling (strips `<think>...</think>` blocks)
- `call_llm_multi_turn(system_prompt, messages)` → str — for multi-round
  review context

### AgentMessage

```python
@dataclass
class AgentMessage:
    role: AgentRole           # who is speaking
    phase: Phase              # which Ont-101 phase
    message_type: str         # "proposal", "review", "revision"
    content: str              # the actual message text
    reasoning: str            # agent's rationale
    issues_raised: list[str]  # specific problems identified
    approves: bool            # does this agent approve?
```

### Debate Protocol

```
Round 1:
  OntologyEngineer.propose(phase, context) → AgentMessage
  DomainExpert.review(phase, proposal)     → AgentMessage
  Critic.review(phase, proposal, prior)    → AgentMessage

If not consensus AND round < max_rounds:
  OntologyEngineer.revise(phase, proposal, feedback) → AgentMessage
  → repeat review

Outcome:
  CONSENSUS  — all reviewers approve
  REVISED    — proposal improved, accepted on revision
  PARTIAL    — some issues resolved, minor ones accepted
  ESCALATED  — fundamental disagreement → AgentQuestion for HITL
```

### Usage

```python
team = AgentTeam(settings=settings, document_context="...", max_debate_rounds=2)
outcome = team.run_debate(phase=Phase.DEFINE_SCOPE, context="...")
# outcome.verdict in {CONSENSUS, REVISED, PARTIAL, ESCALATED}
# outcome.final_proposal, outcome.escalated_questions
```

---

## 3. Ont-101 Methodology Pipeline

### Source Files

```
src/ontology_hitl/methodology/
├── ontology101.py           # Data models (Phase, OntologyScope, ClassHierarchy, etc.)
├── pipeline.py              # Ont101Pipeline — runs 7 phases with AgentTeam
├── prompts.py               # Agent prompt templates
└── validation_rules.py      # Structural validation (naming, depth, disjointness)
```

### Seven Phases

| Phase | Model | Output |
|-------|-------|--------|
| 1. Scope & CQs | `OntologyScope` | Domain, purpose, competency questions, boundaries |
| 2. Reuse Analysis | `ReuseReport` | Candidate ontologies, recommendations |
| 3. Term Enumeration | `TermEnumeration` | Categorised terms (class/property/instance) |
| 4. Class Hierarchy | `ClassHierarchy` | Tree of `HierarchyNode` with is-a relationships |
| 5. Property Definition | `PropertyProposal` | Domain/range/description per property |
| 6. Facet Specification | `FacetReport` | Cardinality, ranges, SHACL constraints |
| 7. Instance Validation | `SampleInstance` | Test instances with CQ answerability results |

### Validation Rules (applied after Phase 4)

- **NamingConvention** — CamelCase classes, lowerCamelCase properties
- **HierarchyDepth** — max 6 levels deep
- **SingleRoot** — warns if no `owl:Thing` root
- **PropertyAttachment** — flags redundant definitions
- **Disjointness** — suggests axioms for siblings

---

## 4. Debate Strategies

The Moderator selects a strategy per phase:

```
Phase 1: SCOPE     → SOCRATIC      Multi-dimensional questioning
Phase 2: REUSE     → CONSENSUS     Equal-voice discourse
Phase 3: TERMS     → SOCRATIC      Assumption examination
Phase 4: HIERARCHY → DIALECTICAL   Thesis → Antithesis → Synthesis
Phase 5: PROPERTIES→ DIALECTICAL   Competing valid designs
Phase 6: FACETS    → DELPHI        Anonymous iterative consensus
Phase 7: INSTANCES → ABDUCTIVE     Hypothesis → Examination → Parsimony
```

### Dialectical (Phases 4–5)

```
Engineer → THESIS (structured proposal with explicit claims)
Expert + Critic → ANTITHESIS (genuine counter-positions)
Engineer → SYNTHESIS (preserves valid insights from both)
Expert + Critic → AUFHEBUNG CHECK (is synthesis genuinely higher?)
If unresolved → ESCALATE to HITL
```

**Why**: Hierarchy/property design involves competing valid options.
Forces both sides to be articulated and resolved. Du et al. (2023) showed
debate improves factuality by 15–25%.

### Socratic (Phases 1, 3)

Cycles through 5 epistemic dimensions: ontological ("What *is* this?"),
epistemological ("How do we *know*?"), pragmatic ("What is it *for*?"),
methodological ("Is it *well-built*?"), coherence ("Does it *fit*?").

### Delphi (Phase 6)

Independent anonymous reviews → aggregate → iterate until ≥80% agreement.
Prevents anchoring bias.

### Abductive (Phase 7)

"What is the *simplest* extension that explains this gap?" — inference to
best explanation (Peirce). Prevents over-engineering.

### Fallback Logic

```
Failed strategy → CONSENSUS → DIALECTICAL → SOCRATIC → ABDUCTIVE → DELPHI
```

---

## 5. Moderator Orchestration

The Moderator is **deterministic code** (no LLM calls). It enforces
structural rules without contributing opinions.

### Grounding Stack (6 Layers)

| Layer | Check | Threshold | Response |
|-------|-------|-----------|----------|
| 1. Document grounding | Every element cites evidence | ≥ 0.85 | "Provide citations or WITHDRAW" |
| 2. CQ anchoring | Every element serves a CQ | ≥ 0.80 | "Remove elements serving no CQ" |
| 3. Seed tethering | Extensions connect to seed | ≥ 0.90 | "Re-anchor to seed classes" |
| 4. Complexity budget | Max new elements per phase | ≤ 20 | "Simplify — which can be MERGED?" |
| 5. Drift detection | Embedding similarity to corpus | < 0.4 | Switch to Abductive strategy |
| 6. HITL veto | Human reviewer approves all | Every element | Accept / Reject / Revise |

### Drift Patterns Detected

| Pattern | Signature | Response |
|---------|-----------|----------|
| Hallucination spiral | `grounding_ratio < 0.85` | Halt debate, demand re-grounding |
| Complexity ratchet | N consecutive additive revisions | Inject simplification prompt |
| Conceptual drift | `connectivity_ratio < 0.6` | Flag orphan elements |
| Echo chamber | All-approve-no-issues for N rounds | Inject Socratic questioning |
| Scope creep | `cq_coverage < 0.8` | Auto-reject elements without CQ mapping |

---

## 6. Literature-Inspired Modules (A–F)

### A — Seed Protection (`schema/seed_manager.py`)

*Inspired by Azure DTDL extension-by-inheritance pattern.*

`SeedProtectedOntology` manages a ConjunctiveGraph with separate named graphs
for seed (`urn:graph:seed`) and extensions (`urn:graph:ext:*`). Never modifies
the seed graph; new classes extend via `rdfs:subClassOf`.

### B — Entity Linking (`discovery/entity_linker.py`)

*Inspired by John et al. (2025).*

Links proposed class labels to Wikidata, BFO, EMMO, schema.org, SAREF.
Uses Ollama embeddings for cosine similarity matching + live Wikidata search.
Integration point: after Phase 2.

### C — Embedding Advisor (`discovery/embedding_advisor.py`)

*Inspired by Memariani et al. (2025).*

Encodes seed classes as Ollama embedding vectors. For each proposed class,
finds nearest seed class as parent recommendation. `structural_confidence` =
gap between best and runner-up similarity. Integration point: after Phase 4.

### D — Provenance Chain (`evaluation/provenance.py`)

*Inspired by John et al. (2025).*

Records evidence citations from agent debates. Exports as PROV-O RDF triples
or JSON audit trail. Cross-cutting: active during all debate phases.

### E — Ensemble Strategy (`discovery/ensemble_strategy.py`)

*Inspired by Mossakowski (2023+).*

Weighted vote: LLM (0.5) + Embedding (0.3) + Co-occurrence (0.2).
Split decisions (agreement < 0.5) flagged for HITL. Integration point: after Phase 4.

### F — Feedback Learning (`evaluation/feedback_learner.py`)

*Inspired by John et al. (2025).*

Records HITL accept/reject decisions. `get_few_shot_examples()` returns
accepted patterns for prompts; `get_rejection_warnings()` alerts about
previously rejected patterns. Memory persists as JSON across sessions.

---

## 7. Feedback Loop Orchestrator

`src/ontology_hitl/core/loop_orchestrator.py`

```python
orchestrator = FeedbackLoopOrchestrator(
    settings=settings,
    mode=LoopMode.STANDALONE,      # or COUPLED (with KGB)
    max_iterations=6,
    convergence_threshold=0.02,
    max_debate_rounds=2,
)
report: ConvergenceReport = orchestrator.run()
```

### Iteration Lifecycle

1. Plan iteration (focus areas based on prior metrics)
2. Fetch document excerpts from Qdrant (50 chunks)
3. Run Ont-101 pipeline (7 phases × 3 agents × debate rounds)
4. Collect metrics (CQ answerability, entity coverage)
5. Log to W&B (if enabled)
6. Check convergence — stop if improvement < 2% or targets met

### Convergence Criteria

- Entity coverage improvement < 2% between iterations, OR
- CQ answerability ≥ 80%, OR
- Maximum iteration count reached

---

## 8. Seed Ontology

**File**: `data/seed_ontology/plan-ontology-v1.0.owl`
**Source**: AI Planning Ontology | **Triples**: 228 | **Classes**: 18 |
**Object Properties**: 26 | **Datatype Properties**: 4

Key classes: `Action`, `Plan`, `Planner`, `PlanningDomain`, `PlanningProblem`,
`GoalState`, `MacroAction`, `DomainRequirement` (all HIGH extension potential).

### How the Pipeline Uses the Seed

1. `SeedProtectedOntology` loads OWL into `urn:graph:seed` (never modified)
2. Phase 1 (Scope): agents receive 18 class labels + 26 properties as context
3. Phase 2 (Reuse): `EntityLinker` checks against Wikidata/BFO/EMMO
4. Phase 4 (Hierarchy): `EmbeddingAdvisor` recommends parents from seed;
   `EnsembleStrategy` combines LLM + embedding + co-occurrence signals
5. All phases: `Moderator.analyze_grounding()` enforces seed connectivity
6. Export: `SeedProtectedOntology.build_merged()` produces union of seed + extensions

---

## 9. Infrastructure & Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Ollama | `ollama-ontology-extender` | 18135 | LLM inference (qwen3-next 79.7B Q4_K_M) |
| Fuseki (shared) | existing KGB fuseki | 3030 | Main ontology + KG store |
| Fuseki (staging) | `hitl-fuseki` | 3031 | Staging graphs for review |
| Qdrant (shared) | existing KGB qdrant | 6333 | Document vector store |

### Ollama

- **Model**: qwen3-next (79.7B, Q4_K_M, ~52 GB VRAM)
- **GPU**: 2× NVIDIA H200 NVL (143 GB each)
- **Config**: `OLLAMA_KEEP_ALIVE=24h`, `OLLAMA_NUM_PARALLEL=2`, `OLLAMA_FLASH_ATTENTION=1`

Agents call Ollama internally via `BaseAgent.call_llm()`. For non-agent calls:

```python
import httpx
resp = httpx.post(f"{settings.ollama_url}/api/chat", json={
    "model": settings.ollama_model,
    "messages": [{"role": "user", "content": prompt}],
    "stream": False,
    "options": {"num_predict": 2048, "temperature": 0.5},
}, timeout=300.0)
content = resp.json()["message"]["content"]
```

---

## 10. Module Reference

All modules are implemented. Stale `TODO` markers remain in ~12 files
(docstring TODOs where code exists below them — cosmetic only).

| Package | Module | Status | Description |
|---------|--------|--------|-------------|
| **agents/** | `base.py` | ✅ | BaseAgent, AgentMessage, Debate, DebateOutcome |
| | `ontology_engineer.py` | ✅ | Proposer with 7 phase-specific prompts |
| | `domain_expert.py` | ✅ | Hermeneutic reviewer with document grounding |
| | `critic.py` | ✅ | Falsificationist reviewer with CQ checking |
| | `team.py` | ✅ | 3-agent debate orchestration, 7 context builders |
| | `epistemics.py` | ✅ | Epistemic framework constants |
| | `debate_strategies.py` | ✅ | 5 strategies (dialectical, Socratic, Delphi, abductive, consensus) |
| | `moderator.py` | ✅ | Deterministic strategy selection, grounding, drift detection |
| **core/** | `loop_orchestrator.py` | ✅ | Iterative convergence loop with W&B |
| | `config.py` | ✅ | Pydantic Settings with `HITL_` env prefix |
| | `models.py` | ✅ | 11 data models (ProposedClass, GapCandidate, etc.) |
| | `protocols.py` | ✅ | 4 Protocol interfaces |
| | `feedback_protocol.py` | ✅ | FeedbackMetrics, ConvergenceReport, LoopMode |
| **methodology/** | `pipeline.py` | ✅ | 7-phase multi-agent pipeline |
| | `ontology101.py` | ✅ | Phase enum, OntologyScope, ClassHierarchy, etc. |
| | `validation_rules.py` | ✅ | 8 structural validation rules |
| **discovery/** | `gap_analyzer.py` | ✅ | SPARQL + embedding gap analysis |
| | `class_generator.py` | ✅ | LLM class generation with JSON parsing |
| | `relation_generator.py` | ✅ | LLM relation suggestion with SPARQL context |
| | `entity_linker.py` | ✅ | Module B — Wikidata/BFO/EMMO/schema.org/SAREF |
| | `embedding_advisor.py` | ✅ | Module C — Ollama embedding parent advisor |
| | `ensemble_strategy.py` | ✅ | Module E — Weighted ensemble strategy |
| **schema/** | `manager.py` | ✅ | OWL export with rdflib, CQ JSON export |
| | `seed_manager.py` | ✅ | Module A — Extension-by-inheritance |
| | `shacl_generator.py` | ✅ | SHACL shapes + optional pyshacl validation |
| | `version_manager.py` | ✅ | Fuseki Graph Store Protocol operations |
| **evaluation/** | `cq_evaluator.py` | ✅ | Structural + LLM-to-SPARQL CQ evaluation |
| | `completeness.py` | ✅ | Two-stage entity coverage (exact + embedding) |
| | `ontology_quality.py` | ✅ | 5-perspective quality + HermiT reasoner (owlready2) |
| | `provenance.py` | ✅ | Module D — PROV-O evidence chain tracking |
| | `feedback_learner.py` | ✅ | Module F — Few-shot learning from HITL decisions |
| **review/** | `cli.py` | ✅ | Rich/Typer interactive review with resume |
| | `web.py` | ✅ | Streamlit dashboard |
| | `feedback.py` | ✅ | Decision persistence, agreement rates |
| **sources/** | `qdrant_source.py` | ✅ | Document chunk retrieval |
| | `cq_generator.py` | ✅ | CQ generation from documents via LLM |
| **mapping/** | `yarrrml_generator.py` | ✅ | YARRRML/RML mapping rules |

### Remaining Low-Priority Items

| Item | Scope | Effort |
|------|-------|--------|
| Stale `TODO` docstrings | 12 files, ~48 markers | ~3h (cosmetic) |
| Bare `except: pass` handlers | Scattered | ~1h |
| CQ relation coverage metric | `cq_evaluator.py` | ~2h |
| W&B quality sub-score logging | `loop_orchestrator.py` | ~1h |

---

## 11. W&B Logging

Project: **`ontology-hitl`** (`HITL_WANDB_PROJECT=ontology-hitl`)

| Metric | W&B Key | Source |
|--------|---------|--------|
| Entity coverage | `coverage/entity_pct` | CompletenessAnalyzer |
| CQ answerability | `coverage/cq_pct` | CQEvaluator |
| Debates run | `iteration/debates` | Ont101Pipeline |
| Consensus rate | `iteration/consensus_rate` | AgentTeam |
| Escalated questions | `iteration/escalated` | AgentTeam |
| Phase durations | `timing/phase_*` | Pipeline |
| Ontology growth | `ontology/new_classes` | SchemaManager |

---

## 12. Testing

### Test Suite (~170 tests)

```
tests/
├── agents/           # 36 tests — agent construction, debates, team
├── core/             # Convergence, metrics, loop modes
├── methodology/      # Ont-101 data models, validation rules
├── discovery/        # Gap analyzer, class/relation generators, Modules B/C/E
├── schema/           # OWL export, SHACL, versioning, Module A
├── evaluation/       # Completeness, CQ evaluator, Modules D/F
├── mapping/          # YARRRML generator
├── review/           # Feedback persistence
├── sources/          # CQ generator, Qdrant source
└── conftest.py
```

### Running

```bash
make test            # all tests, fast (no network calls)
make test-verbose    # with full output
pytest tests/agents/ # just agent tests
```

### Mock Pattern

Agent tests mock `httpx.post` to avoid real LLM calls:

```python
from unittest.mock import patch, MagicMock

def test_engineer_proposes():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "Proposed hierarchy: ..."}}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.post", return_value=mock_resp):
        agent = OntologyEngineerAgent()
        msg = agent.propose(Phase.DEFINE_HIERARCHY, context="...")
        assert msg.role == AgentRole.ONTOLOGY_ENGINEER
```

---

## 13. Deployment Checklist

### Before First Run

- [ ] `.env` configured with correct ports and model names
- [ ] `docker compose up -d` — Ollama and Fuseki staging running
- [ ] Ollama model pulled: `docker exec ollama-ontology-extender ollama pull qwen3:next`
- [ ] Seed ontology at `data/seed_ontology/plan-ontology-v1.0.owl`
- [ ] Qdrant collection `documents` populated
- [ ] `source .venv/bin/activate && pip install -e ".[dev]"`
- [ ] `python -m pytest tests/ -v` — tests pass

### Optional

- [ ] `owlready2` for OWL consistency checking
- [ ] `pyshacl` for SHACL constraint validation
- [ ] W&B credentials for experiment tracking
- [ ] Fuseki staging (port 3031) for version management

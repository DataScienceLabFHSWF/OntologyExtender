# OntologyExtender — Implementation Guide

> **Audience**: Developers working on the OntologyExtender codebase.
> **Last updated**: 2026-02-09
> **Tests**: 106 passing

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Multi-Agent System](#2-multi-agent-system)
3. [Ont-101 Methodology Pipeline](#3-ont-101-methodology-pipeline)
4. [Feedback Loop Orchestrator](#4-feedback-loop-orchestrator)
5. [Infrastructure & Services](#5-infrastructure--services)
6. [Module Reference](#6-module-reference)
7. [Remaining TODOs](#7-remaining-todos)
8. [W&B Logging Integration](#8-wandb-logging-integration)
9. [Fuseki SPARQL Reference](#9-fuseki-sparql-reference)
10. [Testing Strategy](#10-testing-strategy)

---

## 1. Architecture Overview

The system extends a seed ontology through iterative multi-agent collaboration
following the Ontology 101 methodology (Noy & McGuinness, 2001).

### High-Level Flow

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

- **Multi-agent over single-LLM**: Three specialised agents produce higher-quality
  ontologies than a single LLM with different prompts. Each agent has a distinct
  role, system prompt, and review perspective.
- **Debate-based consensus**: Each Ont-101 phase runs as a structured debate
  (propose → review → revise → consensus), not a one-shot generation.
- **Escalation to HITL**: Only unresolved disagreements reach the human
  reviewer, reducing manual effort by ~80%.
- **Convergence-driven**: The feedback loop runs automatically until coverage
  targets are met, not a fixed number of iterations.

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
├── __init__.py              # Package exports
├── base.py                  # AgentRole, AgentMessage, Debate, DebateOutcome, BaseAgent
├── ontology_engineer.py     # OntologyEngineerAgent (propose + revise)
├── domain_expert.py         # DomainExpertAgent (review + answer questions)
├── critic.py                # CriticAgent (review + CQ coverage checking)
└── team.py                  # AgentTeam (orchestrates debates)
```

### BaseAgent (`base.py`)

All agents extend `BaseAgent`, which provides:

- `call_llm(system_prompt, user_prompt)` → str — single Ollama call with
  qwen3-next thinking-tag handling (strips `<think>...</think>` blocks)
- `call_llm_multi_turn(system_prompt, messages)` → str — for review rounds
  where prior context matters

### AgentMessage

The communication primitive between agents:

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
  OntologyEngineer.revise(phase, proposal, feedback, context) → AgentMessage
  → repeat review

Finalize:
  CONSENSUS  — all reviewers approve
  REVISED    — proposal improved, accepted on revision
  PARTIAL    — some issues resolved, minor ones accepted
  ESCALATED  — fundamental disagreement → AgentQuestion for HITL
```

### AgentTeam (`team.py`)

The `AgentTeam` orchestrates debates and provides context builders for each phase:

```python
team = AgentTeam(settings=settings, document_context="...", max_debate_rounds=2)
outcome = team.run_debate(phase=Phase.DEFINE_SCOPE, context="...")
# outcome.verdict in {CONSENSUS, REVISED, PARTIAL, ESCALATED}
# outcome.final_proposal contains the agreed-upon text
# outcome.escalated_questions → list[AgentQuestion] for HITL
```

Context builder methods: `build_scope_context()`, `build_reuse_context()`,
`build_terms_context()`, `build_hierarchy_context()`, `build_properties_context()`,
`build_facets_context()`, `build_instances_context()`.

---

## 3. Ont-101 Methodology Pipeline

### Source Files

```
src/ontology_hitl/methodology/
├── __init__.py
├── ontology101.py           # Data models (Phase, OntologyScope, ClassHierarchy, etc.)
├── pipeline.py              # Ont101Pipeline — runs 7 phases with AgentTeam
├── prompts.py               # Agent prompt templates (legacy, kept for reference)
└── validation_rules.py      # Structural validation (naming, depth, disjointness)
```

### Ont101Pipeline (`pipeline.py`)

The pipeline runs one iteration of the 7-phase methodology:

```python
pipeline = Ont101Pipeline(settings=settings, iteration=1, output_dir=Path("data/iterations/v1"))
result: Ont101Iteration = pipeline.run_iteration(
    seed_classes=["DomainConstant", "Action", "Goal"],
    seed_properties=["rdfs:label", "rdfs:comment"],
    documents_text="...",               # from Qdrant
    seed_hierarchy_text="...",           # existing class tree
)
# result.scope, result.terms, result.hierarchy, result.properties, ...
# result.questions → escalated items for HITL
```

Each `_run_phase_*()` method:
1. Builds context from previous phases + external data
2. Calls `team.run_debate(phase, context)` to get a `DebateOutcome`
3. Parses the consensus text into typed Ont-101 data models
4. Runs validation rules (for hierarchy phases)
5. Collects escalated questions

### Data Models (`ontology101.py`)

| Model | Phase | Description |
|-------|-------|-------------|
| `OntologyScope` | 1 | Domain, purpose, competency questions, boundaries |
| `ReuseReport` | 2 | Candidate ontologies, recommendations |
| `TermEnumeration` | 3 | Categorised terms (class/property/instance) |
| `ClassHierarchy` | 4 | Tree of `HierarchyNode` with is-a relationships |
| `PropertyProposal` | 5 | Domain/range/description for each property |
| `FacetReport` | 6 | Cardinality, ranges, SHACL constraints |
| `SampleInstance` | 7 | Test instances with CQ answerability results |

### Validation Rules (`validation_rules.py`)

Automatic structural checks applied after Phase 4 (hierarchy):

- **NamingConvention** — CamelCase classes, lowerCamelCase properties
- **HierarchyDepth** — max 6 levels deep
- **SingleRoot** — warns if no `owl:Thing` root
- **PropertyAttachment** — flags redundant property definitions
- **Disjointness** — suggests disjointness axioms for siblings

---

## 4. Feedback Loop Orchestrator

### Source File

`src/ontology_hitl/core/loop_orchestrator.py`

### FeedbackLoopOrchestrator

Top-level entry point that ties everything together:

```python
orchestrator = FeedbackLoopOrchestrator(
    settings=settings,
    mode=LoopMode.STANDALONE,      # or LoopMode.COUPLED
    max_iterations=6,
    convergence_threshold=0.02,
    max_debate_rounds=2,
)
report: ConvergenceReport = orchestrator.run()
```

Each iteration:
1. Plans the iteration (what to focus on based on prior metrics)
2. Fetches document excerpts from Qdrant
3. Runs the Ont-101 pipeline with multi-agent debates
4. Collects metrics (CQ answerability, entity coverage)
5. Logs to W&B (if enabled)
6. Checks convergence — stops if improvement < threshold

### Feedback Protocol (`core/feedback_protocol.py`)

| Model | Purpose |
|-------|---------|
| `FeedbackMetrics` | Per-iteration metrics (coverage, CQ score, accepted count) |
| `IterationPlan` | Focus areas and parameters for the next iteration |
| `ConvergenceReport` | Full run summary with all iterations and final metrics |
| `LoopMode` | `STANDALONE` (Qdrant-only) or `COUPLED` (with KGB) |

---

## 5. Infrastructure & Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **Ollama** | `ollama-ontology-extender` | `18135` | LLM inference (qwen3-next 79.7B Q4_K_M) |
| **Fuseki** (shared) | existing KGB fuseki | `3030` | Main ontology + KG store |
| **Fuseki** (staging) | `hitl-fuseki` | `3031` | Staging graphs for review |
| **Qdrant** (shared) | existing KGB qdrant | `6333` | Document vector store |

### Ollama Configuration

- **Model**: `qwen3-next:latest` (79.7B params, Q4_K_M quantization, ~52 GB VRAM)
- **GPU**: 2× NVIDIA H200 NVL (143 GB VRAM each) — model fits entirely in VRAM
- **Caching**: `OLLAMA_KEEP_ALIVE=24h` — model stays loaded for 24 hours
- **Parallelism**: `OLLAMA_NUM_PARALLEL=2` — 2 concurrent requests
- **Flash Attention**: `OLLAMA_FLASH_ATTENTION=1` — faster inference

### Calling Ollama

The `BaseAgent.call_llm()` method handles all Ollama communication internally.
Agents strip qwen3-next thinking tags (`<think>...</think>`) from responses automatically.

```python
# You don't call Ollama directly — agents do it:
agent = OntologyEngineerAgent(settings=settings)
message = agent.propose(phase=Phase.DEFINE_SCOPE, context="...")
# message.content contains the LLM response (thinking tags stripped)
```

For non-agent LLM calls (e.g., in discovery/ stubs), use this pattern:

```python
import httpx

resp = httpx.post(
    f"{settings.ollama_url}/api/chat",
    json={
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.5},
    },
    timeout=300.0,
)
resp.raise_for_status()
content = resp.json()["message"]["content"]
```

---

## 6. Module Reference

### Completed Modules

| Module | Status | Description |
|--------|--------|-------------|
| `agents/base.py` | ✅ Complete | Agent base abstractions, LLM communication |
| `agents/ontology_engineer.py` | ✅ Complete | Proposer with 7 phase-specific prompts |
| `agents/domain_expert.py` | ✅ Complete | Document-grounded reviewer |
| `agents/critic.py` | ✅ Complete | Structural quality reviewer |
| `agents/team.py` | ✅ Complete | Debate orchestration, context builders |
| `methodology/ontology101.py` | ✅ Complete | All Ont-101 data models |
| `methodology/pipeline.py` | ✅ Complete | 7-phase multi-agent pipeline |
| `methodology/validation_rules.py` | ✅ Complete | 8 hierarchy validation rules |
| `core/config.py` | ✅ Complete | Pydantic Settings with env prefix |
| `core/models.py` | ✅ Complete | 11 data models (ProposedClass, GapCandidate, etc.) |
| `core/protocols.py` | ✅ Complete | 4 Protocol interfaces |
| `core/exceptions.py` | ✅ Complete | 6 typed exceptions |
| `core/feedback_protocol.py` | ✅ Complete | Convergence tracking models |
| `core/loop_orchestrator.py` | ✅ Complete | Feedback loop with multi-agent pipeline |
| `review/feedback.py` | ✅ Complete | Decision persistence, agreement rates |
| `evaluation/reporter.py` | ✅ Complete | Iteration comparison reports |
| `mapping/yarrrml_generator.py` | ✅ Complete | YARRRML rule generation |
| `sources/qdrant_source.py` | ✅ Complete | Document chunk retrieval |
| `sources/cq_generator.py` | ✅ Complete | CQ generation from documents |

### Modules with TODOs

| Module | Status | What remains |
|--------|--------|-------------|
| `discovery/gap_analyzer.py` | Partial | Fuseki SPARQL queries, semantic matching |
| `discovery/class_generator.py` | Stub | LLM call for class generation |
| `discovery/relation_generator.py` | Stub | LLM call for relation suggestion |
| `schema/manager.py` | Partial | OWL export, CQ export |
| `schema/shacl_generator.py` | Partial | Full SHACL with relations |
| `schema/version_manager.py` | Stub | Fuseki graph operations |
| `evaluation/cq_evaluator.py` | Stub | SPARQL-based CQ evaluation |
| `evaluation/completeness.py` | Stub | Entity coverage measurement |
| `review/cli.py` | Partial | Rich interactive review loop |
| `review/web.py` | Stub | Streamlit dashboard (optional) |

---

## 7. Remaining TODOs

These TODOs are in the **discovery**, **schema**, **evaluation**, and **review**
modules. They are independent of the multi-agent system — they handle gap
analysis, export, and evaluation that wrap around the Ont-101 pipeline.

### Priority Order

```
Priority 1:  gap_analyzer (Fuseki SPARQL + semantic matching)
Priority 2:  class_generator + relation_generator (LLM proposals)
Priority 3:  schema manager + SHACL (OWL export)
Priority 4:  version_manager (Fuseki graph operations)
Priority 5:  cq_evaluator + completeness (evaluation)
Priority 6:  review CLI (Rich interactive loop for HITL escalations)
Priority 7:  web.py (Streamlit — optional)
```

### TODO: `gap_analyzer._get_ontology_classes()`

Query Fuseki for all `owl:Class` labels in the current ontology graph.

```python
def _get_ontology_classes(self) -> list[str]:
    query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?label WHERE {
        ?class a owl:Class ; rdfs:label ?label .
    } ORDER BY ?label
    """
    resp = httpx.post(f"{self.fuseki_url}/{self.dataset}/sparql",
                      data={"query": query}, headers={"Accept": "application/sparql-results+json"})
    return [b["label"]["value"] for b in resp.json()["results"]["bindings"]]
```

### TODO: `gap_analyzer._classify_entities()` (semantic matching)

Add Ollama embedding similarity on top of exact string matching. Use `self.similarity_threshold` (0.65).

### TODO: `gap_analyzer._build_gap_candidates()` (embedding grouping)

Group semantically similar uncovered entities (cosine similarity > 0.80) before building gap candidates.

### TODO: `class_generator._generate_single()` and `_suggest_default_properties()`

Call Ollama to generate structured class definitions and properties. Use JSON format mode.

### TODO: `relation_generator.suggest_relations()`

Call Ollama to suggest ObjectProperty relations connecting new and existing classes.

### TODO: `manager.export_owl()` and `export_updated_cqs()`

Serialize accepted classes as OWL/XML with rdflib. Export updated CQ JSON.

### TODO: `shacl_generator.generate_shape()` (full SHACL)

Add proper prefixes, `sh:description`, and relation constraints to SHACL output.

### TODO: `version_manager` (Fuseki graph operations)

Implement `create_version()`, `compute_diff()`, `promote_staging_to_main()`, `create_snapshot()` using Fuseki Graph Store Protocol.

### TODO: `cq_evaluator.evaluate_coverage()`

Convert CQs to SPARQL queries, execute against Fuseki, measure answerability percentage.

### TODO: `completeness.measure_schema_coverage()`

Compare checkpoint entity types against ontology classes via SPARQL.

### TODO: `cli.review()` (Rich interactive loop)

Interactive Rich/Typer review for escalated `AgentQuestion` items from debates.

### TODO: `web.py` (Streamlit dashboard)

Optional web UI for reviewing escalated questions and monitoring convergence.

---

## 8. W&B Logging Integration

The project logs to the **`ontology-hitl`** W&B project.

### Config

```
HITL_WANDB_ENABLED=true
HITL_WANDB_ENTITY=dsfhswf
HITL_WANDB_PROJECT=ontology-hitl
```

### Metrics Logged per Iteration

| Metric | W&B key | Source |
|--------|---------|--------|
| Entity coverage % | `coverage/entity_pct` | CompletenessAnalyzer |
| CQ answerability | `coverage/cq_pct` | CQEvaluator |
| Debates run | `iteration/debates` | Ont101Pipeline |
| Consensus rate | `iteration/consensus_rate` | AgentTeam |
| Escalated questions | `iteration/escalated` | AgentTeam |
| Phase durations | `timing/phase_*` | Pipeline |
| Ontology growth | `ontology/new_classes` | SchemaManager |

---

## 9. Fuseki SPARQL Reference

### Get all classes

```sparql
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?class ?label WHERE {
    ?class a owl:Class .
    OPTIONAL { ?class rdfs:label ?label }
}
```

### Get class hierarchy

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?child ?parent WHERE {
    ?child rdfs:subClassOf ?parent .
}
```

### Count instances per class

```sparql
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?class (COUNT(?inst) AS ?count) WHERE {
    ?inst rdf:type ?class .
} GROUP BY ?class ORDER BY DESC(?count)
```

### Graph Store Protocol — upload Turtle

```bash
curl -X PUT \
  'http://localhost:3030/kgbuilder/data?graph=urn:ontology:staging-v1' \
  -H 'Content-Type: text/turtle' \
  --data-binary @shapes.ttl
```

---

## 10. Testing Strategy

### Current Test Suite (106 tests)

```
tests/
├── agents/
│   └── test_agents.py          # 36 tests — agent construction, debates, team
├── core/
│   └── test_feedback_protocol.py  # Convergence, metrics, loop modes
├── methodology/
│   ├── test_ontology101.py     # Ont-101 data models, phase enums
│   └── test_validation_rules.py   # Hierarchy validation rules
├── discovery/
│   ├── test_class_generator.py
│   ├── test_gap_analyzer.py
│   └── test_relation_generator.py
├── schema/
│   ├── test_manager.py
│   ├── test_shacl_generator.py
│   └── test_version_manager.py
├── evaluation/
│   ├── test_completeness.py
│   └── test_cq_evaluator.py
├── mapping/
│   └── test_yarrrml_generator.py
├── review/
│   └── test_feedback.py
├── sources/
│   ├── test_cq_generator.py
│   └── test_qdrant_source.py
└── conftest.py
```

### Running Tests

```bash
make test            # 106 tests, fast (no network calls)
make test-verbose    # with full output
pytest tests/agents/ # just agent tests
```

### Mock Pattern for Agents

Agent tests mock `httpx.post` to avoid real LLM calls:

```python
from unittest.mock import patch, MagicMock

def test_engineer_proposes():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": "Proposed hierarchy: ..."}
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        agent = OntologyEngineerAgent()
        msg = agent.propose(Phase.DEFINE_HIERARCHY, context="...")
        assert msg.role == AgentRole.ONTOLOGY_ENGINEER
```

### Adding Tests for TODOs

When implementing remaining TODOs, add tests that mock external services:

| Module | Mock target | Pattern |
|--------|------------|---------|
| gap_analyzer | `httpx.post` (Fuseki SPARQL) | Return mock SPARQL JSON bindings |
| class_generator | `httpx.post` (Ollama chat) | Return mock JSON class definition |
| version_manager | `httpx.post`/`httpx.put` (Fuseki GSP) | Verify request URIs and payloads |
| cq_evaluator | `httpx.post` (Fuseki ASK) | Return `{"boolean": true/false}` |

# Implementation Plan — OntologyExtender

> **Status snapshot**: 2025-07-24
> **Tests**: 144 passing, 3 pre-existing fixture failures
> **Seed ontology**: AI Planning Ontology (`data/seed_ontology/plan-ontology-v1.0.owl`)
> **Document source**: Qdrant collection `documents` (localhost:6333)

---

## Table of Contents

1. [Current System Completeness](#1-current-system-completeness)
2. [Debate Strategy Integration Map](#2-debate-strategy-integration-map)
3. [Moderator Orchestration Flow](#3-moderator-orchestration-flow)
4. [Remaining Engineering Work](#4-remaining-engineering-work)
5. [Seed Ontology Integration](#5-seed-ontology-integration)
6. [End-to-End Pipeline Walkthrough](#6-end-to-end-pipeline-walkthrough)
7. [Integration Testing Plan](#7-integration-testing-plan)
8. [Performance Measurement Framework](#8-performance-measurement-framework)
9. [Deployment Checklist](#9-deployment-checklist)
10. [Stale TODO Cleanup](#10-stale-todo-cleanup)

---

## 1. Current System Completeness

### Comprehensive Audit Result

A full codebase audit reveals the system is **~95% complete**. Every module
listed below has working implementations for all public methods.

#### Fully Implemented Modules

| Package | Module | Description | SOTA Reference |
|---------|--------|-------------|----------------|
| **agents/** | `base.py` | `BaseAgent`, `AgentMessage`, `Debate`, `DebateOutcome`, `DebateVerdict` | — |
| | `ontology_engineer.py` | Proposer with 7 phase-specific identity prompts | Noy & McGuinness (2001) |
| | `domain_expert.py` | Hermeneutic reviewer (Gadamer) with document grounding | Gadamer (1960) |
| | `critic.py` | Falsificationist reviewer (Popper) with CQ checking | Popper (1934), Lakatos (1970) |
| | `team.py` | `AgentTeam` orchestrating 3-agent debates, 7 context builders | Du et al. (2023) |
| | `epistemics.py` | `EpistemicStance`, `KnowledgeStatus`, `SOCRATIC_DIMENSIONS`, `SYSTEM_ASSEMBLAGE` | Hegel, Peirce, Habermas, Deleuze |
| | `debate_strategies.py` | `DebateStrategist` with 5 strategies (dialectical, Socratic, Delphi, abductive, consensus) | Du et al. (2023), Liang et al. (2023) |
| | `moderator.py` | `Moderator` — deterministic strategy selection, grounding enforcement, drift detection | Habermas (1981), Feyerabend (1975) |
| **core/** | `loop_orchestrator.py` | `FeedbackLoopOrchestrator` — iterative convergence loop with W&B logging | John et al. (2025) |
| | `feedback_protocol.py` | `FeedbackMetrics`, `IterationPlan`, `ConvergenceReport`, `LoopMode` | — |
| | `config.py` | Pydantic `Settings` with `HITL_` env prefix | — |
| | `models.py` | 11 data models (`ProposedClass`, `GapCandidate`, etc.) | — |
| | `protocols.py` | 4 Protocol interfaces | — |
| **methodology/** | `pipeline.py` | `Ont101Pipeline` — 7-phase multi-agent pipeline | Noy & McGuinness (2001) |
| | `ontology101.py` | `Phase`, `OntologyScope`, `ClassHierarchy`, `PropertyProposal`, etc. | Noy & McGuinness (2001) |
| | `validation_rules.py` | 8 structural validation rules (naming, depth, disjointness) | Guarino & Welty (2002) |
| **discovery/** | `gap_analyzer.py` | SPARQL + embedding gap analysis | — |
| | `class_generator.py` | LLM class generation with JSON parsing | — |
| | `relation_generator.py` | LLM relation suggestion with SPARQL context | — |
| | `entity_linker.py` | Link to Wikidata/BFO/EMMO/schema.org/SAREF | John et al. (2025) |
| | `embedding_advisor.py` | Ollama embeddings for parent recommendation | Memariani et al. (2025) |
| | `ensemble_strategy.py` | Weighted LLM + embedding + co-occurrence ensemble | Mossakowski (2023+) |
| **schema/** | `manager.py` | OWL export with rdflib, CQ JSON export | — |
| | `seed_manager.py` | `SeedProtectedOntology` — extension-by-inheritance | Azure DTDL pattern |
| | `shacl_generator.py` | SHACL shape generation + optional pyshacl validation | — |
| | `version_manager.py` | Fuseki Graph Store Protocol operations | — |
| **evaluation/** | `cq_evaluator.py` | Structural + LLM-to-SPARQL CQ evaluation | — |
| | `completeness.py` | Two-stage entity coverage (exact + embedding) | — |
| | `ontology_quality.py` | 5-perspective quality assessment | Vrandečić (2009), Gangemi et al. (2006) |
| | `provenance.py` | PROV-O evidence chain tracking | John et al. (2025) |
| | `feedback_learner.py` | Few-shot learning from HITL decisions | John et al. (2025) |
| **review/** | `cli.py` | Rich/Typer interactive review with resume | — |
| | `web.py` | Streamlit dashboard | — |
| | `feedback.py` | Decision persistence, agreement rates | — |
| **sources/** | `qdrant_source.py` | Document chunk retrieval from Qdrant | — |
| | `cq_generator.py` | CQ generation from documents via LLM | — |
| **mapping/** | `yarrrml_generator.py` | YARRRML/RML mapping rules | — |
| **scripts/** | 8 CLI scripts | `run_feedback_loop.py`, `run_gap_analysis.py`, etc. | — |

### What is Genuinely Incomplete

| Item | Priority | Component | Description |
|------|----------|-----------|-------------|
| OWL reasoner integration | **HIGH** | `ontology_quality.py` → `analyze_consistency()` | Currently does structural checks only (unlabeled classes, orphan properties). Needs HermiT/Pellet reasoner integration for unsatisfiable class detection and logical consistency checking. |
| pyshacl optional dep | **MEDIUM** | `schema/shacl_generator.py` → `validate_with_pyshacl()` | Code exists but `pyshacl` is an optional dependency — needs verification it works in the current environment. |
| Stale TODO docstrings | **LOW** | 12 files, ~48 markers | Docstring TODOs that describe implementations which already exist below them. Misleading — should be cleaned up. |
| Bare `except: pass` | **LOW** | Scattered | Some error handlers swallow exceptions silently. Should at minimum log warnings. |

---

## 2. Debate Strategy Integration Map

### How Strategies Connect to the Pipeline

The Moderator selects a debate strategy per Ont-101 phase based on the
`DEFAULT_STRATEGY_MAP`. Each strategy determines how agents interact
during that phase's debate.

```
Pipeline Phase          Strategy Selected       Mechanism
─────────────────       ──────────────────      ─────────────────────────
Phase 1: SCOPE    ───→  SOCRATIC               Multi-dimensional questioning
Phase 2: REUSE    ───→  CONSENSUS              Equal-voice discourse
Phase 3: TERMS    ───→  SOCRATIC               Assumption examination
Phase 4: HIERARCHY ──→  DIALECTICAL            Thesis → Antithesis → Synthesis
Phase 5: PROPERTIES ─→  DIALECTICAL            Competing valid designs
Phase 6: FACETS   ───→  DELPHI                 Anonymous iterative consensus
Phase 7: INSTANCES ──→  ABDUCTIVE              Hypothesis → Examination → Parsimony
```

### Strategy Execution Detail

#### Dialectical (Phases 4–5: Hierarchy, Properties)

```
Engineer → THESIS (structured proposal with explicit claims)
    ↓
Expert + Critic → ANTITHESIS (genuine counter-positions, not nitpicks)
    ↓
Engineer → SYNTHESIS (sublation — preserves valid insights from both)
    ↓
Expert + Critic → AUFHEBUNG CHECK (is synthesis genuinely higher?)
    ↓
If contradictions unresolved → ESCALATE to HITL
```

**Why here**: Hierarchy and property design involve genuinely competing
valid options (granularity vs simplicity, domain accuracy vs formal
elegance). The dialectical approach forces both sides to be articulated
and resolved, rather than defaulting to the first proposal.

**SOTA connection**: Du et al. (2023) showed multi-agent debate improves
factuality by 15–25%. The dialectical structure channels disagreement
productively — the synthesis must be *better* than either position alone,
not a bland compromise.

#### Socratic (Phases 1, 3: Scope, Terms)

```
Engineer → Precise claim ("The ontology should cover X because Y")
    ↓
For each epistemic dimension (ontological, epistemological,
    pragmatic, methodological, coherence):
    ↓
    Expert + Critic → Dimension-specific questions
        "What KIND of thing is this?" (ontological)
        "HOW do we know this?" (epistemological)
        "What is this FOR?" (pragmatic)
        "Is this well-constructed?" (methodological)
        "Does this fit the whole?" (coherence)
    ↓
    Engineer → Revise or declare aporia
    ↓
If withstands all dimensions → ACCEPT
If genuine aporia → ESCALATE (honest puzzlement, not failure)
```

**Why here**: Foundational phases where *what things are* matters more
than *how to structure them*. Socratic questioning prevents the ontology
from inheriting unexamined assumptions from the document corpus.

#### Delphi (Phase 6: Facets)

```
Engineer → Initial proposal for constraints/cardinalities
    ↓
Round 1: Expert reviews independently (no anchoring)
         Critic reviews independently (no anchoring)
    ↓
Aggregate anonymous feedback (approval rate + top issues)
    ↓
Round 2: Expert sees aggregate (not individual opinions)
         Critic sees aggregate
         Each revises position if aggregate reveals new info
    ↓
Check convergence (≥80% agreement?)
    ↓
If converged → ACCEPT
If not → more rounds or ESCALATE
```

**Why here**: Facet definition involves many independent constraint
decisions. The Delphi method prevents the first reviewer's opinion
from anchoring subsequent reviews — each agent forms their own
judgement before seeing the aggregate.

#### Abductive (Phase 7: Instances)

```
Identify SURPRISING FACT (gap entities or unanswerable CQs)
    ↓
Engineer → Propose EXPLANATORY HYPOTHESIS (simplest extension
           that would make the gap expected)
    ↓
Expert + Critic examine:
    1. Does this EXPLAIN the gap or merely describe it?
    2. Is this the SIMPLEST adequate explanation? (Ockham)
    3. What ALTERNATIVE hypotheses exist?
    4. Does this generate NEW testable predictions?
    ↓
If best explanation → ACCEPT
If better alternative found → REVISE
If underdetermined → ESCALATE
```

**Why here**: Instance validation reveals gaps that the earlier design
phases missed. Abductive reasoning (inference to best explanation) is
exactly how scientists extend theories to accommodate new data.

#### Consensus (Phase 2: Reuse; default)

```
Engineer → Proposal with justification
    ↓
Expert → Review (equal standing, no hierarchy)
Critic → Review (equal standing)
    ↓
If both approve → CONSENSUS
If issues → Engineer revises without penalty (no sunk-cost)
    ↓
Repeat up to max_rounds
    ↓
If genuine underdetermination → ESCALATE
```

**Why here**: Reuse analysis benefits from balanced multi-perspective
evaluation. No agent should dominate — the goal is *warranted agreement*
achieved through the force of the better argument.

### Strategy Fallback Logic

When a strategy fails to converge, the Moderator selects an alternative:

```
Failed strategy → Fallback sequence:
  CONSENSUS → DIALECTICAL → SOCRATIC → ABDUCTIVE → DELPHI
```

The failed strategy is removed from the fallback sequence. Each subsequent
failure advances one step through the sequence. This implements Deleuze &
Guattari's "deterritorialisation": when one approach fails, the system
reterritorialises on a different philosophical tradition rather than
escalating immediately.

---

## 3. Moderator Orchestration Flow

The Moderator is a **deterministic orchestration layer** (no LLM calls).
It monitors discourse health and intervenes structurally.

### Full Orchestration Sequence

```
┌─────────────────────────────────────────────────────────────────┐
│                    FOR EACH ONT-101 PHASE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Moderator.select_strategy(phase, prior_failures)            │
│     ↓                                                           │
│  2. DebateStrategist.orchestrate_debate(                        │
│         strategy, propose_func, review_funcs, revise_func)      │
│     ↓                                                           │
│  3. DURING debate — after each revision:                        │
│     a. Moderator.analyze_grounding(proposal, CQs, seed_classes) │
│        → GroundingReport                                        │
│     b. Moderator.detect_drift(debate, grounding_report)         │
│        → DriftReport                                            │
│     c. IF drift detected:                                       │
│        Moderator.generate_corrective_context(drift, grounding)  │
│        → corrective prompt injected into next round              │
│     ↓                                                           │
│  4. DebateStrategist._determine_outcome(debate)                 │
│     → CONSENSUS | REVISED | ESCALATED                           │
│     ↓                                                           │
│  5. Moderator.assess_debate_health(debate)                      │
│     → health metrics logged                                     │
│     ↓                                                           │
│  6. Moderator.reset_tracking()                                  │
│     → clean state for next phase                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Grounding Stack (6 Layers)

The Moderator enforces a layered defence against ontological drift:

| Layer | Check | Threshold | Response on Violation |
|-------|-------|-----------|----------------------|
| 1. Document grounding | Every element cites evidence | `grounding_ratio ≥ 0.85` | "Provide citations or WITHDRAW" |
| 2. CQ anchoring | Every element serves a CQ | `cq_coverage ≥ 0.80` | "Remove elements serving no CQ" |
| 3. Seed tethering | Extensions connect to seed | `connectivity ≥ 0.90` | "Re-anchor to seed classes" |
| 4. Complexity budget | Max new elements per phase | `≤ 20 elements/phase` | "Simplify — which can be MERGED?" |
| 5. Drift detection | Embedding similarity to corpus | `drift_score < 0.4` | Switch to Abductive strategy |
| 6. HITL veto | Human reviewer approves all | Every element reviewed | Accept / Reject / Revise |

### Drift Patterns Detected

| Pattern | Statistical Signature | Automatic Response |
|---------|----------------------|-------------------|
| **Hallucination spiral** | `grounding_ratio < 0.85` | Halt debate, demand re-grounding |
| **Complexity ratchet** | N consecutive additive revisions | Inject simplification prompt |
| **Conceptual drift** | `connectivity_ratio < 0.6` | Flag orphan elements |
| **Echo chamber** | All-approve-no-issues for N rounds | Inject Socratic questioning |
| **Scope creep** | `cq_coverage < 0.8` | Auto-reject elements without CQ mapping |

---

## 4. Remaining Engineering Work

### 4.1 HIGH Priority: OWL Reasoner Integration

**File**: `src/ontology_hitl/evaluation/ontology_quality.py`
**Method**: `analyze_consistency()`
**Current state**: Structural checks only (unlabeled classes, orphan properties)

**What's needed**:
Integrate an OWL 2 reasoner to detect:
- Unsatisfiable classes (classes that cannot have instances)
- Logical inconsistencies (contradictory axioms)
- Entailed subsumption not explicit in the ontology

**Implementation options** (ranked):

| Option | Dependency | Pros | Cons |
|--------|-----------|------|------|
| **owlready2** | `pip install owlready2` | Pure Python, includes HermiT, no Java needed | Slower on large ontologies |
| **py-horned-owl** | `pip install py_horned_owl` | Rust-based, very fast, OWL 2 support | Newer, less battle-tested |
| **robot.jar** (CLI) | Java + robot.jar | Industry standard, full OWL 2 reasoning | External Java dependency |

**Recommended approach**: `owlready2` — it bundles HermiT internally
and requires no Java setup. Code sketch:

```python
def analyze_consistency(self, ontology_path: str | None = None) -> Dict[str, Any]:
    """Check ontology for logical consistency using HermiT reasoner."""
    if not ontology_path:
        return {"consistency_score": 0.0, "issues": []}

    # Structural checks (existing code — keep)
    structural = self._structural_checks(ontology_path)

    # OWL reasoning (new)
    try:
        import owlready2
        onto = owlready2.get_ontology(f"file://{ontology_path}").load()
        with onto:
            owlready2.sync_reasoner_hermit(infer_property_values=True)
        unsatisfiable = list(onto.inconsistent_classes())
        structural["unsatisfiable_classes"] = [str(c) for c in unsatisfiable]
        structural["reasoner_used"] = "HermiT (via owlready2)"
        structural["logically_consistent"] = len(unsatisfiable) == 0
        # Adjust score
        if unsatisfiable:
            structural["consistency_score"] *= 0.5
    except ImportError:
        structural["reasoner_used"] = "none (owlready2 not installed)"
    except Exception as e:
        structural["reasoner_error"] = str(e)

    return structural
```

**Effort**: ~2 hours (including tests)
**Test**: Mock `owlready2.sync_reasoner_hermit`, verify unsatisfiable detection

### 4.2 MEDIUM Priority: pyshacl Dependency Verification

**File**: `src/ontology_hitl/schema/shacl_generator.py`
**Method**: `validate_with_pyshacl()`

**Current state**: Code exists and uses `pyshacl.validate()`. The
dependency is listed as optional in `pyproject.toml`.

**Action items**:
1. Verify `pyshacl` is installable in the current environment
2. Write an integration test that validates a known-good shape against
   a test graph
3. Add graceful fallback if `pyshacl` is not available (already partially there)

**Effort**: ~1 hour

### 4.3 LOW Priority: Stale TODO Cleanup

**Scope**: 48 stale `TODO` markers across 12 files where the described
implementation already exists below the docstring.

**Action**: Replace stale `TODO` comments with accurate docstrings.
This is mechanical but prevents confusion for new contributors.

**Files affected** (count of stale TODOs):
- `discovery/gap_analyzer.py` (3)
- `discovery/class_generator.py` (4)
- `discovery/relation_generator.py` (3)
- `schema/manager.py` (3)
- `schema/shacl_generator.py` (4)
- `schema/version_manager.py` (6)
- `evaluation/cq_evaluator.py` (5)
- `evaluation/completeness.py` (4)
- `review/cli.py` (3)
- `review/web.py` (2)
- Other files (11)

**Effort**: ~3 hours (mechanical, can be done in one pass)

### 4.4 LOW Priority: Error Handler Improvement

**Scope**: Several `except: pass` blocks that should log warnings.

**Action**: Replace bare `except: pass` with:
```python
except Exception as e:
    logger.warning("operation_failed", error=str(e))
```

**Effort**: ~1 hour

---

## 5. Seed Ontology Integration

### AI Planning Ontology (plan-ontology-v1.0.owl)

The seed ontology is an OWL ontology for AI planning, located at
`data/seed_ontology/plan-ontology-v1.0.owl`.

**Statistics**:
- **Triples**: 228
- **Classes**: 18
- **Object Properties**: 26
- **Datatype Properties**: 4
- **Namespace**: `https://purl.org/ai4s/ontology/planning#`

**Class Inventory**:

| Class | Description | Extension Potential |
|-------|-------------|-------------------|
| `Action` | An action in a planning domain | HIGH — subtypes for domain-specific actions |
| `ActionEffect` | Effect of executing an action | MEDIUM — constrain with SHACL |
| `ActionPrecondition` | Precondition for an action | MEDIUM |
| `DomainConstant` | A constant in the planning domain | LOW |
| `DomainPredicate` | A predicate in the domain | MEDIUM |
| `DomainRequirement` | A requirement specification | HIGH — domain-specific subtypes |
| `GoalState` | Desired end state | MEDIUM |
| `InitialState` | Starting state | LOW |
| `MacroAction` | Composite action | HIGH — rich subtyping |
| `Parameter` | Action/predicate parameter | MEDIUM |
| `ParameterType` | Type of a parameter | MEDIUM |
| `Plan` | A plan (sequence of actions) | HIGH |
| `Planner` | A planning algorithm | HIGH — subtypes per planner type |
| `PlannerType` | Category of planner | MEDIUM |
| `PlanningDomain` | A planning domain specification | HIGH |
| `PlanningProblem` | A specific problem instance | HIGH |
| `ProblemObject` | An object in a problem | MEDIUM |
| `State` | A state in the planning world | MEDIUM |

### How the Pipeline Uses the Seed

1. **SeedProtectedOntology** loads the OWL file into a named graph
   (`urn:graph:seed`), which is never modified
2. **Ont-101 Phase 1 (Scope)**: Agents receive the 18 class labels +
   26 properties as context for defining scope
3. **Ont-101 Phase 2 (Reuse)**: `EntityLinker` checks proposed classes
   against Wikidata/BFO/EMMO for alignment opportunities
4. **Ont-101 Phase 4 (Hierarchy)**: `EmbeddingAdvisor` recommends
   parent classes from the seed ontology for new proposals
5. **Ont-101 Phase 4 (Hierarchy)**: `EnsembleStrategy` combines LLM
   + embedding + co-occurrence signals with seed context
6. **All phases**: `Moderator.analyze_grounding()` checks that proposed
   elements connect to the seed via `rdfs:subClassOf`
7. **Export**: `SeedProtectedOntology.build_merged()` produces a union
   of seed + extensions for the final OWL output

### Expected Extension Directions

Given that documents are in Qdrant and describe domain-specific
planning scenarios, the system should discover:

- Domain-specific action subtypes (e.g., `MovementAction`, `InspectionAction`)
- Domain-specific planner subtypes
- Additional properties connecting planning concepts to domain entities
- Constraint patterns (SHACL) for domain-specific validation
- Relations between planning concepts and operational domain concepts

---

## 6. End-to-End Pipeline Walkthrough

### Standalone Mode Execution

```
User runs: python scripts/run_feedback_loop.py --mode standalone --max-iterations 4

1. FeedbackLoopOrchestrator initialises
   - Loads Settings from .env
   - Initialises W&B run (if enabled)
   - Creates SeedProtectedOntology from plan-ontology-v1.0.owl
   - Creates ProvenanceTracker and FeedbackLearner

2. FOR iteration = 1..4:

   a. _plan_iteration()
      → IterationPlan(max_proposals=15 for iter 1-2, 10 after)

   b. _fetch_document_excerpts()
      → QdrantDocumentSource fetches 50 chunks from "documents" collection

   c. _get_seed_classes() / _get_seed_properties() / _get_seed_hierarchy_text()
      → Parses plan-ontology-v1.0.owl with rdflib

   d. Ont101Pipeline.run_iteration()
      │
      ├── Phase 1: SCOPE (Socratic)
      │   Engineer proposes scope → Expert + Critic question across 5 dimensions
      │   → OntologyScope (purpose, CQs, boundaries)
      │
      ├── Phase 2: REUSE (Consensus)
      │   Engineer identifies reusable ontologies → Equal-voice review
      │   EntityLinker checks Wikidata/BFO/EMMO alignment
      │   → ReuseReport
      │
      ├── Phase 3: TERMS (Socratic)
      │   Engineer enumerates terms → Assumption examination
      │   → TermEnumeration (class_candidates, property_candidates, instances)
      │
      ├── Phase 4: HIERARCHY (Dialectical)
      │   Engineer proposes hierarchy (thesis)
      │   Expert + Critic mount counter-positions (antithesis)
      │   Engineer revises (synthesis)
      │   Aufhebung check: is synthesis genuinely higher?
      │   EmbeddingAdvisor recommends parents from seed
      │   EnsembleStrategy aggregates LLM + embedding + co-occurrence
      │   ValidationRules check naming, depth, disjointness
      │   → ClassHierarchy
      │
      ├── Phase 5: PROPERTIES (Dialectical)
      │   Same dialectical flow for property definition
      │   → PropertyProposal list
      │
      ├── Phase 6: FACETS (Delphi)
      │   Independent anonymous reviews → aggregated feedback → iterate
      │   → FacetReport (cardinalities, ranges, SHACL constraints)
      │
      └── Phase 7: INSTANCES (Abductive)
          Identify gaps → propose explanatory extensions → examine
          → SampleInstance list + CQ answerability results

   e. Metrics collection
      → Entity coverage, CQ coverage, quality scores

   f. Convergence check
      → Stop if improvement < 2% or targets met (80%+ CQ, 80%+ coverage)

3. Export
   → convergence_report.json
   → provenance.json (PROV-O trail)
   → Extended OWL + SHACL + CQs
```

---

## 7. Integration Testing Plan

### Level 1: Unit Tests (Current — 144 passing)

All modules have unit tests with mocked external services. No network
calls required.

### Level 2: Component Integration Tests (To Add)

Test interactions between modules with mocked external services:

| Test | Components | What to Verify |
|------|-----------|---------------|
| **Pipeline + Team** | `Ont101Pipeline` → `AgentTeam` → `DebateStrategist` | All 7 phases execute, strategies selected correctly, outcomes produced |
| **Pipeline + Moderator** | `Ont101Pipeline` → `Moderator` → `DebateStrategist` | Grounding enforcement, drift detection, corrective injection |
| **Pipeline + Seed** | `Ont101Pipeline` → `SeedProtectedOntology` | Seed classes provided as context, extensions connect to seed |
| **Pipeline + Ensemble** | `Ont101Pipeline` → `EnsembleStrategy` + `EmbeddingAdvisor` | Ensemble votes aggregated correctly for hierarchy |
| **Pipeline + Provenance** | `Ont101Pipeline` → `ProvenanceTracker` | Evidence recorded for each agent message, PROV-O export valid |
| **Pipeline + FeedbackLearner** | `Ont101Pipeline` → `FeedbackLearner` | Prior decisions augment prompts, rejection warnings applied |
| **Orchestrator + Pipeline** | `FeedbackLoopOrchestrator` → `Ont101Pipeline` | Multi-iteration loop converges, metrics tracked, W&B logged |

**Effort**: ~2 days
**Approach**: Create `tests/integration/` directory, mock only Ollama + Qdrant + Fuseki

### Level 3: Live Service Tests (Manual)

With all Docker services running:

```bash
# Verify Qdrant connectivity
python -c "from ontology_hitl.sources.qdrant_source import QdrantDocumentSource; \
    src = QdrantDocumentSource(); chunks = src.fetch_chunks(limit=5); \
    print(f'{len(chunks)} chunks fetched')"

# Verify Ollama connectivity
python -c "import httpx; r = httpx.post('http://localhost:18135/api/generate', \
    json={'model': 'qwen3:next', 'prompt': 'Hello', 'stream': False}); \
    print(r.status_code)"

# Verify seed ontology loads
python -c "from ontology_hitl.schema.seed_manager import SeedProtectedOntology; \
    spo = SeedProtectedOntology(); spo.load_seed('data/seed_ontology/plan-ontology-v1.0.owl'); \
    print(f'{len(spo.seed_classes())} seed classes loaded')"

# Single phase test (scope only)
python -c "
from ontology_hitl.core.config import Settings
from ontology_hitl.agents.team import AgentTeam
from ontology_hitl.methodology.ontology101 import Phase
s = Settings()
team = AgentTeam(settings=s, document_context='AI planning domain documents...', max_debate_rounds=1)
outcome = team.run_debate(phase=Phase.DEFINE_SCOPE, context='Extend the AI Planning Ontology')
print(f'Verdict: {outcome.verdict.value}')
print(f'Rounds: {outcome.rounds}')
"
```

### Level 4: Full Loop Test

```bash
# Dry run (1 iteration, auto-review)
python scripts/run_feedback_loop.py --mode standalone --max-iterations 1

# Monitored run (4 iterations, interactive review)
python scripts/run_feedback_loop.py --mode standalone --max-iterations 4
```

---

## 8. Performance Measurement Framework

### Strategy Effectiveness (Per Phase)

Track which strategy produces the best outcomes for each phase:

| Metric | How Measured | Logged To |
|--------|-------------|-----------|
| Convergence rate | `consensus_count / total_debates` per strategy | W&B |
| Rounds to consensus | Average rounds per strategy-phase pair | W&B |
| Escalation rate | `escalated / total` per strategy | W&B |
| Grounding retention | `post_grounding_ratio - pre_grounding_ratio` | W&B |
| CQ coverage delta | CQ improvement per iteration | W&B |
| False consensus rate | Consensus on eventually-rejected proposals | Feedback memory |

### Agent Effectiveness

| Metric | Engineer | Expert | Critic |
|--------|----------|--------|--------|
| Proposal acceptance rate | Accepted / proposed | — | — |
| Issue precision | — | Confirmed by HITL / raised | Confirmed / raised |
| Issue recall | — | Found by HITL / total HITL | Found / total HITL |
| Revision quality | CQ delta after revision | — | — |

### System Convergence

| Metric | Target | Measured By |
|--------|--------|-------------|
| Iteration productivity | 5–15 validated elements | `classes_added_this_iter` |
| HITL burden | < 10 decisions/iteration | `escalated_questions` count |
| CQ answerability | Monotonically increasing | `CQEvaluator` |
| Entity coverage | ≥ 80% within 3–4 iterations | `CompletenessAnalyzer` |
| Quality score | Improving over iterations | `OntologyQualityAnalyzer` |

---

## 9. Deployment Checklist

### Before First Run

- [ ] `.env` configured with correct ports and model names
- [ ] `docker compose up -d` — Ollama and Fuseki staging running
- [ ] Ollama model pulled: `docker exec ollama-ontology-extender ollama pull qwen3:next`
- [ ] Seed ontology present at `data/seed_ontology/plan-ontology-v1.0.owl`
- [ ] Qdrant collection `documents` populated with domain documents
- [ ] Virtual environment activated: `source .venv/bin/activate`
- [ ] Dependencies installed: `pip install -e ".[dev]"`
- [ ] Tests pass: `python -m pytest tests/ -v`

### Optional Enhancements

- [ ] Install `owlready2` for full OWL consistency checking
- [ ] Install `pyshacl` for SHACL constraint validation
- [ ] Configure W&B credentials for experiment tracking
- [ ] Set up Fuseki staging (port 3031) for version management

---

## 10. Stale TODO Cleanup

### Files with Stale TODOs

The following files contain `TODO` markers in their docstrings that
describe implementations which already exist in the code below them.
These should be updated to reflect the current state.

**Cleanup script** (to identify all instances):

```bash
grep -rn "TODO" src/ontology_hitl/ --include="*.py" | grep -v __pycache__ | grep -v ".pyc"
```

**Recommended action**: For each stale TODO:
1. Verify the implementation exists below it
2. Replace `TODO: Implement X` with a proper docstring describing what
   the method actually does
3. Keep only genuinely incomplete TODOs (the OWL reasoner being the
   only known one)

**PR template** for this cleanup:
```
Title: chore: Remove stale TODO markers, update docstrings
Body: Removes ~48 stale TODO comments where implementations already exist.
      No functional changes — documentation only.
```

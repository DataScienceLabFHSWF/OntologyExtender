# Iteration Workflow

End-to-end workflow for one ontology extension iteration cycle using the
multi-agent Ont-101 methodology.

## Prerequisites

- Qdrant running with document collection indexed
- Ollama running with `qwen3-next` model loaded
- (Optional) Fuseki running with seed ontology loaded
- (Optional) KnowledgeGraphBuilder extraction checkpoint (for coupled mode)

## Architecture Overview

```
                    ┌──────────────────────────────┐
                    │    Feedback Loop Orchestrator  │
                    │  (convergence tracking, W&B)   │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │     Ont-101 Pipeline          │
                    │  (7 phases, validation rules)  │
                    └──────────┬───────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼──────┐
    │ OntologyEngineer│ │ DomainExpert │ │   Critic    │
    │  (proposer)     │ │ (validator)  │ │ (quality)   │
    └────────────────┘ └──────────────┘ └─────────────┘
```

## Ont-101 Seven Phases

Each phase runs as a **multi-agent debate**: the OntologyEngineer proposes,
the DomainExpert and Critic review, the Engineer revises, until consensus
or escalation to HITL.

### Phase 1: Scope & Competency Questions
- Define what the ontology should cover
- Generate competency questions from documents
- Output: `OntologyScope` with domain, CQs, boundaries

### Phase 2: Reuse Analysis
- Identify existing ontologies to adapt (BFO, EMMO, Saref, etc.)
- Check for overlap with seed ontology
- Output: `ReuseReport` with candidates and recommendations

### Phase 3: Term Enumeration
- Extract important domain terms from Qdrant documents
- Classify as class, property, or instance candidates
- Output: `TermEnumeration` with categorised terms

### Phase 4: Class Hierarchy
- Build taxonomic structure from enumerated terms
- Apply Ont-101 naming and depth rules
- Validate hierarchy (max depth, naming conventions, disjointness)
- Output: `ClassHierarchy` with validated tree

### Phase 5: Property Definition
- Define datatype and object properties for each class
- Specify domain, range, and descriptions
- Link to document evidence
- Output: `PropertyProposal` list

### Phase 6: Facet Specification
- Specify cardinality, value ranges, and constraints
- Generate SHACL shapes for validation
- Output: `FacetReport` with constraints and shapes

### Phase 7: Instance Validation
- Test ontology against sample instances from documents
- Run CQ answerability checks
- Output: `SampleInstance` list with test results

## Debate Pattern (per phase)

```
Round 1:
  Engineer → proposes artefact
  Expert   → reviews against documents (approves or raises issues)
  Critic   → reviews structure/quality (approves or raises issues)

Round 2 (if issues raised):
  Engineer → revises based on feedback
  Expert   → re-reviews
  Critic   → re-reviews

Outcome:
  CONSENSUS  → all agents agree, proceed
  REVISED    → proposal improved, all accept the revision
  PARTIAL    → some issues resolved, minor ones accepted
  ESCALATED  → fundamental disagreement → HITL question
```

## Full Iteration Cycle

### Standalone Mode (Recommended)

```bash
# Run the full feedback loop (agents handle most decisions)
python scripts/run_feedback_loop.py --mode standalone --max-iterations 4
```

This will:
1. Fetch document excerpts from Qdrant
2. Run 7-phase multi-agent pipeline
3. Agents debate each phase artefact
4. Escalated questions queued for HITL review
5. Export extended ontology (OWL + SHACL + CQs)
6. Measure CQ answerability and entity coverage
7. If not converged → next iteration

### Coupled Mode (with KGB)

```bash
python scripts/run_feedback_loop.py --mode coupled \
    --checkpoint ../KnowledgeGraphBuilder/output/extraction_checkpoint.json \
    --max-iterations 4
```

Same as standalone, plus:
- Uses KGB extraction checkpoint for gap analysis
- Can trigger KGB re-extraction after ontology export

### Manual Steps

```bash
# Step 1 — Gap analysis
make gap V=v1 CHECKPOINT=<path-to-checkpoint>

# Step 2 — Generate proposals via multi-agent debate
make proposals V=v1

# Step 3 — Review escalated questions only
make review V=v1

# Step 4 — Export extended ontology + CQs
make export V=v1

# Step 5 — Evaluate improvement
make evaluate V=v1
```

## Convergence Criteria

The feedback loop stops when:
- Entity coverage improvement is < 2% between iterations, OR
- CQ answerability target (80%+) is reached, OR
- Maximum iteration count is reached

## Iteration Schedule

| Iteration | Focus | Expected Growth | Target Coverage |
|-----------|-------|-----------------|-----------------|
| v1 | Core domain concepts | 8-12 classes | 55-65% |
| v2 | Process & relationships | 6-10 classes | 70-80% |
| v3 | Fine-grained types | 5-8 classes | 80-85% |
| v4 | Edge cases + refinement | 3-5 classes | 85%+ |

## Outputs per Iteration

Each iteration produces artefacts in `data/iterations/{version}/`:

| Artefact | Description |
|----------|-------------|
| `scope.json` | Phase 1 — domain scope and CQs |
| `reuse_report.json` | Phase 2 — reuse analysis |
| `terms.json` | Phase 3 — enumerated terms |
| `hierarchy.json` | Phase 4 — class hierarchy |
| `properties.json` | Phase 5 — property definitions |
| `facets.json` | Phase 6 — facet specifications |
| `instances.json` | Phase 7 — instance validation |
| `debates/` | Full debate transcripts per phase |
| `questions.json` | Escalated questions for HITL |
| `evaluation_report.json` | Coverage and CQ metrics |

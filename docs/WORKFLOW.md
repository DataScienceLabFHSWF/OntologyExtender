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

#### Phase 2b: Entity Linking _(Module B)_
- Link uncovered terms to external ontologies (Wikidata, BFO, EMMO, schema.org, SAREF)
- Uses Ollama embeddings for cosine similarity matching + live Wikidata search
- Output: `EntityLinkReport` with links, coverage stats, and confidence scores

### Phase 3: Term Enumeration
- Extract important domain terms from Qdrant documents
- Classify as class, property, or instance candidates
- Output: `TermEnumeration` with categorised terms

### Phase 4: Class Hierarchy
- Build taxonomic structure from enumerated terms
- Apply Ont-101 naming and depth rules
- Validate hierarchy (max depth, naming conventions, disjointness)
- Output: `ClassHierarchy` with validated tree

#### Phase 4c: Embedding Advisor _(Module C)_
- Compute Ollama embeddings for seed classes and proposed classes
- Recommend parent classes via nearest-neighbour search
- Confidence score = gap between best and runner-up similarity
- Output: `EmbeddingAdvisorReport` with parent recommendations

#### Phase 4e: Ensemble Strategy _(Module E)_
- Weighted voting across three strategies: LLM (0.5), Embedding (0.3), Co-occurrence (0.2)
- LLM votes come from the Phase 4 debate consensus
- Embedding votes come from Module C recommendations
- Co-occurrence votes come from document chunk analysis
- Reports agreement scores and flags split decisions for HITL
- Output: `EnsembleReport` with final decisions and diagnostics

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

### Cross-Cutting Modules (active throughout all phases)

**Module A — Seed Protection**: The seed ontology is loaded into a
`SeedProtectedOntology` (extension-by-inheritance, inspired by Azure DTDL).
New classes always extend seed classes via `rdfs:subClassOf`; the seed graph
is never modified directly.

**Module D — Provenance Chain**: Evidence citations from agent proposals and
reviews are recorded by `ProvenanceTracker` throughout all debate phases.
Exports as PROV-O RDF triples or JSON audit trail.

**Module F — Feedback Learning Loop**: `FeedbackLearner` augments agent prompts
with few-shot examples from prior HITL accept/reject decisions. Rejection warnings
prevent repeated mistakes. Memory persists as JSON across sessions.

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

## Gap Detection Pipeline (Production / Coupled Mode Only)

> **Important**: The gap analyzer is a *production-only* component used
> exclusively in the coupled KGB pipeline for domain-specific experiments
> (e.g., nuclear decommissioning).  Benchmarking tests (OntoURL,
> TamingHallucinations, Plu et al.) do **not** build knowledge graphs and
> therefore never invoke the gap analyzer — comparisons would be unfair
> since baselines don't have the KG advantage.

### What It Does

The gap analyzer answers: *"Which real-world entity types appear in our
documents but have no corresponding class in the current ontology?"*

It bridges the KnowledgeGraphBuilder (KGB) extraction output and the
OntologyExtender by comparing extracted entity types against the seed
ontology's class hierarchy.

### How Gaps Are Found — Step by Step

```
  KGB Checkpoint                  Fuseki (Seed Ontology)
  ┌────────────────┐              ┌───────────────────┐
  │ extraction_    │              │  SPARQL query:     │
  │ checkpoint.json│              │  SELECT ?class     │
  │                │              │  WHERE {           │
  │ entities: [    │              │    ?class a        │
  │   {type:       │              │      owl:Class .   │
  │    "Facility"} │              │  }                 │
  │   {type:       │              │  → ["Action",      │
  │    "Permit"}   │              │     "Plan",        │
  │   {type:       │              │     "Planner", …]  │
  │    "Action"}   │              │                    │
  │ ]              │              │                    │
  └───────┬────────┘              └────────┬──────────┘
          │                                │
          └──────────┬─────────────────────┘
                     │
            ┌────────▼─────────┐
            │  Classification  │
            │                  │
            │  1. Exact match  │
            │     entity_type  │
            │     ∈ classes?   │
            │                  │
            │  2. Embedding    │
            │     similarity   │
            │     ≥ 0.65?      │
            │                  │
            │  Match → COVERED │
            │  No match → GAP  │
            └────────┬─────────┘
                     │
            ┌────────▼─────────┐
            │  Gap Candidates  │
            │                  │
            │  Group by type   │
            │  Filter by       │
            │    min_frequency │
            │  Find closest    │
            │    seed class    │
            │  Compute         │
            │    semantic dist │
            └──────────────────┘
```

**Algorithm in detail:**

1. **Load KGB Checkpoint** — Parse `extraction_checkpoint.json` from the
   KnowledgeGraphBuilder.  Each entity has a `label`, `entity_type`,
   `confidence`, and `evidence` spans linking back to source documents.

2. **Query Ontology Classes** — Send `SELECT DISTINCT ?class ?label` SPARQL
   to Fuseki (`http://localhost:3030/{dataset}/sparql`).  Extract `rdfs:label`
   or fall back to local name from URI.

3. **Classify Entities** — For each extracted entity:
   - **Exact match**: If `entity_type.lower()` matches any ontology class
     label (case-insensitive) → **covered**.
   - **Semantic match**: Compute embedding via Ollama `/api/embed` for both
     the entity type and every ontology class.  If cosine similarity ≥ 0.65
     with any class → **covered** (logs the match).
   - Otherwise → **uncovered** (gap candidate).

4. **Build Gap Candidates** — Group uncovered entities by `entity_type`:
   - Filter out types with frequency below `min_frequency` (default: 3)
   - For each gap: find the closest seed class (lowest semantic distance)
   - Sort by frequency descending → highest-impact gaps first

5. **Output `GapReport`** with:
   - Coverage statistics (total, covered, uncovered, coverage %)
   - List of `GapCandidate` objects (type, frequency, closest seed class,
     semantic distance, representative examples)

### Services Used

| Service | Purpose | Port |
|---------|---------|------|
| **Fuseki** | SPARQL query for `owl:Class` labels from seed ontology | 3030 |
| **Ollama** | Text embeddings via `/api/embed` for semantic matching | 18135 |

**Not used**: Neo4j.  The gap analyzer reads the *ontology* (Fuseki), not the
knowledge graph.  Neo4j stores the extracted KG triples, which is a downstream
concern for the GraphQAAgent.

### When It Runs in the Pipeline

```
Coupled mode iteration:
  1. Load KGB checkpoint        ← _load_checkpoint()
  2. Run gap analysis           ← OntologyGapAnalyzer.analyze()
  3. Feed gaps to Phase 3       ← uncovered types → term enumeration
  4. Multi-agent debate (7 phases)
  5. Export extended ontology
  6. Trigger KGB re-extraction
  7. Measure improvement → next iteration
```

In **standalone mode** (no KGB), entities come from Qdrant document
excerpts directly — the gap analyzer is skipped, and the multi-agent
pipeline discovers terms from raw text instead.

### Usage

```bash
# Manual gap analysis
python scripts/run_gap_analysis.py \
    --checkpoint ../KnowledgeGraphBuilder/output/extraction_checkpoint.json \
    --min-frequency 3 \
    --output data/iterations/v1/gap_report.json

# Automatic (coupled mode feedback loop)
python scripts/run_feedback_loop.py --mode coupled \
    --checkpoint ../KnowledgeGraphBuilder/output/extraction_checkpoint.json
```

---

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
| `2b_entity_links.json` | Phase 2b — entity linking to external ontologies _(Module B)_ |
| `terms.json` | Phase 3 — enumerated terms |
| `hierarchy.json` | Phase 4 — class hierarchy |
| `4c_embedding_advisor.json` | Phase 4c — embedding-based parent recommendations _(Module C)_ |
| `4e_ensemble.json` | Phase 4e — ensemble voting results _(Module E)_ |
| `properties.json` | Phase 5 — property definitions |
| `facets.json` | Phase 6 — facet specifications |
| `instances.json` | Phase 7 — instance validation |
| `provenance.json` | PROV-O evidence chain _(Module D)_ |
| `debates/` | Full debate transcripts per phase |
| `questions.json` | Escalated questions for HITL |
| `evaluation_report.json` | Coverage and CQ metrics |

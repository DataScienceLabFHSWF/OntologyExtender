# Evaluation Strategy

How we prove that our system works, and why each evaluation layer exists.

---

## 1. The Claim We Need to Prove

Our system claims three things:

1. **Agentic workflows** (multi-turn, debate, self-verify) produce better ontological outputs than single-shot LLM prompting
2. **Our architecture** (independent agents + structured review + moderator) outperforms simulated multi-role approaches (LLM4ACOE)
3. **Human-in-the-loop** adds value that no amount of automation can replicate

Each claim requires a different evaluation method. We use four layers.

---

## 2. Evaluation Layers

```
Layer 1: OntoURL Benchmark — Parametric (no RAG)
│   Proves: agentic workflows > vanilla prompting
│   Method: 15 standardized tasks × 6 strategies × 3 models
│   Compare against: published baselines (Qwen2.5, LLaMA3.3)
│
Layer 2: OntoURL Benchmark — with RAG
│   Proves: RAG + agentic > agentic alone
│   Method: same 15 tasks, but inject source ontology context
│   Compare against: Layer 1 scores (our own baseline)
│
Layer 3: LLM4ACOE Head-to-Head
│   Proves: our architecture > LLM4ACOE's HCOME architecture
│   Method A: reproduce their method as an OntoURL strategy (our turf)
│   Method B: run our method on their SAR domain (their turf)
│   Compare against: LLM4ACOE published results + our reproduction
│
Layer 4: Full System Evaluation (HITL)
│   Proves: grounded, iterative, human-supervised > autonomous
│   Method: 6-dimension scoring on gold-standard ontologies
│   Compare against: LLM-only baselines, Layer 1-3 scores
```

### Why this progression works

- **Layer 1** isolates the reasoning architecture — holds knowledge constant, varies only the workflow. Any improvement is purely from the agentic design.
- **Layer 2** shows what RAG adds on top of the agentic foundation.
- **Layer 3** proves our architecture beats the closest competitor under controlled conditions.
- **Layer 4** shows the complete system's value with HITL.

If Layer 1 shows no agentic improvement, the workflow design needs fixing. If Layer 3 shows no advantage over LLM4ACOE, our architecture isn't better. Only if all layers show progressive improvement do we have a strong overall claim.

---

## 3. Layer 1: OntoURL Parametric Benchmark

### 3.1 What OntoURL Tests

15 tasks across three cognitive levels, ~58K examples from 40 real-world ontologies:

| Level | Tasks | Metric | What It Tests |
|-------|-------|--------|---------------|
| **Understanding** (U1–U5) | Class defs, relations, property domains, instances | Accuracy | Can the model comprehend existing ontology structures? |
| **Reasoning** (R1–R5) | Inferred relations, constraints, SWRL, description logic | Accuracy | Can it perform formal ontological inference? |
| **Learning** (L1–L5) | Definition generation, hierarchy, properties, alignment | ROUGE-L / Triple-F1 | Can it *produce* new ontological structures? |

### 3.2 Our 6 Strategies

Ordered from simple to complex:

| Strategy | LLM Calls | Task Coverage | What It Mirrors in CogAgent |
|----------|-----------|---------------|---------------------------|
| `vanilla_zero` | 1 | All 15 tasks | Pure baseline — raw LLM capability |
| `cot` | 1 | All 15 tasks | Chain-of-thought reasoning |
| `engineer` | 1 | All 15 tasks | Ontology engineer role-play (proposal agent) |
| `self_verify` | 2 | All 15 tasks | Review agent feedback loop |
| `multi_turn` | 3 | L1–L5 | Iterative refinement pipeline |
| `debate` | 3 | L1–L5 | Multi-agent proposer-critic debate |

multi_turn and debate are restricted to Learning tasks because generate-then-critique is designed for generative tasks, not MCQ selection.

### 3.3 Why No RAG Is Valid Here

1. **Isolates agentic contribution.** Knowledge source is constant (parametric); only the workflow varies. Any improvement is purely from the strategy.
2. **Fair comparison.** Published OntoURL baselines (Qwen2.5-3B/72B, LLaMA3.3-70B) all run without RAG. Same conditions → fair comparison.
3. **Lower bound.** Our production system has RAG + HITL. OntoURL parametric scores are the *floor* — real performance is strictly better.

### 3.4 Expected Results

| Task Type | Expected Agentic Uplift | Why |
|-----------|------------------------|-----|
| U1–U5 | Minimal (0–5%) | MCQ comprehension is single-inference; little room for self-correction |
| R1–R4 | Small (5–10%) | CoT helps multi-step reasoning, but ceiling is set by model capability |
| R5 | Moderate (10–15%) | Boolean T/F benefits most from self-verification |
| L1 | Moderate (5–15%) | Multi-turn refinement → more precise definitions |
| L2–L4 | Significant (15–30%) | Debate and multi_turn should shine on structured construction |
| L5 | Moderate (10–20%) | Multi-turn ontology analysis before alignment catches missed mappings |

**Key prediction:** Small models (3B) should show proportionally *larger* uplift from agentic strategies — they benefit more from structured scaffolding.

---

## 4. Layer 2: OntoURL with RAG

### 4.1 The RAG Question

OntoURL tests parametric knowledge, but our production system uses RAG. Can we add RAG to OntoURL to show the additional lift?

### 4.2 What "Domain Documents" Means for OntoURL

OntoURL's questions are derived from 40 real-world ontologies across 8 domains (Healthcare, Finance, Food, Ecology, Legal, Sciences, Arts, Society). Each question includes a `domain` field (e.g., `health_medicine/addiction_ontology`) and often an entity IRI. The source ontology OWL files are available ([Google Drive](https://drive.google.com/drive/folders/1jpvdZ9uH9ZOXhrDiJdFI9wjvJM1DGwmj)).

**The challenge: the "documents" ARE the ontologies.** Unlike LC3's setup (where domain documents are fire incident reports and the ontology is built FROM those documents), OntoURL's questions are ABOUT the ontologies themselves. Feeding the ontology back as RAG context is somewhat circular — you're giving the LLM the answer source.

**But this is still a valid and interesting test:**
- A real ontology-aware agent WOULD consult the ontology to answer questions about it
- It tests whether our RAG pipeline can effectively chunk, index, and retrieve OWL structures
- The retrieval quality itself becomes a variable — bad chunking/retrieval won't help even if the answers are in the index
- It shows the delta between "LLM guessing about an ontology" vs. "LLM consulting the actual ontology"

### 4.3 Implementation Plan

| Step | What | Effort |
|------|------|--------|
| Download OWL files | Get all 40 ontologies from Google Drive (8 domain folders) | Low |
| Parse & chunk | Convert OWL to text chunks: class definitions, axiom groups, hierarchy subtrees | Medium |
| Index per ontology | Create per-ontology FAISS/Qdrant index using our existing vector store pipeline | Medium |
| RAG strategy | New `RAGStrategy` that retrieves from the correct ontology index based on the `domain` field | Low |
| Run benchmark | Same 15 tasks, same models, RAG column alongside parametric columns | Low |

**Total effort:** ~1 week. The hardest part is OWL-to-text chunking — ontology structures don't chunk as cleanly as prose documents. We need to decide granularity: individual axioms? Class blocks? Entire subgraphs?

### 4.4 What This Proves

- RAG on U1–U5 should provide **large** uplift — answers are literally in the ontology
- RAG on R1–R5 should provide **moderate** uplift — facts come from retrieval, inference still needed
- RAG on L1–L5 should provide **moderate** uplift — structural examples help, but generation is creative

The critical comparison: **RAG + vanilla** vs. **no-RAG + agentic**. If agentic strategies WITHOUT RAG beat vanilla WITH RAG on Learning tasks, that proves the workflow matters more than the knowledge source for generative ontology tasks.

---

## 5. Layer 3: LLM4ACOE Head-to-Head

### 5.1 Why LLM4ACOE Is the Right Comparison Target

LLM4ACOE (Soularidis et al., 2025) is the closest published system:
- Multi-agent ontology engineering with role-based collaboration
- RAG-enhanced (domain docs + OWL docs + ReAct examples)
- Published results: 78% CQ coverage on Search and Rescue domain

| Dimension | LLM4ACOE | Our System |
|-----------|----------|-----------|
| Agent roles | 3 fixed roles simulated in single prompt | 6+ independent agents with separate state |
| Quality control | None | Review agent + Moderator budget |
| LLMs | GPT-4o, Claude, Gemini (cloud only) | Ollama local (any open model) |
| RAG | 3 retrievers (domain, OWL, ReAct) | Multi-source (vector store, KG, web) |
| Iteration | Fixed 3 rounds | Configurable N with convergence detection |
| HITL | None | Structured review (accept/reject/revise) |
| Domain | SAR only | Any domain |

### 5.2 Comparison A: Their Method on Our Turf (OntoURL)

Implement LLM4ACOE's approach as OntoURL strategies:

**`hcome_single`** — Single LLM call with 3-role simulation prompt. All three HCOME roles respond in sequence. Tests whether role-playing alone adds value.

**`hcome_3round`** — 3 sequential calls matching LC3's enhanced pipeline: (1) generate from domain context, (2) refine with OWL axioms, (3) ReAct-style improvement.

Same models, same tasks, same metrics → differences are purely architectural. If our `debate` beats their `hcome_3round`, our architecture is better.

### 5.3 Comparison B: Our Method on Their Turf (SAR Domain)

LC3 provides everything needed:

| Resource | Location in LC3 repo |
|----------|---------------------|
| Domain documents | `data/SAR_docs_text/Fire_Document_{1-10}.txt` |
| Reference ontology | `Experiments/SAR/safers_ontology_V3.0.owl` |
| Competency questions | `Experiments/SAR/Phase_{1,2,3}/CQs/` |
| Their results | `Experiments/SAR/Phase_{1,2,3}/Ontologies/` |

**Plan:**
1. Download their SAR docs and reference ontology
2. Run our full pipeline (gap analysis → multi-agent debate → review) on the same docs
3. Use our local Ollama models (no cloud API)
4. Evaluate with CQ coverage (their metric, 78% target) AND our 6-dimension scoring
5. Compare: their GPT-4o output vs. our qwen3-next output vs. our llama3.2:3b output

### 5.4 Effort Estimate

| Task | Time |
|------|------|
| HCOME strategies for OntoURL | ~3h |
| Download SAR resources from LC3 repo | ~30min |
| Run our pipeline on SAR domain | ~2h |
| Evaluation and comparison tables | ~2h |
| **Total** | **~8h** |

---

## 6. Layer 4: Full System (6-Dimension HITL Evaluation)

### 6.1 Core Metrics (Already Implemented)

| Dimension | Weight | Target | What It Measures |
|-----------|--------|--------|-----------------|
| Semantic Correctness | 0.25 | ≥ 0.92 | Embedding alignment with gold standard |
| Hallucination Rate | 0.20 | < 0.05 | Elements with no gold-standard match |
| CQ Coverage | 0.20 | > 0.85 | Competency questions answerable |
| Hierarchy Quality | 0.10 | 0.8–1.0 | Depth/breadth vs. gold standard |
| Domain Compliance | 0.15 | ≥ 0.95 | Vocabulary/namespace alignment |
| Expert Acceptance | 0.10 | ≥ 0.87 | Human acceptance in HITL sessions |

These directly address failure modes from Lippolis et al. (2025): superfluous elements → Hallucination Rate, wrong axioms → Semantic Correctness, flat hierarchies → Hierarchy Quality.

### 6.2 Extended Methods

| Method | Source | What It Adds |
|--------|--------|-------------|
| **TamingHallucinations** | Fathallah et al. (2025) | Semantic matching (concept + triple level) |
| **OWLUnit** | Asprino (2024) | Ontology unit testing (annotation, CQ, inference, error) |
| **Lippolis metrics** | Lippolis et al. (2025) | OOPS! pitfall scan, superfluous rate, expert qualitative |

See [BENCHMARKING.md](BENCHMARKING.md) for implementation details of all metrics and baselines.

### 6.3 Existing Experiment Results

We have already run experiments with these 6-dimension metrics using our HITL pipeline (see `results/` directory). These results are preserved and will be incorporated into the final comparison. The experiments cover:
- Multiple debate strategies (consensus, dialectical, Socratic, Delphi, abductive)
- Small vs. large model comparison
- LLM-only baselines vs. full agentic pipeline

---

## 7. The Complete Comparison Matrix

| Comparison | Evaluation Layer | Metric | What It Proves |
|-----------|-----------------|--------|---------------|
| Our strategies vs. published baselines | L1: OntoURL (no RAG) | Accuracy, ROUGE-L, Triple-F1 | Agentic > vanilla |
| With RAG vs. without RAG | L2: OntoURL (RAG) | Same | RAG adds value |
| RAG+vanilla vs. no-RAG+agentic | L1 vs L2 cross | Same | Workflow vs. knowledge source |
| Our debate vs. HCOME 3-role | L3: OntoURL comparison | Same | Architecture matters |
| Our system vs. LLM4ACOE on SAR | L3: SAR domain | CQ coverage + 6-dim | Full system comparison |
| HITL vs. LLM-only | L4: Gold standard | 6-dim composite | HITL value quantified |
| Us vs. student baselines | L4: Lippolis methodology | Superfluous rate | Practical quality |

### Running Everything

```bash
# Layer 1: OntoURL parametric (currently running)
bash scripts/run_full_ontourl.sh

# Layer 2: OntoURL with RAG (after OWL indexing)
python scripts/run_ontourl_benchmark.py --strategy rag_vanilla --tasks ALL

# Layer 3a: LLM4ACOE methods on OntoURL
python scripts/run_ontourl_benchmark.py --strategy hcome_single hcome_3round --tasks ALL

# Layer 3b: Our system on SAR domain
python scripts/run_feedback_loop.py --mode standalone --documents data/sar_docs/

# Layer 4: Full 6-dimension evaluation
python scripts/run_benchmark.py evaluate --enable-semantic-matching --enable-owlunit
```
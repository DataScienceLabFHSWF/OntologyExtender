# Benchmarking Rationale: OntoURL, LLM4ACOE, and Our System

## 1. Why We Run the OntoURL Benchmark

### 1.1 The Core Question

Our system (CogAgent/OntologyExtender) claims that **agentic multi-role workflows** produce better ontological outputs than simple LLM prompting. OntoURL provides the first rigorous way to test this claim because it decomposes "ontology capability" into 15 measurable tasks across three cognitive levels:

| Level | Tasks | What It Measures |
|-------|-------|-----------------|
| **Understanding** (U1–U5) | Class definitions, relations, property domains, instance classification, instance definitions | Can the model comprehend existing ontological structures? |
| **Reasoning** (R1–R5) | Inferred relations, constraints, instance reasoning, SWRL logic, description logic | Can the model perform formal ontological inference? |
| **Learning** (L1–L5) | Definition generation, hierarchy construction, property construction, constraint construction, ontology alignment | Can the model *produce* new ontological structures? |

### 1.2 Why This Benchmark Without RAG Is Still Valid

**Objection:** *"Our system uses RAG-enhanced agents with document retrieval. OntoURL tests parametric knowledge only. Isn't this testing the wrong thing?"*

**Answer: No. Here's why the parametric-only evaluation actually strengthens our argument.**

1. **Isolating the agentic contribution.** By removing RAG, we hold the knowledge source constant (the LLM's training data) and vary only the *reasoning process*. Any improvement from self_verify, multi_turn, or debate strategies over vanilla prompting is **purely attributable to the agentic workflow**, not to better retrieval.

2. **Lower bound on system capability.** Our production system has RAG, knowledge graphs, and human-in-the-loop. OntoURL scores represent the *floor* of our system's capability — what it can do with just the LLM and the workflow. Real-world performance will be strictly better.

3. **Comparability with published results.** OntoURL provides published baselines (Qwen2.5-3B, Qwen2.5-72B, LLaMA3.3-70B) all tested without RAG. Running our models under identical conditions ensures fair comparison.

4. **Highlighting where structure helps most.** If agentic strategies improve Learning tasks (L1–L5) but not Understanding (U1–U5), that tells us exactly where multi-agent workflows add value: in *generative* ontology construction, not in comprehension.

### 1.3 What RAG Extension Would Require

To extend the OntoURL benchmark with RAG, we would need to:

| Component | Implementation | Effort |
|-----------|---------------|--------|
| **Ontology context retrieval** | For each OntoURL question, retrieve relevant triples/axioms from the source ontology as context | Medium — OntoURL provides ontology names, need to download and index all 40 source ontologies |
| **RAG adapter strategy** | New `RAGStrategy` that prepends retrieved ontology fragments to the prompt before answering | Low — extends existing `OntoURLStrategy` base class |
| **Fair comparison design** | Published OntoURL baselines don't use RAG, so RAG results would be a separate column ("Our System + RAG") alongside vanilla baselines | Design decision |
| **Chunking & embedding** | Process 40 OWL ontologies through our existing vector store pipeline (`src/ontology_hitl/sources/vector_store.py`) | Medium — need to parse OWL to text, chunk, embed |
| **Retrieval quality metrics** | Measure retrieval precision/recall to separate RAG quality from LLM quality | Low |

**This is Phase 2 work** — run parametric-only first, then add RAG to show the additional lift.

## 2. Strategy Coverage and Comparison

### 2.1 Our Benchmark Strategies

We run 6 strategies that form a clear progression from simple to complex:

```
Baseline Tier (1 LLM call per example, all tasks):
┌──────────────────┐
│ vanilla_zero     │  Direct prompt → answer (OntoURL's exact methodology)
│ cot              │  Chain-of-thought prefix before answering
│ engineer         │  Ontology engineer role-play system prompt
└──────────────────┘

Agentic Tier (2-3 LLM calls per example):
┌──────────────────┐
│ self_verify      │  Answer → verify reasoning → revise (ALL tasks)
│ multi_turn       │  Analyze → draft → critique → refine (L1–L5)
│ debate           │  Proposer → Critic → Revise cycle (L1–L5)
└──────────────────┘
```

### 2.2 What Each Strategy Tests

| Strategy | Mirrors in CogAgent | Hypothesis |
|----------|---------------------|------------|
| `vanilla_zero` | — (pure baseline) | Control group: raw LLM capability |
| `cot` | — (enhanced prompting) | Does step-by-step reasoning help ontology tasks? |
| `engineer` | Role-play in proposal agent | Does role framing improve ontological output quality? |
| `self_verify` | **Review agent** feedback loop | Does self-check catch and fix ontological errors? |
| `multi_turn` | **Iterative refinement** through pipeline stages | Does structured decomposition (analyze→draft→refine) improve generative quality? |
| `debate` | **Multi-agent debate** (proposer vs. critic) | Does adversarial review produce better ontological structures? |

### 2.3 Task × Strategy Coverage Matrix

| Strategy | U1-U5 (MCQ) | R1-R4 (MCQ) | R5 (Bool) | L1 (Text) | L2-L4 (Triple) | L5 (Tuple) |
|----------|:-----------:|:-----------:|:---------:|:---------:|:-------------:|:----------:|
| vanilla_zero | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| cot | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| engineer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| self_verify | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| multi_turn | — | — | — | ✅ | ✅ | ✅ |
| debate | — | — | — | ✅ | ✅ | ✅ |

multi_turn and debate are restricted to Learning tasks because the agentic analyze→draft→refine pattern is designed for *generative* tasks, not MCQ selection.

## 3. Comparison with LLM4ACOE (LC3 Framework)

### 3.1 LLM4ACOE Architecture Summary

LLM4ACOE (Soularidis et al.) — "LLM-based framework that automates the Collaborative Ontology Engineering process using simulated LLM-powered Agents enhanced with RAG" — is the closest published system to ours. Key architecture:

| Component | LLM4ACOE (LC3) | Our System (CogAgent) |
|-----------|----------------|----------------------|
| **Agent roles** | 3 fixed roles: Knowledge Engineer, Domain Expert, Knowledge Worker (HCOME methodology) | 6+ configurable agents: Proposal, Discovery, Gap Analysis, Review, Mapping, Moderator |
| **RAG sources** | 3 retrievers: SAR domain docs, OWL documentation, ReAct examples | Multi-source: vector store, knowledge graph, web search, ontology repos |
| **LLM backend** | GPT-4o, Gemini, Claude (closed-source, cloud API) | Ollama local (llama3.2, nemotron, qwen3-next) — fully self-hosted |
| **Reasoning** | ReAct-style think-act-observe prompting (baked into prompt) | Actual tool-use agents with structured state management |
| **Iteration** | 3 fixed rounds: (1) domain data → ontology, (2) OWL refinement, (3) ReAct refinement | Configurable N iterations with convergence detection |
| **Output** | Turtle (TTL) via regex extraction from LLM response | Structured OWL via dedicated OntologySerializer |
| **Evaluation** | Manual expert review on SAR domain | Automated 6-dimension scoring + OntoURL benchmark + expert review |
| **Reproducibility** | Requires OpenAI/Google/Anthropic API keys, fixed SAR domain | Fully local, any domain, open models |

### 3.2 How We Can Benchmark Against LLM4ACOE

**Direct OntoURL comparison is not possible** because LLM4ACOE:
- Uses closed-source models (GPT-4o) that we don't have API access for
- Their pipeline is domain-specific (Search and Rescue) and prompt-fixed
- No published OntoURL scores exist for LLM4ACOE

**What we CAN do:**

#### Option A: Reproduce Their Method on OntoURL (Recommended)

Implement LLM4ACOE's core approach as another benchmark strategy:

```python
class HCOMEStrategy(OntoURLStrategy):
    """Reproduce LLM4ACOE's HCOME 3-role simulation.
    
    Simulates Knowledge Engineer, Domain Expert, and Knowledge Worker
    having a collaborative discussion to answer each OntoURL question.
    """
    name = "hcome_3role"
```

This would involve:
1. **3-role prompt**: Exact HCOME role definitions from LC3's `PromptTemplates.py`
2. **Single-turn simulation**: One LLM call with the 3-role simulation prompt
3. **Multi-round variant**: 3 sequential rounds matching LC3's enhanced pipeline

**Advantage:** Same models, same evaluation, same dataset → fair comparison of *method*, holding everything else constant.

#### Option B: Structural Comparison Table

Even without running their code, we can produce a **theoretical comparison** based on architectural properties:

| Dimension | LLM4ACOE | Our System | Advantage |
|-----------|----------|-----------|-----------|
| Agent independence | Single LLM playing 3 roles (simulated multi-agent) | Separate agent invocations with independent reasoning | Ours — true separation of concerns |
| Quality control | None — no explicit validation step | Review agent with structured critique + Moderator budget | Ours — built-in error correction |
| Superfluous element control | None mentioned | Moderator agent with explicit budget/scope checks | Ours |
| Iteration convergence | Fixed 3 rounds | Configurable with convergence detection | Ours |
| RAG integration | 3 separate retrievers (SAR, OWL, ReAct) | Unified multi-source with relevance scoring | Comparable |
| Model flexibility | Tied to cloud APIs | Any Ollama-compatible model | Ours — cost, privacy, reproducibility |
| Domain flexibility | Hardcoded SAR domain | Generic (any seed ontology + documents) | Ours |

### 3.3 Implementation Plan for LLM4ACOE Comparison

**Can be implemented while the benchmark runs** — it's just another strategy:

```
1. Add HCOMEStrategy to strategies.py (~80 lines)
   - Adapts LC3's exact 3-role HCOME prompt format
   - Uses our OllamaAdapter (same model, fair comparison)
   
2. Add HCOMEEnhancedStrategy to strategies.py (~120 lines)
   - 3-round sequential refinement matching LC3's enhanced pipeline
   - Round 1: Generate ontology from domain context
   - Round 2: Refine with OWL axiom guidance  
   - Round 3: Apply ReAct-style structural improvement
   
3. Register in run_ontourl_benchmark.py
   
4. Run on same tasks × same models → direct comparison
```

**Estimated effort:** 2-3 hours to implement and wire up. Can run alongside our existing strategies.

## 4. The Complete Evaluation Argument

### 4.1 Three-Layer Evaluation Strategy

```
Layer 1: OntoURL Parametric Benchmark (current)
├── Tests: Pure LLM ontology capability across 15 tasks
├── Controls: Published baselines (Qwen2.5, LLaMA3.3)
├── Variables: Our 6 strategies × 3 models
├── Claim: Agentic strategies improve ontological output quality
└── Evidence: Score deltas on Learning tasks (L1–L5)

Layer 2: LLM4ACOE Method Comparison (next)
├── Tests: Our strategies vs. LC3's HCOME 3-role approach
├── Controls: Same models, same tasks, same evaluation
├── Variables: Architectural differences only
├── Claim: Independent agent roles + review loops outperform simulated multi-role
└── Evidence: Head-to-head score comparison on OntoURL

Layer 3: Full System HITL Evaluation (future)
├── Tests: Complete CogAgent pipeline with RAG + HITL + seed ontology
├── Controls: Gold-standard ontologies with graded reduction
├── Variables: Full system vs. LLM-only vs. LC3 approach
├── Claim: Grounded, iterative, human-supervised extension > autonomous generation
└── Evidence: 6-dimension composite score + expert review
```

### 4.2 Why This Progression Works

1. **Layer 1 isolates the reasoning architecture.** By removing RAG and HITL, we show that the *structure* of multi-agent workflows (not just better ingredients) drives improvement.

2. **Layer 2 provides methodological comparison.** Running LC3's HCOME approach on our infrastructure proves that our architecture genuinely outperforms the closest competitor, not just that different models perform differently.

3. **Layer 3 shows the complete value proposition.** Adding RAG + HITL on top of the agentic foundation demonstrates the full system's practical utility.

**Each layer builds on the previous one.** If Layer 1 shows no improvement from agentic strategies, we know the problem is in our workflow design (and Layer 2/3 won't help). If Layer 1 shows improvement but Layer 2 doesn't differentiate from LC3, our architecture isn't better, just equally good. Only if all three layers show progressive improvement do we have a strong claim.

### 4.3 What We Expect From Results

Based on the OntoURL paper's findings and our architecture:

| Task Type | Expected Agentic Uplift | Reasoning |
|-----------|------------------------|-----------|
| U1–U5 (Understanding) | **Minimal** (~0-5%) | MCQ comprehension is a single-inference task; self_verify may catch some errors but fundamentally limited by parametric knowledge |
| R1–R4 (Reasoning) | **Small** (~5-10%) | CoT and self_verify can improve multi-step reasoning, but the reasoning ceiling is set by the model's inference capability |
| R5 (Description Logic) | **Moderate** (~10-15%) | Boolean T/F benefits most from self-verification — the model can reason about its own uncertainty |
| L1 (Definition Generation) | **Moderate** (~5-15%) | Multi-turn refinement should produce more precise, complete definitions |
| L2–L4 (Triple Construction) | **Significant** (~15-30%) | This is where debate and multi_turn should shine — structured decomposition of complex construction tasks with error correction |
| L5 (Ontology Alignment) | **Moderate** (~10-20%) | Multi-turn analysis of two ontologies before alignment should catch missed mappings |

**Key prediction:** The absolute scores for small models (3B) will be low, but the *relative improvement* from agentic strategies should be proportionally larger for small models — because they benefit more from structured scaffolding.

## 5. Running the Benchmark

### 5.1 Current Configuration

```bash
# Models available via Ollama (localhost:18135):
llama3.2:3b       # 2.0 GB — small baseline  
nemotron-3-nano   # 24.3 GB — medium model
qwen3-next:latest # 50.4 GB — large model (79.7B params)

# Strategies (6 total):
vanilla_zero  # Baseline: direct prompt
cot           # Enhanced: chain-of-thought
engineer      # Enhanced: ontology engineer role
self_verify   # Agentic: answer → verify → revise
multi_turn    # Agentic: analyze → draft → refine (L1-L5)
debate        # Agentic: proposer → critic → revise (L1-L5)

# Full run command:
bash scripts/run_full_ontourl.sh
```

### 5.2 Resume Support

The benchmark runner saves results after every completed split as:
- `results/ontourl/<model>/<strategy>/<split>.jsonl` — per-example predictions
- `results/ontourl/<model>/<strategy>/<split>_summary.json` — metrics

Re-running with `--resume` skips completed splits. Safe to interrupt and restart.

### 5.3 Tracing

All benchmark runs are traced via:
- **LangSmith**: Tagged with `exp:ontourl_<model>`, `model:<model>`, `strategy:benchmark`
- **W&B**: Logged to `dsfhswf/ontology-hitl` with per-split metrics

### 5.4 Estimated Timeline

| Phase | Scale | Est. Time |
|-------|-------|-----------|
| Baseline strategies (vanilla, cot, engineer) × 3 models | ~294k inferences | ~40-70h |
| self_verify × 3 models | ~196k inferences | ~50-80h |
| multi_turn + debate × 3 models (L1-L5 only) | ~35k inferences × 3 calls | ~20-40h |
| **Total** | | **~110-190h** |

With 2× NVIDIA H200 NVL GPUs, the small and medium models run fast (~0.5s/inference). The 80B model is slower (~3-5s/inference).

## 6. After the Benchmark

### 6.1 Deliverables

1. **Comparison table** (auto-generated): Our 3 models × 6 strategies vs. published baselines (Qwen2.5-3B/72B, LLaMA3.3-70B)
2. **Capability profiles**: Understanding/Reasoning/Learning averages per model+strategy
3. **Strategy uplift analysis**: Per-task improvement from agentic strategies over vanilla baseline
4. **Cost-benefit analysis**: Quality improvement per additional LLM call
5. **LLM4ACOE comparison**: Head-to-head if HCOME strategy is implemented

### 6.2 What Success Looks Like

- **Minimum viable result:** Self_verify shows statistically significant improvement on L2–L4 Triple-F1 for at least one model
- **Good result:** Agentic strategies (debate, multi_turn) outperform vanilla by >10% on Learning tasks across all models
- **Ideal result:** Clear progression — vanilla < cot < engineer < self_verify < multi_turn ≈ debate — showing that each layer of agentic complexity adds value

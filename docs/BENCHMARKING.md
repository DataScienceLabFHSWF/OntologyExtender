# Benchmarking Framework

Comprehensive evaluation framework for comparing CogAgent against baselines
and state-of-the-art ontology evaluation methods. Integrates insights from
six recent research papers.

---

## Table of Contents

1. [Evaluation Architecture](#1-evaluation-architecture)
2. [Core Metrics (6 Dimensions)](#2-core-metrics-6-dimensions)
3. [Extended Evaluation Frameworks](#3-extended-evaluation-frameworks)
4. [Benchmark Datasets](#4-benchmark-datasets)
5. [Prompting Techniques Reference](#5-prompting-techniques-reference)
6. [Baseline Systems](#6-baseline-systems)
7. [CLI Usage](#7-cli-usage)
8. [Module Structure](#8-module-structure)
9. [References](#9-references)

---

## 1. Evaluation Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Benchmarking Framework                              │
├───────────────────┬─────────────────────────────────────────────────────────┤
│                   │                                                         │
│  Test Case Gen.   │  Gold-standard OWL → 4 reduction levels (50/75/90/95%)  │
│  (test_cases.py)  │  Periphery-first removal + CQ generation               │
│                   │                                                         │
├───────────────────┼─────────────────────────────────────────────────────────┤
│                   │                                                         │
│  System Adapters  │  CogAgent | Agent-OM | LLM4ACOE | NLP-W2V              │
│  (baselines.py)   │  Unified run() interface per system                     │
│                   │                                                         │
├───────────────────┼─────────────────────────────────────────────────────────┤
│                   │                                                         │
│  Core Metrics     │  6 dimensions: Semantic Correctness, Hallucination      │
│  (metrics.py)     │  Rate, CQ Coverage, Hierarchy Quality, Domain           │
│                   │  Compliance, Expert Acceptance                           │
│                   │                                                         │
├───────────────────┼─────────────────────────────────────────────────────────┤
│                   │                                                         │
│  Extended Evals   │  TamingHallucinations: concept + triple matching        │
│  (metrics.py)     │  OntoURL: 15-task capability profile                    │
│                   │  OWLUnit: ontology unit testing (4 test types)           │
│                   │  Lippolis et al.: multi-dimensional structural analysis  │
│                   │                                                         │
├───────────────────┼─────────────────────────────────────────────────────────┤
│                   │                                                         │
│  Datasets         │  OntoURL (58K questions) | TamingHallucinations         │
│  (datasets.py)    │  Plu et al. ISWC 2024 | Lippolis et al. 2025 | OAEI    │
│                   │                                                         │
├───────────────────┼─────────────────────────────────────────────────────────┤
│                   │                                                         │
│  Statistics &     │  Paired t-test, bootstrap CI, Cohen's d                 │
│  Reporting        │  LaTeX tables, Markdown, W&B integration                │
│                   │                                                         │
└───────────────────┴─────────────────────────────────────────────────────────┘
```

---

## 2. Core Metrics (6 Dimensions)

| Dimension | Weight | Target | Description |
|-----------|--------|--------|-------------|
| Semantic Correctness | 0.25 | ≥ 0.92 | Embedding-based alignment with gold standard |
| Hallucination Rate | 0.20 | < 0.05 | Elements with no gold-standard correspondence (inverted) |
| CQ Coverage | 0.20 | > 0.85 | Fraction of competency questions answerable |
| Hierarchy Quality | 0.10 | 0.8–1.0 | Class hierarchy depth and structure vs. gold standard |
| Domain Compliance | 0.15 | ≥ 0.95 | Alignment with domain vocabulary and namespace |
| Expert Acceptance | 0.10 | ≥ 0.87 | Human (or LLM-simulated) acceptance rate |

Composite score = weighted average across all six dimensions.

---

## 3. Extended Evaluation Frameworks

### 3.1 TamingHallucinations — Semantic Matching (Fathallah et al., 2025)

Automated evaluation comparing LLM-generated ontologies against expert-curated
reference ontologies using transformer-based semantic similarity.

**Method:**
- **Concept matching**: Embed concept label + definition using
  `all-MiniLM-L6-v2` (preferred) or an Ollama embedding model (fallback),
  compute cosine similarity matrix against reference. Threshold ≥ 0.55 = match.
- **Triple matching**: Convert SPO triples to sentences
  (`"{subject} {predicate} {object}"`), embed, match against reference.
  Threshold ≥ 0.50.
- **Cumulative evaluation**: Match sequentially against multiple reference
  ontologies with increasing domain specificity. Each round removes matched
  items from the unmatched pool.

**Our integration:**
- `SemanticMatchResult` model captures concept/triple match rates
- `BenchmarkEvaluator.score_semantic_match_concepts()` and
  `score_semantic_match_triples()` implement the pipeline
- Configurable thresholds and embedding model in `BenchmarkConfig`

**Embedding options / fallback**
- Preferred: `sentence-transformers` (local Python package) for fast,
  reproducible embeddings (model configurable via
  `BenchmarkConfig.semantic_match_model`).
- Fallback: Ollama `/api/embed` using `BenchmarkConfig.semantic_embedding_model`
  (default: `qwen3-embedding`) if `sentence-transformers` is not installed.
- To pull the Ollama embedding model locally run:

```bash
docker exec ollama-ontology-extender ollama pull qwen3-embedding
```

This makes the Ollama embedding route available for CI/workstation setups
that prefer hosting all models in the Ollama service.

**Source:** [NadeenAhmad/TamingHallucinations](https://github.com/NadeenAhmad/TamingHallucinations) (MIT)

### 3.2 OntoURL — Capability Profiling (Zhang et al., 2025)

The most comprehensive LLM ontology benchmark to date: 58,981 questions from
40 ontologies across 8 domains, structured into 15 tasks under three
Bloom-inspired capability levels.

**Capability taxonomy:**

| Level | Tasks | Metric | Description |
|-------|-------|--------|-------------|
| **Understanding** | U1–U5 | Accuracy | Factual recall: class defs, relations, property domains, instances |
| **Reasoning** | R1–R5 | Accuracy | Logical inference: inferred relations, constraints, SWRL, DL |
| **Learning** | L1–L5 | ROUGE-L / Triple-F1 | Generation: class defs, hierarchy, properties, alignment |

**All 15 tasks:**
- U1: Class Definition, U2: Class Relation, U3: Property Domain,
  U4: Instance Class, U5: Instance Definition
- R1: Inferred Relation, R2: Constraint, R3: Instance Class (Inferred),
  R4: SWRL-Based, R5: Description Logic
- L1: Class Def Generation, L2: Hierarchy Construction, L3: Property Construction,
  L4: Constraint Construction, L5: Ontology Alignment

**Key findings (20 LLMs evaluated):**
- LLMs are strong at Understanding, weak at Reasoning and Learning
- Best: Qwen2.5-72B, LLaMA3.3-70B
- Few-shot prompting improves Reasoning most (+5–10% accuracy)

**Our integration:**
- `OntoURLCapabilityProfile` model with per-task and per-capability scores
- `BenchmarkEvaluator.score_ontourl_profile()` for capability assessment
- Dataset: [XiaoZhang98/OntoURL](https://huggingface.co/datasets/XiaoZhang98/OntoURL) (CC BY 4.0)
- Code: [LastDance500/OntoURL](https://github.com/LastDance500/OntoURL)

### 3.3 OWLUnit — Ontology Unit Testing (Asprino, 2024)

Systematic unit testing for ontologies with four complementary strategies:

| Test Type | What It Verifies | How |
|-----------|-----------------|-----|
| **Annotation** | Entity annotations are complete | SHACL shapes validation |
| **CQ Verification** | CQs are answerable | CQ → SPARQL, IRI check, result isomorphism |
| **Inference** | Ontology is consistent + inferences hold | HermiT reasoner + SPARQL ASK |
| **Error Provocation** | Ontology rejects bad data | Inject inconsistencies, verify detection |

**Our integration:**
- `OWLUnitTestSuite` and `OWLUnitTestResult` models
- `BenchmarkEvaluator.score_owlunit_suite()` orchestrates all test types
- Can delegate to OWLUnit JAR or use rdflib-based approximation
- [luigi-asprino/owl-unit](https://github.com/luigi-asprino/owl-unit) (Apache 2.0)

### 3.4 Lippolis et al. — Multi-Dimensional Evaluation (2025)

The most rigorous multi-dimensional evaluation of LLM-generated ontologies,
using a benchmark of 10 ontologies with 100 CQs and 29 user stories.
Introduces **four complementary evaluation criteria**:

**Evaluation criteria:**

| Criterion | What It Measures | How |
|-----------|-----------------|-----|
| **OOPS! Pitfall Scanning** | Structural errors | Automated scan for critical pitfalls (wrong inverses, domain/range issues, cycles) |
| **CQ Modelling Proportion** | Requirements coverage | Expert assessment: is each CQ modelled in the OWL output? |
| **Superfluous Element Rate** | Conciseness | Count classes/properties not used in any SPARQL verification query |
| **Expert Qualitative Analysis** | Overall quality | Two knowledge engineers independently assess usability, completeness, accuracy |

**Key findings (GPT-4, o1-preview, Llama-3.1-405B):**
- o1-preview + Ontogenia achieves highest CQ modelling proportion
- All LLMs generate significant superfluous elements (10–60% depending on model)
- LLMs consistently produce wrong domain/range axioms
- Llama-3.1 generates the most critical OOPS! pitfalls and structural flaws
- Expert evaluations align closely with structural metrics
- **Reducing input context size improves LLM output quality** (Memoryless CQbyCQ > CQbyCQ)

**Superfluous element rates by model (averaged across stories):**

| Model | Technique | Superflu. Classes | Superflu. Obj. Props | Superflu. Data Props |
|-------|-----------|-------------------|---------------------|---------------------|
| GPT-4 | Ontogenia | 10.9% | 24.2% | 41.1% |
| o1-preview | Ontogenia | 18.8% | 40.5% | 46.9% |
| Llama-3.1 | Ontogenia | 38.9% | 41.6% | 38.9% |
| GPT-4 | MemorylessCQbyCQ | 31.9% | 18.2% | 41.7% |
| o1-preview | MemorylessCQbyCQ | 36.0% | 7.4% | — |

**Relevance to CogAgent:** Our multi-agent debate + Moderator grounding
enforcement directly addresses the superfluous element problem. The Critic
agent performs structural quality review analogous to OOPS! scanning, and
the Moderator's complexity budget (≤20 elements/phase) constrains over-generation.

**Source:** [arXiv:2503.05388](https://arxiv.org/abs/2503.05388) — Lippolis, Saeedizade,
Keskisärkkä, Zuppiroli, Ceriani, Gangemi, Blomqvist, Nuzzolese (2025)

### 3.5 Plu et al. — Comprehensive Benchmark (ISWC 2024)

Combines quantitative metrics against human-made reference ontologies with
qualitative user assessments across diverse domains.

**Evaluation approach:**
- **Quantitative**: Generate ontologies from source documents, compare
  against human reference using structural and semantic metrics
- **Qualitative**: Expert users assess for correctness, completeness,
  and usability across domains (software documentation, geography,
  music theory, business)
- **Models tested**: Claude 3.5 Sonnet, GPT-4o, GPT-4o-mini

**Source:** [jplu/ontology-benchmark](https://github.com/jplu/ontology-benchmark)

---

## 4. Benchmark Datasets

| Dataset | Samples | Domains | Tasks | Source | License |
|---------|---------|---------|-------|--------|---------|
| **OntoURL** | 58,981 | 8 | 15 | [HuggingFace](https://huggingface.co/datasets/XiaoZhang98/OntoURL) | CC BY 4.0 |
| **TamingHallucinations** | — | 3 | 4 | [GitHub](https://github.com/NadeenAhmad/TamingHallucinations) | MIT |
| **Lippolis et al.** | 100 CQs | 10 ontologies | 4 | [arXiv](https://arxiv.org/abs/2503.05388) | — |
| **Plu et al.** | — | 4 | 3 | [GitHub](https://github.com/jplu/ontology-benchmark) | — |
| **OAEI-LLM** | — | 3 | 3 | [OAEI](https://oaei.ontologymatching.org/) | Various |

### OntoURL Reference Ontologies (by domain)

| Domain | Ontologies |
|--------|-----------|
| Healthcare | SNOMED CT, LOINC, Gene Ontology, DrugBank |
| Geography | GeoNames, LinkedGeoData |
| Ecology | Environment Ontology (ENVO), Biological Collections |
| Finance | FIBO, Financial Industry Business |
| Food | FoodOn, Open Food Facts |

---

## 5. Prompting Techniques Reference

Based on Lippolis et al. (2025), two prompting techniques are relevant
for ontology generation benchmarking:

### Memoryless CQbyCQ

- Processes one CQ at a time with its ontology story
- Does **not** provide LLM with previously generated ontology state
- Reduces input context by ~60%
- Merges outputs into a single ontology at the end
- Includes common pitfalls to avoid in the prompt

**Key insight:** Reducing context size improves output quality. This
aligns with our system design, where each debate phase has focused
context rather than full pipeline history.

### Ontogenia

- Processes one CQ at a time, but incorporates previous output incrementally
- Uses Metacognitive Prompting (Wang et al., 2024) mapped to eXtreme Design
- Five stages: interpret requirements → identify classes/properties →
  extend with restrictions → validate with reasoning → generate test cases
- Injects Ontology Design Patterns from the ODP repository
- Produces richer, more pattern-based formalizations

**Key insight:** The five-stage metacognitive process mirrors our
7-phase Ont-101 pipeline. Ontogenia's pattern injection is analogous
to our Module B (Entity Linking) and Module C (Embedding Advisor).

### Comparison to Our Approach

| Aspect | Memoryless CQbyCQ | Ontogenia | CogAgent (ours) |
|--------|-------------------|-----------|-----------------|
| Context management | Minimal (1 CQ) | Incremental | Per-phase focused |
| Superfluous control | None | None | Moderator budget + Critic |
| Multi-perspective | No | No | 3 agents + 5 strategies |
| Human review | Post-hoc | Post-hoc | Integrated (HITL escalation) |
| Pattern reuse | Manual | ODP injection | Entity Linking + Embedding |

---

## 6. Baseline Systems

| System | Type | Paper | Key Mechanism |
|--------|------|-------|---------------|
| **CogAgent** (ours) | Extension | — | Multi-agent debate + HITL |
| **Agent-OM** | Matching | Qiang et al., VLDB 2024 | 2-agent matching with pgvector |
| **LLM4ACOE** | Extension | Soularidis et al., KER 2025 | 3-agent autonomous (Engineer/Expert/Worker) |
| **NLP-W2V** | Extension | Behr et al., 2023 | Word2Vec embeddings + ontology rules |

---

## 7. CLI Usage

```bash
# Initialise benchmark configuration
python scripts/run_benchmark.py init \
    --gold-standard data/seed_ontology/plan-ontology-v1.0.owl \
    --output-dir results/benchmarking

# Generate graded test cases (50%, 75%, 90%, 95% reduction)
python scripts/run_benchmark.py generate-test-cases \
    --config results/benchmarking/config.json

# Run all systems on all test cases
python scripts/run_benchmark.py run \
    --config results/benchmarking/config.json \
    --systems cogagent,agent_om,llm4acoe,nlp_w2v

# Evaluate with all metrics (core + extended)
python scripts/run_benchmark.py evaluate \
    --config results/benchmarking/config.json \
    --enable-semantic-matching \
    --enable-ontourl-profile \
    --enable-owlunit

# Generate publication-ready report
python scripts/run_benchmark.py report \
    --config results/benchmarking/config.json \
    --format markdown,latex
```

---

## 8. Module Structure

```
src/ontology_hitl/benchmarking/
├── __init__.py         # Package exports (15 public classes)
├── models.py           # Pydantic models: MetricScores, OntoURL*, OWLUnit*, SemanticMatch*
├── test_cases.py       # TestCaseGenerator: gold-standard → graded test cases
├── baselines.py        # BaselineAdapter ABC + 4 system adapters + factory
├── metrics.py          # BenchmarkEvaluator: 6 core + 3 extended evaluations
├── datasets.py         # DatasetManager: 4 registered datasets + loaders
├── aggregator.py       # ResultsAggregator: cross-system comparison tables
├── statistics.py       # StatisticalAnalyzer: t-test, bootstrap CI, Cohen's d
├── reporting.py        # ReportGenerator: charts, LaTeX, Markdown, W&B
└── runner.py           # BenchmarkRunner: 7-phase orchestrator + checkpointing
```

---

## 9. References

1. **Fathallah, N., Staab, S., & Algergawy, A.** (2025). *Taming
   Hallucinations in LLM-based Ontology Engineering.* CEUR-WS.
   [GitHub](https://github.com/NadeenAhmad/TamingHallucinations)

2. **Zhang, X., Lai, Z., Meng, R., & Bos, J.** (2025). *OntoURL: A
   Comprehensive Benchmark for Evaluating Large Language Models in
   Ontology Understanding, Reasoning, and Learning.* arXiv:2505.11031.
   [GitHub](https://github.com/LastDance500/OntoURL) ·
   [Dataset](https://huggingface.co/datasets/XiaoZhang98/OntoURL)

3. **Asprino, L.** (2024). *OWLUnit: Ontology Unit Testing.*
   [GitHub](https://github.com/luigi-asprino/owl-unit)

4. **Lippolis, A. S., Saeedizade, M. J., Keskisärkkä, R., Zuppiroli, S.,
   Ceriani, M., Gangemi, A., Blomqvist, E., & Nuzzolese, A. G.** (2025).
   *Ontology Generation using Large Language Models.* arXiv:2503.05388.

5. **Plu, J. et al.** (2024). *A comprehensive benchmark for evaluating
   LLM-generated ontologies.* ISWC 2024.
   [GitHub](https://github.com/jplu/ontology-benchmark)

6. **Qiang, S. et al.** (2024). *Agent-OM: Leveraging LLM Agents for
   Ontology Matching.* VLDB 2024.

7. **Soularidis, A. et al.** (2025). *LLM4ACOE: Autonomous Collaborative
   Ontology Extension Using LLM Agents.* Knowledge Engineering Review.

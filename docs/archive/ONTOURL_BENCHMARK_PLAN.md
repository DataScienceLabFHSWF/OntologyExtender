# OntoURL Benchmark Integration — Implementation Plan

> **Branch:** `feature/ontourl-benchmark`  
> **Paper:** Zhang et al. (2025) "OntoURL: A Benchmark for Evaluating LLMs on Symbolic Ontological Understanding, Reasoning and Learning" ([arXiv:2505.11031](https://arxiv.org/abs/2505.11031))  
> **Dataset:** [HuggingFace XiaoZhang98/OntoURL](https://huggingface.co/datasets/XiaoZhang98/OntoURL) — 97,771 questions, 40 ontologies, 8 domains  
> **License:** CC BY 4.0 / Apache 2.0

---

## 1. Motivation & Goals

OntoURL is the first comprehensive benchmark for evaluating LLM capabilities on
ontologies, covering **15 tasks** across three dimensions:

| Dimension | Tasks | Format | Metric |
|---|---|---|---|
| **Understanding** (U1–U5) | Class definition, relation, property domain, instance class/definition | MCQ | Accuracy |
| **Reasoning** (R1–R5) | Inferred relations, constraints, instance class, SWRL, description logic | MCQ / T-F | Accuracy |
| **Learning** (L1–L5) | Class definition generation, hierarchy/property/constraint construction, alignment | Generation | ROUGE-L, Triple-F1, Tuple-F1 |

**Our goal:** Run the OntoURL benchmark using our Ollama-hosted models and compare:

1. **Vanilla LLM baseline** — same approach as OntoURL (prompt → answer), establishing a fair comparison point against their published results
2. **Our advanced methods** — agentic strategies (multi-agent debate, iterative refinement) applied to the Learning tasks (L1–L5), where our system can differentiate
3. **Investigate** whether structured, multi-turn ontology engineering workflows improve performance on symbolic knowledge tasks

**Key constraint:** No RAG retrieval for this benchmark — all tasks rely on the LLM's parametric knowledge only, unless we identify suitable domain documents for OntoURL's 8 domains.

---

## 2. OntoURL Task Taxonomy (Complete Reference)

### 2.1 Understanding Tasks (U1–U5) — MCQ, Accuracy

| ID | Task | Split | Size | Description |
|---|---|---|---|---|
| U1 | Class definition understanding | `1_1` | 9,151 | Given a class, pick the correct definition from choices |
| U2 | Class relation understanding | `1_2` | 9,201 | Given two classes, identify the correct relationship |
| U3 | Property domain understanding | `1_3` | 375 | Identify the domain/range of a property |
| U4 | Instance class understanding | `1_4` | 2,475 | Given an instance, pick the correct class |
| U5 | Instance definition understanding | `1_5` | 3,814 | Given an instance, pick the correct definition |

### 2.2 Reasoning Tasks (R1–R5) — MCQ/T-F, Accuracy

| ID | Task | Split | Size | Description |
|---|---|---|---|---|
| R1 | Inferred relation reasoning | `2_1` | 8,208 | Infer transitive/implicit class relationships |
| R2 | Constraint reasoning | `2_2` | 6,956 | Reason about OWL constraints (disjointness, etc.) |
| R3 | Instance class reasoning | `2_3` | 3,793 | Infer instance class via reasoning chains |
| R4 | SWRL-based logic reasoning | `2_4` | 6,517 | Apply SWRL rules to derive conclusions |
| R5 | Description logic reasoning | `2_5` | 882 | T/F questions about DL expressions |

### 2.3 Learning Tasks (L1–L5) — Generation, ROUGE-L / F1

| ID | Task | Split | Size | Metric | Description |
|---|---|---|---|---|---|
| L1 | Class definition generation | `3_1` | 2,936 | ROUGE-L | Generate natural language definitions for classes |
| L2 | Class hierarchy construction | `3_2` | 952 | Triple-F1 | Given class list → produce (child, subClassOf, parent) triples |
| L3 | Property relation construction | `3_3` | 256 | Triple-F1 | Given classes + properties → produce (property, relation, class) triples |
| L4 | Constraint construction | `3_4` | 643 | Triple-F1 | Given classes + properties → produce (property, domain/range, class) triples |
| L5 | Ontology alignment | `3_5` | 1,149 | Tuple-F1 | Given two ontology fragments → produce alignment tuples |

---

## 3. Architecture Overview

```
scripts/
  run_ontourl_benchmark.py       ← NEW: Main benchmark runner script
  
src/ontology_hitl/benchmarking/
  ontourl/                        ← NEW: OntoURL integration package
    __init__.py
    loader.py                     ← Dataset loading from HuggingFace
    prompts.py                    ← Prompt templates per task (zero/few-shot)
    evaluator.py                  ← Metric computation (Accuracy, ROUGE-L, Triple-F1, Tuple-F1)
    strategies.py                 ← Strategy adapters (vanilla, agentic, multi-turn)
    reporter.py                   ← Results aggregation, comparison tables, charts
    
  datasets.py                     ← EXISTING: Wire up load_ontourl()
  models.py                       ← EXISTING: Already has OntoURLTask enum etc.
  metrics.py                      ← EXISTING: Wire up score_ontourl_profile()
```

---

## 4. Implementation Phases

### Phase 1: Data Loading & Infrastructure (1–2 days)

#### 1.1 Dataset Loader (`src/ontology_hitl/benchmarking/ontourl/loader.py`)

```python
class OntoURLLoader:
    """Load and cache OntoURL dataset from HuggingFace."""
    
    def __init__(self, cache_dir: Path = "data/benchmark_datasets/ontourl"):
        self.cache_dir = cache_dir
        self._dataset = None
    
    def load(self) -> DatasetDict:
        """Load full dataset (all 15 splits) from HuggingFace."""
        from datasets import load_dataset
        self._dataset = load_dataset("XiaoZhang98/OntoURL")
        return self._dataset
    
    def get_split(self, split_id: str) -> Dataset:
        """Get a specific split, e.g. '3_2' → class hierarchy construction."""
        ...
    
    def get_task_examples(self, task: OntoURLTask, max_n: int = None) -> list[dict]:
        """Get examples for a specific task."""
        ...
    
    def get_task_type(self, split_id: str) -> str:
        """Return 'mc', 'bool', 'open_text', 'open_triple', or 'open_tuple'."""
        ...
```

**Dependencies to add to `pyproject.toml`:**
```toml
datasets>=3.0      # HuggingFace datasets library
rouge-score>=0.1   # ROUGE metric (Google)
nltk>=3.8          # For BLEU tokenization
```

#### 1.2 Split-to-Task Mapping (reuse OntoURL's exact mapping)

```python
SPLIT_TASK_MAP = {
    "1_1": ("mc", OntoURLTask.U1_CLASS_DEFINITION),
    "1_2": ("mc", OntoURLTask.U2_CLASS_RELATION),
    "1_3": ("mc", OntoURLTask.U3_PROPERTY_DOMAIN),
    "1_4": ("mc", OntoURLTask.U4_INSTANCE_CLASS),
    "1_5": ("mc", OntoURLTask.U5_INSTANCE_DEFINITION),
    "2_1": ("mc", OntoURLTask.R1_INFERRED_RELATION),
    "2_2": ("mc", OntoURLTask.R2_CONSTRAINT),
    "2_3": ("mc", OntoURLTask.R3_INSTANCE_CLASS_INFERRED),
    "2_4": ("mc", OntoURLTask.R4_SWRL_BASED),
    "2_5": ("bool", OntoURLTask.R5_DESCRIPTION_LOGIC),
    "3_1": ("open_text", OntoURLTask.L1_CLASS_DEF_GENERATION),
    "3_2": ("open_triple", OntoURLTask.L2_HIERARCHY_CONSTRUCTION),
    "3_3": ("open_triple", OntoURLTask.L3_PROPERTY_CONSTRUCTION),
    "3_4": ("open_triple", OntoURLTask.L4_CONSTRAINT_CONSTRUCTION),
    "3_5": ("open_tuple", OntoURLTask.L5_ONTOLOGY_ALIGNMENT),
}
```

---

### Phase 2: Prompt Templates & LLM Interface Adapter (1–2 days)

#### 2.1 Prompt Templates (`src/ontology_hitl/benchmarking/ontourl/prompts.py`)

Replicate OntoURL's exact prompt format for fair comparison, plus enhanced versions for our methods:

```python
class OntoURLPromptBuilder:
    """Build prompts for OntoURL tasks."""
    
    def build_prompt(
        self,
        task_type: str,
        split_id: str,
        example: dict,
        shot_setting: str = "zero_shot",  # zero_shot, two_shot, four_shot
        enhanced: bool = False,            # Use enhanced ontology-engineer prompt
    ) -> str:
        """Build prompt for a single example."""
        ...
    
    def _build_mcq_prompt(self, example, shot_examples=None) -> str:
        """MCQ: question + options → answer letter (A/B/C/D)."""
        ...
    
    def _build_bool_prompt(self, example, shot_examples=None) -> str:
        """True/False: statement → true/false."""
        ...
    
    def _build_generation_prompt(self, example, split_id, shot_examples=None) -> str:
        """Generation: question → text/triples/tuples."""
        ...
    
    def _build_enhanced_hierarchy_prompt(self, example) -> str:
        """Our enhanced prompt: uses ontology engineering best practices,
        asks the LLM to reason about taxonomic principles before generating."""
        ...
```

**Prompt strategy variants:**

| Variant | Applicable Tasks | Description |
|---|---|---|
| `vanilla_zero` | All 15 | OntoURL's exact zero-shot prompt (direct comparison) |
| `vanilla_few` | All 15 | OntoURL's exact 2-shot / 4-shot prompts |
| `cot` | All 15 | Chain-of-thought reasoning before answering |
| `engineer` | L1–L5 | Ontology engineering role prompt with reasoning steps |
| `multi_turn` | L2–L4 | Multi-turn: first reason about structure, then generate |
| `debate` | L2–L4 | Simulated proposer/critic debate before final answer |

#### 2.2 Ollama LLM Interface Adapter (`strategies.py`)

Since OntoURL uses vLLM, we need an adapter that uses our Ollama HTTP interface:

```python
class OllamaOntoURLAdapter:
    """Call Ollama for OntoURL tasks, replacing vLLM."""
    
    def __init__(
        self,
        model: str = "llama3.2:3b",
        ollama_url: str = "http://localhost:18135",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ):
        ...
    
    def generate(self, prompt: str) -> str:
        """Single-turn generation via Ollama /api/generate."""
        ...
    
    def generate_batch(self, prompts: list[str]) -> list[str]:
        """Sequential batch generation (no vLLM batching)."""
        ...
    
    def generate_multi_turn(self, messages: list[dict]) -> str:
        """Multi-turn via Ollama /api/chat."""
        ...
```

---

### Phase 3: Evaluation Metrics (1 day)

#### 3.1 Metric Functions (`src/ontology_hitl/benchmarking/ontourl/evaluator.py`)

Reimplement OntoURL's exact evaluation metrics for reproducibility:

```python
class OntoURLEvaluator:
    """Compute OntoURL metrics."""
    
    def evaluate_split(
        self,
        predictions: list[str],
        references: list[str],
        task_type: str,
    ) -> dict[str, float]:
        """Compute task-appropriate metrics."""
        ...
    
    # --- Core metrics ---
    
    def accuracy(self, preds: list[str], refs: list[str]) -> float:
        """Exact match accuracy for MCQ/Bool tasks."""
        ...
    
    def rouge_l(self, preds: list[str], refs: list[str]) -> float:
        """ROUGE-L F-measure for text generation (L1)."""
        ...
    
    def triple_f1(self, preds: list[list[tuple]], refs: list[list[tuple]]) -> dict:
        """Order-sensitive Triple-F1 for L2/L3/L4."""
        ...
    
    def tuple_f1(self, preds: list[list[tuple]], refs: list[list[tuple]]) -> dict:
        """Order-insensitive Tuple-F1 for L5 (ontology alignment)."""
        ...
    
    # --- Prediction extraction ---
    
    def extract_prediction(self, raw: str, task_type: str) -> str | list[tuple]:
        """Parse model output to structured prediction.
        MCQ → letter, Bool → true/false, Generation → triples/text."""
        ...
    
    def _parse_triples(self, raw: str) -> list[tuple]:
        """Parse (s, p, o) triples from raw text, handling <ans> tags."""
        ...
```

**Critical detail:** We must use the same metric implementations as OntoURL to ensure
fair comparison. The order-sensitive Triple-F1 counts matches at the same position only.

---

### Phase 4: Benchmark Strategy Adapters (2–3 days)

#### 4.1 Strategy Definitions

Each strategy wraps a different approach to answering OntoURL questions:

```python
class OntoURLStrategy(ABC):
    """Base class for OntoURL benchmark strategies."""
    
    @abstractmethod
    def answer(self, example: dict, task_type: str, split_id: str) -> str:
        """Generate answer for a single OntoURL example."""
        ...

class VanillaStrategy(OntoURLStrategy):
    """Direct prompt → answer. Reproduces OntoURL baseline."""
    ...

class ChainOfThoughtStrategy(OntoURLStrategy):
    """CoT reasoning before answering. Compares to OntoURL's CoT experiments."""
    ...

class OntologyEngineerStrategy(OntoURLStrategy):
    """Role-play as ontology engineer with structured reasoning.
    Only for Learning tasks (L1–L5)."""
    ...

class MultiTurnStrategy(OntoURLStrategy):
    """Multi-turn refinement: analyze → draft → critique → final answer.
    Only for Learning tasks (L2–L4)."""
    
    def answer(self, example, task_type, split_id):
        # Turn 1: Analyze the ontology structure
        analysis = self.llm.generate_multi_turn([
            {"role": "system", "content": "You are an ontology engineer..."},
            {"role": "user", "content": f"Analyze this ontology structure: {example['question']}"}
        ])
        # Turn 2: Generate candidate triples
        draft = self.llm.generate_multi_turn([
            {"role": "system", "content": "You are an ontology engineer..."},
            {"role": "user", "content": f"Analyze: {example['question']}"},
            {"role": "assistant", "content": analysis},
            {"role": "user", "content": "Now generate the triples..."}
        ])
        # Turn 3: Self-critique and refine
        final = self.llm.generate_multi_turn([
            ...  # Previous context + critique prompt
        ])
        return final

class DebateStrategy(OntoURLStrategy):
    """Simulated multi-agent debate for Learning tasks.
    Proposer generates triples, Critic identifies issues, 
    Proposer revises. Maps to our dialectical debate approach."""
    
    def answer(self, example, task_type, split_id):
        # Agent 1: Proposer generates initial triples
        proposal = self.proposer.generate(...)
        # Agent 2: Critic reviews and identifies issues
        critique = self.critic.generate(...)
        # Agent 1: Proposer revises based on critique
        revised = self.proposer.generate(...)
        return revised
```

#### 4.2 Strategy Matrix

| Strategy | U1–U5 | R1–R5 | L1 | L2–L4 | L5 |
|---|---|---|---|---|---|
| `vanilla_zero` | Yes | Yes | Yes | Yes | Yes |
| `vanilla_2shot` | Yes | Yes | Yes | Yes | Yes |
| `vanilla_4shot` | Yes | Yes | Yes | Yes | Yes |
| `cot` | Yes | Yes | Yes | Yes | Yes |
| `engineer` | No | No | Yes | Yes | Yes |
| `multi_turn` | No | No | No | Yes | No |
| `debate` | No | No | No | Yes | No |

---

### Phase 5: Benchmark Runner Script (1–2 days)

#### 5.1 Main Runner (`scripts/run_ontourl_benchmark.py`)

```python
"""Run OntoURL benchmark with our models and strategies.

Usage:
    # Full benchmark (all 15 tasks, zero-shot, llama3.2:3b)
    python scripts/run_ontourl_benchmark.py --model llama3.2:3b

    # Learning tasks only, all strategies
    python scripts/run_ontourl_benchmark.py \
        --tasks L1 L2 L3 L4 L5 \
        --strategies vanilla_zero cot engineer multi_turn debate \
        --model qwen3-next:latest

    # Specific task with few-shot
    python scripts/run_ontourl_benchmark.py \
        --tasks L2 --strategies vanilla_2shot vanilla_4shot \
        --model llama3.2:3b

    # Resume interrupted run
    python scripts/run_ontourl_benchmark.py --resume

    # Max examples per split (for quick testing)
    python scripts/run_ontourl_benchmark.py --max-examples 50
"""
```

**CLI arguments:**

| Argument | Default | Description |
|---|---|---|
| `--model` | `llama3.2:3b` | Ollama model name |
| `--tasks` | all | Task filter: `U1 U2 ... R1 ... L1 L2 L3 L4 L5` |
| `--strategies` | `vanilla_zero` | Strategy list |
| `--shots` | `zero_shot` | Shot setting for vanilla strategies |
| `--max-examples` | `None` | Limit examples per split (for testing) |
| `--output-dir` | `results/ontourl/` | Output directory |
| `--resume` | `False` | Skip completed (split, strategy, model) runs |
| `--ollama-url` | env/config | Ollama endpoint |
| `--temperature` | `0.0` | Generation temperature |
| `--max-tokens` | `512` | Max tokens per response |
| `--wandb` | `True` | Log to W&B |
| `--langsmith` | env-based | Trace with LangSmith |

#### 5.2 Output Format

```
results/ontourl/
  {model_name}/
    {strategy}/
      {split_id}.jsonl            ← Per-example predictions
      summary.json                ← Aggregate metrics for this split
  comparison_table.csv            ← All models × strategies × tasks
  comparison_table.md             ← Markdown version
  figures/
    understanding_radar.png
    reasoning_radar.png
    learning_bar_chart.png
    vs_published_baselines.png    ← Compare against OntoURL paper results
```

**Per-example JSONL record:**
```json
{
  "identifier": "U1_001",
  "split": "1_1",
  "task": "U1_class_definition",
  "strategy": "vanilla_zero",
  "model": "llama3.2:3b",
  "question": "...",
  "options": "A) ... B) ... C) ... D) ...",
  "reference_answer": "B",
  "prediction": "B",
  "raw_response": "The answer is B because...",
  "correct": true,
  "latency_seconds": 1.23,
  "timestamp": "2025-02-11T12:00:00Z"
}
```

---

### Phase 6: Results Comparison & Reporting (1 day)

#### 6.1 Comparison Against Published Results

OntoURL published results for 16 models. We compare our Ollama-hosted models:

| Our Model | Comparable OntoURL Models | Size Group |
|---|---|---|
| `llama3.2:3b` | Qwen2.5-3B, Phi-4-4B | 3–4B |
| `nemotron-3-nano` | (not in OntoURL) | custom |
| `qwen3-next:latest` (79.7B) | Qwen2.5-72B, LLaMA3.3-70B | 70–72B |

#### 6.2 Comparison Table Format

```
| Task |  Metric  | Qwen2.5-3B | llama3.2:3b | llama3.2:3b | llama3.2:3b |
|      |          | (OntoURL)  |  vanilla_0  |     cot     |   engineer  |
|------|----------|------------|-------------|-------------|-------------|
| U1   | Accuracy |    77.8    |    ?.??     |    ?.??     |     N/A     |
| U2   | Accuracy |    86.3    |    ?.??     |    ?.??     |     N/A     |
| ...  |   ...    |    ...     |    ...      |    ...      |     ...     |
| L2   | Triple-F1|     0.1    |    ?.??     |    ?.??     |    ?.??     |
| L3   | Triple-F1|     0.0    |    ?.??     |    ?.??     |    ?.??     |
| L4   | Triple-F1|     0.2    |    ?.??     |    ?.??     |    ?.??     |
| L5   | Tuple-F1 |     6.7    |    ?.??     |    ?.??     |    ?.??     |
```

#### 6.3 Key Research Questions

1. **Do our models match published baselines?** (Vanilla zero-shot vs OntoURL paper)
2. **Does CoT improve performance?** (Especially on Reasoning tasks)
3. **Do agentic strategies improve Learning tasks?** (L2–L4 Triple-F1 improvements)
4. **How much does the debate approach help?** (Multi-agent critique on hierarchy/property construction)
5. **Is there a trade-off between latency and quality?** (Multi-turn strategies are slower)

---

## 5. Detailed File-by-File Implementation Checklist

### New Files

| # | File | Lines (est.) | Description |
|---|---|---|---|
| 1 | `src/ontology_hitl/benchmarking/ontourl/__init__.py` | 20 | Package init, public API |
| 2 | `src/ontology_hitl/benchmarking/ontourl/loader.py` | 150 | HuggingFace dataset loading + caching |
| 3 | `src/ontology_hitl/benchmarking/ontourl/prompts.py` | 350 | All prompt templates (vanilla + enhanced) |
| 4 | `src/ontology_hitl/benchmarking/ontourl/evaluator.py` | 300 | Metric computation (Accuracy, ROUGE-L, F1) |
| 5 | `src/ontology_hitl/benchmarking/ontourl/strategies.py` | 400 | 6 strategy implementations |
| 6 | `src/ontology_hitl/benchmarking/ontourl/reporter.py` | 250 | Results aggregation + comparison tables |
| 7 | `scripts/run_ontourl_benchmark.py` | 350 | CLI runner script |

### Modified Files

| # | File | Changes |
|---|---|---|
| 8 | `pyproject.toml` | Add `datasets`, `rouge-score`, `nltk` deps |
| 9 | `src/ontology_hitl/benchmarking/datasets.py` | Implement `load_ontourl()` |
| 10 | `src/ontology_hitl/benchmarking/metrics.py` | Wire up `score_ontourl_profile()` |
| 11 | `README.md` | Add OntoURL benchmark section |

**Total estimated:** ~1,800 lines of new code, ~100 lines of modifications.

---

## 6. Execution Plan

### Week 1: Core Infrastructure

| Day | Task | Deliverable |
|---|---|---|
| 1 | Create branch, add deps, implement loader | Dataset loads successfully |
| 2 | Implement prompts + vanilla strategy | Can generate answers for all 15 tasks |
| 3 | Implement evaluator (all 4 metric types) | Metrics match OntoURL's implementation |
| 4 | Implement runner script + output format | End-to-end run on 1 task works |
| 5 | Run full vanilla benchmark (llama3.2:3b) | Baseline numbers for comparison |

### Week 2: Advanced Strategies + Reporting

| Day | Task | Deliverable |
|---|---|---|
| 6 | Implement CoT + engineer strategies | CoT results for all tasks |
| 7 | Implement multi-turn + debate strategies | Agentic results for L2–L4 |
| 8 | Run full benchmark (qwen3-next) | Large model results |
| 9 | Implement reporter + comparison tables | Publication-ready tables |
| 10 | Analysis, write-up, merge to main | Final results document |

---

## 7. Technical Considerations

### 7.1 Ollama vs vLLM Differences

| Aspect | OntoURL (vLLM) | Our Setup (Ollama) |
|---|---|---|
| Batching | Parallel batch inference | Sequential (one at a time) |
| Speed | Fast (GPU-native batching) | Slower (~2-5x per example) |
| API | `LLM.generate(prompts)` | `POST /api/generate` (streaming) |
| Quantization | Full precision | Ollama's GGUF quantization |
| Models | HuggingFace model IDs | Ollama model tags |

**Mitigation:** 
- Use response caching (SHA-256 hash → disk) to avoid re-computation
- Focus intensive runs on Learning tasks (smaller splits: 256–2,936 examples)
- For Understanding/Reasoning (larger splits: 3,793–9,201), use `--max-examples 500` initially

### 7.2 Time Estimates

| Task Group | Examples | Time/example (3B est.) | Total |
|---|---|---|---|
| U1–U5 (MCQ) | 24,816 | ~1s | ~7h |
| R1–R4 (MCQ) | 25,474 | ~1s | ~7h |
| R5 (T/F) | 882 | ~1s | ~15min |
| L1 (text gen) | 2,936 | ~3s | ~2.5h |
| L2–L4 (triple gen) | 1,851 | ~5s | ~2.5h |
| L5 (tuple gen) | 1,149 | ~5s | ~1.5h |
| **Total (vanilla zero)** | **57,108** | — | **~21h** |

For qwen3-next (79.7B), multiply by ~3–5x → **~60–100h** for full benchmark.

**Recommendation:** Start with Learning tasks only for advanced strategies:
- L2–L4 = 1,851 examples × 6 strategies ≈ 11,106 calls → ~15h for 3B, ~2 days for 79.7B

### 7.3 No RAG Constraint

OntoURL tests LLMs' parametric knowledge of ontologies. Our system normally uses
RAG (document retrieval) for ontology extension. For fair comparison:

- **Vanilla/CoT strategies:** No RAG, pure LLM knowledge
- **Agentic strategies:** Multi-turn prompting without external retrieval
- **Future work:** If we find domain documents for OntoURL's 8 domains (healthcare,
  geography, ecology, finance, transport, food, cultural heritage, general), we
  could add a RAG-enhanced strategy as a bonus comparison

### 7.4 Model Mapping

Our Ollama models map to OntoURL's published baselines:

```
llama3.2:3b      →  Compare with Qwen2.5-3B (77.8% U1, 0.1% L2)
                     and Phi-4-4B (77.5% U1, 0.1% L2)
                     
qwen3-next:latest → Compare with Qwen2.5-72B (89.1% U1, 0.1% L2)
  (79.7B)            and LLaMA3.3-70B (88.0% U1, 0.1% L2)
```

Note: Learning tasks (L2–L5) show very low scores across ALL models in OntoURL
(typically 0.0–1.6% Triple-F1). This is the gap our methods aim to address.

---

## 8. Success Criteria

| Criterion | Target |
|---|---|
| Vanilla baseline reproduces OntoURL results | Within ±5% of published numbers for comparable model |
| All 15 tasks runnable | End-to-end pipeline works for every split |
| Learning tasks show improvement | At least 1 strategy beats vanilla on L2–L4 Triple-F1 by >2% |
| Results are reproducible | Caching + fixed seeds ensure deterministic runs |
| Comparison table is publication-ready | Markdown + CSV output with proper formatting |
| W&B + LangSmith tracking | All runs logged for experiment management |

---

## 9. References

1. Zhang, X., Lai, H., Meng, Q., & Bos, J. (2025). OntoURL: A Benchmark for Evaluating Large Language Models on Symbolic Ontological Understanding, Reasoning and Learning. *arXiv:2505.11031*
2. OntoURL GitHub: https://github.com/LastDance500/OntoURL
3. OntoURL Dataset: https://huggingface.co/datasets/XiaoZhang98/OntoURL
4. OntoURL Construction Code: https://github.com/LastDance500/Bench_Construct

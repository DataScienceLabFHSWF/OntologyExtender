# Key Papers for OntologyExtender

Quick-reference summaries of the most important papers, what they found, and why our approach addresses their gaps.

---

## 1. LLM4ACOE — Autonomous Multi-Agent Ontology Extension
**Soularidis, Doumanas & Kotis (2025)** · Knowledge Engineering Review 40
[Paper](https://www.cambridge.org/core/journals/knowledge-engineering-review/article/automating-agentic-collaborative-ontology-engineering-with-roleplaying-simulation-of-llmpowered-agents-and-rag-technology) · [Code](https://github.com/AndreasSoularidis/LLM-based-OE-Framework-LC3)

**What they did:** 3 LLM agents (Engineer, Expert, Worker) autonomously extend an ontology from documents using RAG. Fully automated — no human in the loop.

**Key results:** 78% CQ coverage, but no human validation gate. Extensions are plausible but may contain hallucinated concepts. Flat hierarchies with limited relational depth.

**Implication for us:** Shows multi-agent ontology extension works in principle, but without human oversight the output is unreliable. We add structured HITL review + debate strategies to force deeper reasoning.

---

## 2. Agent-OM — Multi-Agent Ontology Matching
**Qiang, Wang & Taylor (2024)** · VLDB 18(3)
[Paper](https://arxiv.org/abs/2312.00326) · [Code](https://github.com/qzc438/ontology-llm)

**What they did:** 2-agent system (Retrieval + Matching) for ontology alignment using PostgreSQL + pgvector. Chain-of-thought + tool-calling for matching operations.

**Key results:** 83%+ Hits@1 on OAEI benchmarks. Demonstrates agent coordination for ontology tasks at scale.

**Implication for us:** Validates the multi-agent architecture pattern for ontology tasks. Agent-OM does matching (aligning existing ontologies); we do extension (adding new concepts). Different task, same proven architecture.

---

## 3. Lippolis et al. — Ontology Generation with LLMs
**Lippolis, Saeedizade, Keskisärkkä et al. (2025)** · arXiv:2503.05388
[Paper](https://arxiv.org/abs/2503.05388)

**What they did:** Tested GPT-4, o1-preview, and Llama-3.1-405B on generating ontologies from competency questions. Two prompting techniques: Memoryless CQbyCQ (minimal context) and Ontogenia (metacognitive prompting + design patterns). Evaluated on 10 ontologies, 100 CQs, 29 user stories.

**Key results:**
- All LLMs generate 10–60% superfluous elements (classes/properties nobody asked for)
- Wrong domain/range axioms are the most common structural pitfall
- Reducing input context by ~60% (Memoryless CQbyCQ) actually *improves* output quality
- o1-preview + Ontogenia = best combination (100% CQ modelling on some domains)
- LLMs surpass first-attempt student submissions but match revised ones

**Implication for us:** This is the strongest evidence for our design. Our Moderator's complexity budget (≤20 elements/phase) directly prevents superfluous generation. The Critic agent performs structural review analogous to OOPS! scanning. Focused per-phase context mirrors the Memoryless CQbyCQ finding that less context = better output.

---

## 4. TamingHallucinations — Semantic Matching for Evaluation
**Fathallah, Staab & Algergawy (2025)** · CEUR-WS
[Code](https://github.com/NadeenAhmad/TamingHallucinations)

**What they did:** Automated evaluation pipeline comparing LLM-generated ontologies against expert references. Uses transformer embeddings (MiniLM) to match concepts (threshold ≥ 0.55) and triples (threshold ≥ 0.50). Cumulative multi-reference evaluation.

**Key results:** LLMs achieve high concept overlap but significantly lower triple-level alignment. They get the *names* right but the *relationships* wrong.

**Implication for us:** We've integrated their semantic matching approach into our benchmarking framework. This gives us an automated, reproducible way to measure hallucination rates without manual comparison.

---

## 5. OntoURL — Comprehensive LLM Ontology Benchmark
**Zhang, Lai, Meng & Bos (2025)** · arXiv:2505.11031
[Paper](https://arxiv.org/abs/2505.11031) · [Dataset (58K questions)](https://huggingface.co/datasets/XiaoZhang98/OntoURL)

**What they did:** Created the largest ontology benchmark: 58,981 questions across 40 ontologies, 8 domains, 15 tasks at 3 capability levels (Understanding, Reasoning, Learning). Tested 20 LLMs.

**Key results:**
- LLMs are strong at Understanding (recalling facts), weak at Reasoning (logical inference) and Learning (generating new structures)
- Best models: Qwen2.5-72B, LLaMA3.3-70B
- Few-shot prompting helps Reasoning most (+5–10%)

**Implication for us:** Confirms that single-LLM approaches hit a ceiling on reasoning tasks. Our multi-agent debate forces reasoning through structured disagreement — the Dialectical strategy makes agents defend opposing positions, which is exactly the kind of pressure that improves reasoning scores.

---

## 6. OWLUnit — Ontology Unit Testing
**Asprino (2024)**
[Code](https://github.com/luigi-asprino/owl-unit)

**What they did:** 4-type unit testing framework for ontologies: annotation completeness (SHACL), CQ verification (SPARQL), inference consistency (HermiT), and error provocation (inject bad data, verify rejection).

**Implication for us:** We use OWLUnit-style testing as part of our evaluation pipeline. After each HITL iteration, we can automatically verify that the extended ontology still passes all tests — catching regressions before they accumulate.

---

## 7. Plu et al. — User-Centered Ontology Evaluation
**Plu et al. (2024)** · ISWC 2024
[Code](https://github.com/jplu/ontology-benchmark)

**What they did:** Combined quantitative metrics (structural comparison against reference) with qualitative user assessments across 4 domains. Tested Claude 3.5 Sonnet, GPT-4o, GPT-4o-mini.

**Key results:** LLM-generated ontologies are perceived as overly broad, flat, and under-hierarchized. Users want more intermediate abstraction layers.

**Implication for us:** Our 7-phase Ont-101 pipeline explicitly generates hierarchy in Phase 4 (Hierarchy) and refines it in Phase 5 (Properties). The Dialectical debate strategy in these phases forces agents to argue about placement depth rather than defaulting to flat structures.

---

## 8. Li, Poveda & Garijo — Systematic Literature Review
**Li, Poveda & Garijo (2025)** · Semantic Web Journal
[Paper](https://www.semantic-web-journal.net/content/large-language-models-ontology-engineering-systematic-literature-review-0)

**What they did:** Reviewed 30+ studies on LLMs in ontology engineering. Covered the full lifecycle: requirements, conceptualization, formalization, evaluation, maintenance.

**Key results:** LLMs are effective at bootstrapping but consistently fail at axiom correctness, hierarchy depth, and relation precision without expert oversight. No fully automatic system produces publication-quality ontologies.

**Implication for us:** This review is the meta-evidence for our entire approach. Every failure mode they identify — shallow hierarchies, wrong axioms, missing relations — is addressed by a specific component in our system (debate strategies, Moderator grounding, HITL gates).

---

## Why Our Approach Works

| Known LLM Failure | Evidence | Our Solution |
|---|---|---|
| **Superfluous elements** (10–60%) | Lippolis et al., 2025 | Moderator complexity budget (≤20 elements/phase) + Critic review |
| **Flat hierarchies** | Plu et al., 2024 | Dialectical debate in hierarchy phase forces depth |
| **Wrong relationships** | Fathallah et al., 2025 | Triple-level semantic matching catches errors |
| **Weak reasoning** | OntoURL (Zhang et al.) | Multi-agent debate = external reasoning pressure |
| **No self-correction** | Li et al. SLR, 2025 | Iterative HITL loop with accept/reject/revise |
| **Context overload** | Lippolis et al. (CQbyCQ) | Per-phase focused context, not full pipeline history |
| **No human oversight** | LLM4ACOE (78% CQ cov.) | Structured HITL with escalation thresholds |

**Bottom line:** Every recent paper confirms that LLMs alone cannot reliably engineer ontologies. The gap is always the same: reasoning depth, structural quality, and validation. Our system fills exactly this gap by combining multi-agent debate (for reasoning) with structured HITL (for validation) and grounded context (for accuracy).

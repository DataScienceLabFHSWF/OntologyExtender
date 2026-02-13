# Related Work

## Ontology Learning and Automatic Ontology Construction

Ontology learning is a long-established research area focused on the automatic
or semi-automatic construction of ontologies from text, data, or existing
knowledge sources. Early surveys already observed that while term extraction
and lightweight taxonomies can be derived automatically, relations, axioms,
and deep hierarchies remain difficult to infer without human involvement.

Shamsfard and Barforoush provide one of the foundational surveys, identifying
ontology learning as a multi-layered process (lexical, syntactic, semantic,
and pragmatic), and concluding that full automation is infeasible for
expressive ontologies without expert supervision.
https://www.sciencedirect.com/science/article/pii/S1574013720304391

Subsequent surveys and reviews reinforce this conclusion. Ding et al. and
later systematic reviews note that most successful ontology learning systems
are semi-automatic, relying on seed ontologies, background knowledge, or
iterative expert validation to ensure correctness and consistency.
https://academic.oup.com/database/article/doi/10.1093/database/bay101/5116160

These findings established an early consensus: automation can assist ontology
engineers, but cannot replace them.

---

## Human-in-the-Loop Ontology Engineering

Human-in-the-loop (HITL) approaches explicitly integrate expert judgment into
ontology construction, extension, and evaluation workflows. Rather than
treating human validation as an afterthought, HITL methodologies formalize
it as a core design principle.

Tsaneva and Sabou investigate HITL ontology curation and show that task
design, contributor qualification, and representation of axioms significantly
affect the quality of human validation results. Their work demonstrates that
structured HITL processes outperform both unstructured crowd evaluation and
fully automatic methods.
https://research.wu.ac.at/en/publications/enhancing-human-in-the-loop-ontology-curation-results-through-tas

The HERO methodology further formalizes human-centric ontology evaluation,
defining preparatory and execution phases supported by tooling. HERO
demonstrates substantial reductions in expert workload while maintaining
semantic quality, reinforcing the value of structured HITL pipelines.
https://link.springer.com/chapter/10.1007/978-3-031-17105-5_14

Other applied systems, such as OntoHuman, integrate user feedback directly
into ontology extension during information extraction tasks, highlighting
the practical viability of interactive ontology refinement.
https://elib.dlr.de/189331/2/803_OntoHuman.pdf

---

## Large Language Models for Ontology Engineering

With the rise of Large Language Models (LLMs), recent work explores their
use in ontology engineering tasks such as concept suggestion, taxonomy
induction, relation extraction, and alignment.

Shimizu and Hitzler show that LLMs can accelerate knowledge graph and
ontology engineering across multiple tasks, but emphasize that human
verification is still required to ensure correctness and logical consistency.
https://arxiv.org/abs/2411.09601

A comprehensive systematic literature review by Li, Poveda, and Garijo
analyzes over 30 studies on LLMs in ontology engineering. The review
concludes that while LLMs are effective at bootstrapping ontology artifacts,
they consistently struggle with axiom correctness, hierarchy depth, and
relation precision without expert oversight.
https://www.semantic-web-journal.net/content/large-language-models-ontology-engineering-systematic-literature-review-0

Domain-specific studies reinforce this conclusion. For example, ontology
construction for Parkinson's disease monitoring shows that initial
LLM-generated ontologies are incomplete and inconsistent, and only become
usable after iterative human–LLM collaboration.
https://arxiv.org/abs/2512.14288

---

## Evaluation of LLM-Generated Ontologies

Recent empirical evaluations directly assess the quality of LLM-generated
ontologies against human-crafted references.

Zhao et al. evaluate LLM-generated ontologies using semantic matching
techniques and find high concept overlap but significantly lower triple-level
alignment, indicating that LLMs struggle to commit to correct relationships
even when concept labels are accurate.
https://ceur-ws.org/Vol-3953/362.pdf

Plu et al. conduct a user-centered evaluation and report that LLM-generated
ontologies are often perceived as overly broad, flat, and under-hierarchized,
with insufficient intermediate abstractions.
https://ceur-ws.org/Vol-3979/paper2.pdf

Lippolis et al. perform the most rigorous multi-dimensional evaluation to
date, testing GPT-4, o1-preview, and Llama-3.1-405B with two prompting
techniques (Memoryless CQbyCQ and Ontogenia) on a benchmark of 10
ontologies. Their four evaluation criteria — OOPS! pitfall scanning, CQ
modelling proportion, superfluous element rates, and expert qualitative
analysis — reveal that all LLMs generate significant superfluous elements
(10–60%) and struggle with domain/range axioms.
https://arxiv.org/abs/2503.05388

These studies converge on a shared diagnosis: LLMs optimize for surface
plausibility rather than ontological commitment, leading to shallow
structures and weak relational modeling.

---

## Semi-Automatic and Iterative Ontology Extension Pipelines

Several recent systems propose iterative or pipeline-based approaches
combining automation with human control.

NeOn-GPT demonstrates that iterative ontology extension with reuse analysis
and human validation produces higher-quality ontologies than one-shot
generation.
https://link.springer.com/chapter/10.1007/978-3-031-17105-5_16

Garcia-Fernández et al. show that LLMs can inspire ontology extensions and
assist verification against competency questions, but require human decisions
for concept definitions, placement, and relation modeling.
https://ceur-ws.org/Vol-4020/Paper_ID_8.pdf

End-to-end ontology learning approaches using LLMs and structural
regularizers further demonstrate improvements over subtask-based methods,
yet still rely on expert evaluation for final acceptance.
https://arxiv.org/abs/2410.23584

---

## Multi-Agent and Collaborative LLM-Based Ontology Engineering

A recent line of work investigates multi-agent LLM architectures that
simulate collaborative ontology engineering processes.

### LLM4ACOE (Soularidis et al.)

LLM4ACOE is the most closely related system to ours. It automates
Collaborative Ontology Engineering (COE) by simulating the HCOME
methodology with three LLM-powered agents playing distinct roles:
Knowledge Engineer, Domain Expert, and Knowledge Worker. The system
uses RAG with three specialized retrievers (domain documents, OWL
documentation, and ReAct-style reasoning examples) to augment LLM
responses.
https://github.com/AndreasSoularidis/LLM-based-OE-Framework-LC3

**Architecture:** LLM4ACOE operates in a fixed three-round pipeline:
(1) generate ontology from domain data, (2) refine using OWL axiom
guidance, (3) apply ReAct-style structural improvement. The three
agent roles are simulated within a single LLM call using role-playing
prompts, with LangChain orchestrating the RAG retrieval chains.

**Key limitations vs. our system:**

| Dimension | LLM4ACOE | Our System |
|-----------|----------|-----------|
| **Agent independence** | Single LLM simulating 3 roles in one prompt | Separate agent invocations with independent state |
| **Quality control** | No explicit review or critique step | Dedicated review agent + moderator budget control |
| **Models** | Cloud APIs only (GPT-4o, Claude, Gemini) | Local open models via Ollama — reproducible, private |
| **Domain scope** | Hardcoded to Search and Rescue (SAR) | Any domain with seed ontology + documents |
| **Iteration** | Fixed 3 rounds, no convergence detection | Configurable N iterations with convergence check |
| **HITL** | No human oversight loop | Structured HITL with proposal review + expert feedback |
| **Formal evaluation** | Manual expert review on SAR only | Automated 6-dimension scoring + OntoURL benchmark |

**Significance:** LLM4ACOE demonstrates that role-playing multi-agent
simulation is a viable approach to ontology engineering. However, its
design choices — simulated (not independent) agents, no structured
review, cloud-only models, single-domain evaluation — limit both its
reproducibility and generalizability. Our system addresses each of
these limitations while preserving the core insight that multi-role
collaboration improves ontological output.

We plan to reproduce LLM4ACOE's HCOME three-role approach as a benchmark
strategy on the OntoURL evaluation suite (see BENCHMARKING_RATIONALE.md),
enabling a controlled comparison that holds the LLM and evaluation
metrics constant while varying only the agentic architecture.

---

## OntoURL: Standardized Ontology Capability Benchmark

OntoURL provides a comprehensive evaluation framework with 15 tasks
spanning three cognitive levels (Understanding, Reasoning, Learning)
and ~58,000 examples drawn from 40 real-world ontologies. Published
baselines exist for Qwen2.5-3B, Qwen2.5-72B, and LLaMA3.3-70B.

We use OntoURL as our primary capability benchmark because it enables:
(1) isolation of agentic strategy value by holding the knowledge source
constant (parametric only), (2) direct comparison against published
baselines under identical conditions, and (3) fine-grained analysis of
where multi-agent workflows add the most value (Understanding vs.
Reasoning vs. Learning tasks).

See [BENCHMARKING_RATIONALE.md](BENCHMARKING_RATIONALE.md) for our
full evaluation methodology and three-layer comparison strategy.

---

## Summary and Positioning

Across ontology learning, HITL systems, multi-agent approaches, and
recent LLM-based evaluations, the literature consistently shows that:

- **Fully automatic ontology construction remains unreliable**, particularly
  for relations and hierarchy depth.
- **LLMs are effective as assistants**, not autonomous ontology engineers.
- **Structured human-in-the-loop workflows outperform single-shot
  generation** in both quality and usability.
- **Multi-agent role simulation** (LLM4ACOE) improves over single-pass
  generation, but lacks independent critique and structured review.
- **Recent evaluations confirm** that epistemic pressure and iterative
  validation are necessary to mitigate LLM limitations.
- **Standardized benchmarks** (OntoURL) enable rigorous, reproducible
  comparison of ontology engineering approaches across models and methods.

These findings motivate agentic, multi-role, debate-driven ontology
engineering pipelines that embed grounding, critique, and human oversight
as first-class design elements — and demand formal benchmarking to
substantiate improvement claims.

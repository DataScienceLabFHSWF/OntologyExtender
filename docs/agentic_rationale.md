# Why an Agentic Approach to Ontology Engineering Is Reasonable

This document explains **why our multi‑agent (agentic) ontology engineering approach is justified**, how it directly addresses known limitations of Large Language Models (LLMs), and where its limits still lie. It is intended for **internal validation**, **design justification**, and **use in academic writing**.

The argument is grounded in recent peer‑reviewed evaluations of LLM‑generated ontologies, most notably:

* Zhao et al., *Evaluating LLM‑Generated Ontologies via Semantic Matching* (ESWC 2025)
* Plu et al., *User‑Centered Evaluation of LLM‑Generated Ontologies* (2025)
* Supporting findings from Fathallah et al., *NeOn‑GPT* (EKAW 2024)

---

## 1. What Recent Papers Actually Show

Across multiple independent evaluations, the literature converges on a **consistent diagnosis** of LLM‑based ontology generation.

### 1.1 Concept Labels Are Easy; Ontological Structure Is Not

Zhao et al. demonstrate that LLM‑generated ontologies achieve **high concept overlap** with reference ontologies (often >90% when multiple references are combined), but **much lower alignment on triples (subject–predicate–object relations)**.

> *LLMs can extract and generate entity‑level knowledge effectively, but struggle to formalize structured semantic relationships.*
> — Zhao et al., ESWC 2025

This shows that the core failure is **not vocabulary**, but **commitment to relationships**.

---

### 1.2 LLM Ontologies Are Broad, Flat, and Under‑Hierarchized

Plu et al. report that users consistently perceive LLM‑generated ontologies as:

* Too many top‑level classes
* Insufficient hierarchy depth
* Missing intermediate abstractions
* Poorly grouped concepts

> *The ontology remains overly simplistic and flat, with many top‑level classes and insufficient hierarchical depth.*
> — Plu et al., 2025

This flatness is not accidental — it reflects LLM optimization for **surface plausibility**, not ontological differentiation.

---

### 1.3 Implicit Conclusion of the Literature

Although rarely stated explicitly, the papers collectively imply:

> **LLMs do not fail because they lack domain knowledge. They fail because they lack epistemic pressure.**

There is no cost to:

* Being vague
* Omitting relations
* Avoiding hard modeling decisions

---

## 2. Why a Purely Single‑Shot LLM Approach Fails

Ontology engineering is fundamentally a **commitment‑making activity**:

* Declaring subclasses
* Asserting domain/range
* Choosing between alternative conceptualizations

LLMs are statistically optimized to **hedge rather than commit**. This directly explains:

* Low triple alignment (Zhao et al.)
* Shallow hierarchies (Plu et al.)

As long as ontology generation is treated as a *single‑agent, single‑pass* task, these failures are structural and unavoidable.

---

## 3. Core Design Hypothesis of Our Agentic Approach

Our system is based on the following hypothesis:

> **LLMs can contribute to ontology engineering if they are embedded in an institutional process that simulates epistemic pressure.**

Rather than treating the LLM as an oracle, we treat it as a **fallible participant** in a structured workflow resembling scientific practice.

---

## 4. How the Agentic Architecture Addresses Known Failure Modes

### 4.1 Weak or Missing Relations → Dialectical Commitment

**Failure observed in literature:**

* Low triple alignment
* Missing or underspecified relations

**Our mitigation:**

* **OntologyEngineer** must explicitly propose relations
* **DomainExpert** demands documentary grounding
* **Critic** challenges coherence, necessity, and consistency
* **Competency Questions (CQs)** ensure relations are functionally justified

Relations that do not survive this process are revised or removed.

This directly targets the core issue identified by Zhao et al.

---

### 4.2 Flat Hierarchies → Structural Critique and Synthesis

**Failure observed in literature:**

* Overly flat class structures
* Missing intermediate abstractions

**Our mitigation:**

* Critic explicitly evaluates hierarchy depth
* Flags excessive top‑level classes
* Encourages abstraction over enumeration
* Iterative synthesis produces intermediate concepts

This operationalizes Plu et al.’s recommendation to group related classes under meaningful parent categories.

---

### 4.3 Hallucination → Grounding and Falsifiability

**Failure observed in literature:**

* Plausible but unjustified concepts

**Our mitigation:**

* Every class and relation must:

  * Be grounded in documents **or**
  * Serve at least one Competency Question

Ungrounded elements are treated as hypotheses and rejected if unsupported.

---

### 4.4 Drift and Overgrowth → Complexity and Reuse Controls

**Failure observed in practice:**

* Ontology sprawl
* Incoherent growth over iterations

**Our mitigation:**

* Complexity budgets per iteration
* Mandatory reuse analysis against existing ontologies
* Connectivity metrics to prevent isolated branches

This aligns with findings from NeOn‑GPT, which show reuse and iteration outperform one‑shot generation.

---

## 5. Role of Human‑in‑the‑Loop (HITL)

The literature consistently emphasizes the necessity of expert oversight.

Zhao et al. explicitly note that unmatched or ambiguous concepts require **domain expert judgment**.

Our system formalizes this by:

* Escalating unresolved disputes to humans
* Treating expert review as a **designed phase**, not an afterthought

The goal is not to remove experts, but to **multiply their effectiveness**.

---

## 6. Known Limitations (Honest Assessment)

Despite its strengths, our approach does not eliminate all risks.

### 6.1 Shared LLM Biases

All agents may share training priors, risking collective blind spots.

### 6.2 Incomplete Detection of Missing Relations

We currently detect *invalid* relations better than *absent but necessary* ones — a gap also noted in the literature.

### 6.3 Human Bottleneck Remains

The system reduces, but does not eliminate, the need for expert judgment.

This aligns with empirical findings that ontology engineering remains a socio‑technical process.

---

## 7. Final Position

Based on current evidence:

* **The failure modes of LLM ontology generation are well‑understood**
* **Our agentic approach directly targets those failure modes**
* **The design is consistent with empirical findings and theoretical ontology practice**

We do not claim that the system produces perfect ontologies autonomously.

We claim — and the literature supports — that:

> **Embedding LLMs in a structured, adversarial, grounded, and human‑supervised process produces qualitatively better ontologies than single‑agent generation.**

This makes the agentic approach not only reasonable, but necessary.

# Philosophical Foundations for Multi-Agent Ontology Construction

> *"The owl of Minerva spreads its wings only with the falling of the dusk."*
> — Hegel, *Philosophy of Right* (1820), Preface

This document provides the epistemological and methodological grounding
for the multi-agent ontology extension system. It connects philosophical
traditions to concrete design decisions, documents where and why LLMs are
used, addresses the risk of **runaway ontologies**, defines agent roles
precisely, and proposes performance measurement frameworks.

---

## Table of Contents

1. [From Philosophy to System Design](#1-from-philosophy-to-system-design)
2. [Knowledge Discovery Methods from Philosophy](#2-knowledge-discovery-methods-from-philosophy)
3. [Debate Strategies: Philosophical Derivation](#3-debate-strategies-philosophical-derivation)
4. [Agent Roles and Epistemic Identities](#4-agent-roles-and-epistemic-identities)
5. [The Moderator: Orchestrating Discourse](#5-the-moderator-orchestrating-discourse)
6. [Where LLMs Are Used](#6-where-llms-are-used)
7. [Emergent Behaviour and Runaway Ontologies](#7-emergent-behaviour-and-runaway-ontologies)
8. [Performance Measurement](#8-performance-measurement)
9. [System Prompts: From Philosophy to Instructions](#9-system-prompts-from-philosophy-to-instructions)
10. [Sources](#10-sources)

---

## 1. From Philosophy to System Design

### 1.1 The Core Problem

Ontology construction is fundamentally an *epistemic* activity: it
involves deciding what exists (ontological commitment), how we know it
(epistemological justification), and how to represent it (formal
encoding). These are not merely technical questions — they carry
philosophical commitments whether we acknowledge them or not.

When we automate parts of this process with LLMs, we must be explicit
about *what kind of knowledge* the system produces, *how it is
justified*, and *where it can go wrong*.

### 1.2 Methodological Pluralism as Architectural Principle

**Source**: Feyerabend (1975), Kellert, Longino & Waters (2006)

Feyerabend's *Against Method* argues that no single epistemic strategy
has universal validity. Kellert et al. extend this into a mature
"scientific pluralism": multiple models, methods, and perspectives may
be needed to understand complex phenomena, and the relationships between
them cannot always be reduced to a single framework.

**Design consequence**: The system does not privilege any single
knowledge source. Vector retrieval, symbolic reasoning, graph structure
analysis, LLM generation, and human judgement coexist as *partially
independent epistemic channels*. Their agreement strengthens
confidence; their disagreement signals genuine uncertainty, not error.

### 1.3 Ontologies as Productive Constraints

**Source**: Deleuze & Guattari (1980), Whitehead (1929)

Following process philosophy, we treat ontologies not as static mirrors
of reality but as *productive constraints* — structures that enable
certain operations (SPARQL queries, SHACL validation, knowledge graph
population) while intentionally leaving other aspects unspecified.

An ontology is not a complete model of the world. It is a *tool for
thinking* — a formalisation good enough to support the competency
questions its users actually need to answer.

**Design consequence**: The system aims for *adequacy relative to
competency questions*, not metaphysical completeness. This directly
prevents scope creep and runaway elaboration.

### 1.4 Dynamic Assemblages, Not Static Architectures

**Source**: Deleuze & Guattari (1980), Latour (2005)

The system is a *dynamic assemblage* (agencement) of loosely coupled
components: agents, ontologies, documents, prompts, constraints, and
human reviewers. Each is an *actant* (Latour 2005) whose agency is
constituted through relations with the others. No single component
controls the outcome; the knowledge graph emerges from the network of
interactions.

**Design consequence**: Components are replaceable. The LLM can be
swapped, agents can be added or reconfigured, debate strategies can
be changed — the architecture does not collapse because it depends on
*relations*, not *identities*.

---

## 2. Knowledge Discovery Methods from Philosophy

Beyond the debate strategies (Section 3), several philosophical
traditions inform how the system *discovers* knowledge to propose:

### 2.1 Peircean Abduction — Inference to the Best Explanation

**Source**: Peirce (1903), Lipton (2004)

The dominant reasoning mode in the system. Given:
- *Surprising fact*: gap entities that the ontology cannot represent
- *Hypothesis*: a proposed ontology extension
- *If the hypothesis were true*, the surprising fact would be expected

The OntologyEngineer reasons abductively: "What minimal extension to
the ontology would make these gaps *expected*?"

This distinguishes our approach from pure induction (generalise from
examples) or deduction (derive from axioms). Abduction generates
*explanatory hypotheses* that must then survive critique.

**Where used**: Gap analysis → proposal generation (Phases 3–5);
instance validation revealing missing concepts (Phase 7).

### 2.2 Hermeneutic Circle — Interpretation as Knowledge Production

**Source**: Gadamer (1960), Ricoeur (1981)

The DomainExpert performs hermeneutic work: understanding parts (terms,
sentences) through the whole (domain context), and understanding the
whole through the parts. This is not a vicious circle but a *productive
spiral* — each pass deepens understanding.

Ricoeur's "hermeneutics of suspicion" adds a critical layer: texts do
not simply reveal meaning; they may conceal, distort, or assume. The
DomainExpert must read *against the grain* as well as with it.

**Where used**: Document context interpretation; term validation;
checking that formal definitions match *lived* domain usage.

### 2.3 Dialectical Materialism — Knowledge Through Contradiction

**Source**: Hegel (1807), Marx (1845), Bhaskar (1975)

Knowledge advances through the negation of existing claims. The
thesis→antithesis→synthesis pattern is not merely oppositional but
*sublative* (aufhebend): the synthesis preserves what was valid in
both positions while resolving their contradiction at a higher level.

Bhaskar's critical realism adds that the structures we model may be
*real but unobservable* — the ontology represents tendencies and
mechanisms, not merely observed regularities.

**Where used**: The Dialectical debate strategy (Section 3.1); the
Critic's role as productive negation.

### 2.4 Popperian Demarcation — Falsifiability as Quality Criterion

**Source**: Popper (1934/1959), Lakatos (1970)

A proposal is *meaningful* only if it is falsifiable — if there exists
an observation that could refute it. Applied to ontology:

- A class is falsifiable if we can specify instances that should NOT
  be members
- A property is falsifiable if we can identify values it should NOT accept
- A hierarchy is falsifiable if we can describe entities that would
  violate its structure

Lakatos refines this: we don't reject immediately on falsification but
track a *research programme's* progressive or degenerating nature. The
system tracks whether iterations are progressively extending coverage
or merely shifting problems around.

**Where used**: The Critic's epistemic stance; competency question
evaluation; iteration-over-iteration progress metrics.

### 2.5 Phenomenological Reduction — Bracketing Assumptions

**Source**: Husserl (1913), Heidegger (1927)

Husserl's *epoché* (bracketing) suspends natural assumptions to
examine phenomena as they appear. Applied to ontology engineering:
before categorising a domain entity, we should bracket our default
classifications and ask *how it actually appears in the documents*.

Heidegger's existential phenomenology adds that entities are
encountered *as equipment* — as things with purposes in practices.
An ontology class should reflect how practitioners *use* the thing,
not just what it abstractly *is*.

**Where used**: The DomainExpert's insistence on document evidence
over abstract reasoning; Phase 3 term enumeration.

### 2.6 Pragmatism — Truth as What Works

**Source**: James (1907), Dewey (1938), Rorty (1979)

For pragmatists, the value of a concept is measured by its practical
consequences. An ontology class is justified if it *enables useful
queries* and *supports practical decisions*. This aligns directly
with the competency question methodology.

Dewey's "inquiry" framework — the self-correcting process of
transforming an indeterminate situation into a determinate one —
maps onto the iterative loop of propose→critique→revise.

**Where used**: CQ-driven evaluation; the principle that every
ontology element must serve at least one competency question.

### 2.7 Wittgensteinian Language Games — Meaning as Use

**Source**: Wittgenstein (1953), Winch (1958)

The meaning of a term is its use in a language game. Domain terms
don't have fixed meanings; they acquire meaning through how they are
used in documents, conversations, and practices. The system must be
sensitive to *usage patterns*, not just dictionary definitions.

**Where used**: Term extraction from document context; synonym
detection; the DomainExpert's check that formal definitions match
*practitioner usage*.

### 2.8 Foucauldian Discourse Analysis — Power in Classification

**Source**: Foucault (1966/1970), Bowker & Star (1999)

Classification systems are never neutral. They embody assumptions,
foreground certain distinctions, and render others invisible. Bowker
and Star's *Sorting Things Out* demonstrates how ontological choices
have real consequences for what can and cannot be seen, queried, and
acted upon.

**Where used**: The Critic's attention to what is *excluded* by a
classification; the requirement to document out-of-scope decisions
explicitly (Phase 1); the concern that automated systems may
uncritically reproduce biases in training data.

---

## 3. Debate Strategies: Philosophical Derivation

Each debate strategy is derived from a specific philosophical tradition
about how knowledge is validated through discourse. The mapping is not
metaphorical — each strategy operationalises a *specific mechanism* from
its source tradition.

### 3.1 Dialectical Strategy (Hegel 1807)

| Phase | Philosophical Operation | System Operation |
|-------|------------------------|-----------------|
| Thesis | A definite claim is stated | Engineer proposes structured artefact |
| Antithesis | The claim is negated productively | Expert + Critic mount counter-positions |
| Synthesis | Contradiction is sublated (aufgehoben) | Engineer revises, preserving valid insights from both |
| Aufhebung check | Is the synthesis genuinely higher? | Reviewers evaluate whether contradictions are truly resolved |

**Key insight from Hegel**: The synthesis is not a *compromise* between
thesis and antithesis. It is a *qualitative advance* that preserves what
was valid in both while resolving their contradiction. If this is not
achieved, the tension is genuine and should be escalated.

**When to use**: Complex phases (hierarchy, properties) where competing
valid designs exist. The dialectical approach is most productive when
there are *genuinely opposing considerations* — e.g., granularity vs.
simplicity, domain accuracy vs. formal elegance.

### 3.2 Socratic Strategy (Plato, *Meno* / *Theaetetus*)

The Socratic elenchus proceeds by:
1. Eliciting a precise claim from the interlocutor
2. Examining it through targeted questioning across dimensions
3. Revealing hidden assumptions or contradictions (aporia)
4. Arriving at a more justified position — or honest puzzlement

**Five epistemic dimensions** cycle through across rounds:

| Dimension | Core Question | Philosophical Root |
|-----------|--------------|-------------------|
| Ontological | "What kind of thing *is* this?" | Aristotle, *Categories* |
| Epistemological | "How do we *know* this?" | Plato, *Theaetetus* |
| Pragmatic | "What is this *for*?" | Dewey, *Logic: The Theory of Inquiry* |
| Methodological | "Is this *well-constructed*?" | Noy & McGuinness, Ont-101 |
| Coherence | "Does this *fit* the whole?" | Quine, *Two Dogmas* |

**Key insight from Plato**: Aporia (productive puzzlement) is a valid
outcome. If the Socratic examination reveals that a question genuinely
cannot be resolved by the agents, this is not failure — it is honest
recognition of the limits of automated reasoning. Such cases become
HITL escalations.

**When to use**: Scope definition (Phase 1), term enumeration (Phase 3)
— phases where *what things are* matters more than *how to structure
them*.

### 3.3 Delphi Strategy (Dalkey & Helmer 1963)

The Delphi technique achieves convergence through:
1. Independent individual judgements (no anchoring)
2. Anonymous aggregation of opinions
3. Feedback of aggregate statistics
4. Iteration until convergence (≥80% agreement)

**What it prevents**:
- **Anchoring bias**: reviewers don't see each other's initial opinions
- **Bandwagon effect**: no social pressure toward premature consensus
- **Dominance effects**: no agent's "authority" overrides another

**Key insight from Dalkey & Helmer**: When experts disagree, it is
often because they attend to different aspects of the problem. Iterative
anonymous feedback allows each reviewer to learn from the *substance*
of other perspectives without being influenced by their *source*.

**When to use**: Property and facet definition (Phases 5–6), where
there are many independent decisions and anchoring on the first
reviewer's opinions would be harmful.

### 3.4 Abductive Strategy (Peirce 1903)

| Step | Peircean Operation | System Operation |
|------|-------------------|-----------------|
| 1 | Observe surprising fact | Identify gap entity / unmet CQ |
| 2 | Propose explanatory hypothesis | Propose ontology extension |
| 3 | Examine explanatory adequacy | Reviewers: does this *explain* the gap? |
| 4 | Compare alternative hypotheses | Reviewers: is there a *simpler* explanation? |
| 5 | Select most parsimonious | Select version that survives Ockham's razor |

**Key insight from Peirce**: Abduction generates *candidate hypotheses*,
not proven conclusions. The hypothesis must then survive deductive
testing (does it logically cover the CQs?) and inductive confirmation
(does it match document evidence?). This three-stage pattern
(abduction→deduction→induction) is the system's core reasoning cycle.

**When to use**: Gap-driven iteration; when the system discovers entities
or relations that the current ontology cannot represent.

### 3.5 Consensus Strategy (Habermas 1981)

Based on Habermas's discourse ethics and the ideal speech situation:
- All participants have equal standing
- Claims are accepted based on the *force of the better argument*
- No coercion, strategic manipulation, or appeal to authority
- Every participant can introduce or challenge any claim

**Key insight from Habermas**: Consensus achieved through genuine
discourse is *rationally motivated* — it reflects not mere agreement
but *warranted agreement*. If consensus cannot be reached, this signals
genuine underdetermination, not failure.

**When to use**: Default strategy; suitable for most phases. Especially
for reuse analysis (Phase 2) where balanced multi-perspective
evaluation is needed.

### 3.6 Deriving Strategies from Deleuze and Feyerabend

**Deleuze & Guattari** (1980) contribute not a debate strategy per se
but an *architectural principle*: the system is a **rhizomatic
assemblage** rather than a hierarchical command structure. Each
debate strategy is one *line of flight* among many; no strategy has
meta-theoretical priority over the others. The system can dynamically
select strategies based on context.

Concrete operational implications:
- **Deterritorialisation**: When a phase fails to converge, the system
  may *reterritorialise* on a different strategy rather than escalating
  immediately (strategy fallback).
- **Multiplicity**: The same proposal may be debated under multiple
  strategies in parallel, with results compared.
- **Becoming**: The system's behaviour is not predetermined but *emerges*
  from the interaction of components, strategies, and contexts.

**Feyerabend** (1975) contributes **epistemological anarchism** — the
principle that "anything goes" is the only methodological rule not
refuted by the history of science. For our system this means:

- **No strategy is always best**: Performance must be measured
  *contextually*, not absolutely (see Section 8).
- **Counter-induction is legitimate**: Deliberately proposing *against*
  existing consensus can reveal hidden assumptions. The Dialectical
  strategy's antithesis phase operationalises this.
- **Proliferation of alternatives**: When stuck, generate *more*
  hypotheses rather than refining a single one. This informs the
  Abductive strategy's comparison of alternative explanations.

---

## 4. Agent Roles and Epistemic Identities

### 4.1 OntologyEngineer — The Constructive Abducer

| Attribute | Specification |
|-----------|--------------|
| **Role** | Proposer — generates structured ontology artefacts |
| **Epistemic stance** | Constructive abduction (Peirce 1903) |
| **Philosophical identity** | The *researcher* who infers explanatory hypotheses |
| **Knowledge mode** | Inference to best explanation |
| **Quality criterion** | Explanatory adequacy + methodological compliance |
| **Failure mode** | Over-engineering; proposing structure beyond evidence |
| **Strengths** | Ont-101 methodology, structural patterns, systematic design |
| **Blind spots** | May privilege formal elegance over domain accuracy |
| **Relation to others** | Proposes → receives critique → revises |

**LLM usage**: Generates proposals (Phase 1–7), revises based on
feedback. Each proposal passes through the LLM once for generation
and once per revision round.

### 4.2 DomainExpert — The Hermeneutic Interpreter

| Attribute | Specification |
|-----------|--------------|
| **Role** | Reviewer — validates against document evidence |
| **Epistemic stance** | Hermeneutic grounding (Gadamer 1960) |
| **Philosophical identity** | The *practitioner* who reads through lived experience |
| **Knowledge mode** | Interpretation and evidence citation |
| **Quality criterion** | Domain accuracy + terminological faithfulness |
| **Failure mode** | Over-reliance on surface text; missing implicit knowledge |
| **Strengths** | Document grounding, terminology validation, completeness |
| **Blind spots** | May miss structural issues; limited to what documents say |
| **Relation to others** | Reviews proposals → provides evidence → flags gaps |

**LLM usage**: Reviews proposals against document context (provided in
prompt). One LLM call per review round.

### 4.3 Critic — The Critical Falsifier

| Attribute | Specification |
|-----------|--------------|
| **Role** | Reviewer — structural quality and consistency |
| **Epistemic stance** | Critical falsification (Popper 1934) |
| **Philosophical identity** | The *devil's advocate* who seeks refutation |
| **Knowledge mode** | Attempted falsification and structural analysis |
| **Quality criterion** | Falsifiability + structural soundness |
| **Failure mode** | Being too conservative; blocking valid innovation |
| **Strengths** | Consistency checking, redundancy detection, scope control |
| **Blind spots** | May reject novel but valid structures; lacks domain knowledge |
| **Relation to others** | Reviews proposals + expert feedback → provides verdict |

**LLM usage**: Reviews proposals and prior discussion. One LLM call per
review round; may include multi-turn context.

### 4.4 Moderator — The Discourse Facilitator (NEW)

| Attribute | Specification |
|-----------|--------------|
| **Role** | Orchestrator — selects strategy, manages flow, detects drift |
| **Epistemic stance** | Meta-procedural (Habermas 1981, Feyerabend 1975) |
| **Philosophical identity** | The *facilitator* who ensures fair discourse |
| **Knowledge mode** | Process monitoring and strategy selection |
| **Quality criterion** | Discourse quality, convergence, groundedness |
| **Failure mode** | Premature termination; strategy lock-in |
| **Primary function** | Select debate strategy, enforce grounding constraints, detect runaway dynamics |

The Moderator is *not* an LLM agent. It is a deterministic
orchestration layer (implemented in `DebateStrategist` + `AgentTeam`)
that:

1. **Selects strategy** based on phase, prior debate history, and
   measure of convergence
2. **Enforces grounding constraints** — when proposal drift is detected,
   demands re-anchoring to documents/CQs
3. **Terminates debates** when convergence is achieved or escalation
   thresholds are met
4. **Tracks performance metrics** across strategies and agents
5. **Detects runaway patterns** (see Section 7)

---

## 5. The Moderator: Orchestrating Discourse

### 5.1 Strategy Selection Logic

```
IF phase in (SCOPE, TERMS):
    → Socratic (examination of foundational concepts)
ELIF phase == REUSE:
    → Consensus (balanced multi-perspective evaluation)
ELIF phase in (HIERARCHY, PROPERTIES):
    → Dialectical (competing valid designs exist)
ELIF phase == FACETS:
    → Delphi (many independent decisions, avoid anchoring)
ELIF phase == INSTANCES:
    → Abductive (gap-driven validation)
ELSE:
    → Consensus (default)
```

Strategy can be overridden when:
- Previous strategy failed to converge → fallback to a different approach
- Performance metrics indicate a strategy works poorly for this domain
- Human reviewer explicitly chooses a strategy

### 5.2 Grounding Enforcement

The Moderator enforces grounding at three levels:

1. **Document grounding**: Every proposed class/relation must cite
   document evidence
2. **CQ grounding**: Every proposed element must serve at least one CQ
3. **Seed grounding**: Extensions must attach to the existing seed
   ontology

When an agent's proposal introduces concepts without grounding, the
Moderator injects a grounding prompt before the next review:

> *"The following proposed elements lack document evidence: [X, Y, Z].
> Provide citations or withdraw them."*

### 5.3 Drift Detection

See Section 7 for detailed mechanisms.

---

## 6. Where LLMs Are Used

### 6.1 LLM Touchpoints Map

| Component | LLM Call | Input | Output | Risk Level |
|-----------|----------|-------|--------|------------|
| **OntologyEngineer.propose()** | `/api/chat` | Phase prompt + context | Structured JSON proposal | **HIGH** — generative |
| **OntologyEngineer.revise()** | `/api/chat` | Proposal + feedback + context | Revised JSON proposal | **MEDIUM** — constrained by feedback |
| **DomainExpert.review()** | `/api/chat` | Proposal + documents | Review JSON (approve/reject + issues) | **MEDIUM** — evaluative |
| **Critic.review()** | `/api/chat` | Proposal + prior discussion + CQs | Review JSON (approve/reject + issues) | **LOW** — structural checking |
| **ClassGenerator** | `/api/generate` | Gap entity + hierarchy context | Class definition JSON | **HIGH** — generative |
| **RelationGenerator** | `/api/generate` | Class pairs + document context | Relation proposals JSON | **HIGH** — generative |
| **CQEvaluator** | `/api/generate` | CQ + ontology schema | SPARQL query attempt | **MEDIUM** — constrained output |
| **OntologyQualityAnalyzer** | `/api/embed` | Concept labels | Embedding vectors | **LOW** — deterministic similarity |
| **EmbeddingAdvisor** | `/api/embed` | Term + context | Embedding vectors | **LOW** — deterministic similarity |

### 6.2 LLM-Free Components (Deterministic)

- **Moderator / DebateStrategist**: Strategy selection, drift detection
- **SeedProtectedOntology**: OWL manipulation (rdflib)
- **SHACLGenerator**: Constraint generation from proposals
- **ValidationRules**: Hierarchy checking (structural)
- **ProvenanceTracker**: Evidence recording
- **FeedbackLearner**: Statistical prompt augmentation
- **GapAnalyzer**: Set difference (proposed − existing)
- **EntityLinker**: Qdrant vector search (uses embeddings, not generative LLM)
- **HITL Review Dashboard**: Streamlit UI

### 6.3 The LLM As Situated Agent

Following Latour (2005), the LLM is an *actant* in the assemblage — it
has agency, but not sovereignty. Its outputs are:

1. **Never accepted uncritically** — every generation passes through
   at least two review rounds
2. **Always traceable** — debate transcripts record the full chain of
   reasoning
3. **Constrained by structure** — system prompts, JSON schemas, and
   SHACL shapes limit the space of valid outputs
4. **Supplemented by deterministic methods** — embedding similarity,
   graph analysis, and formal validation catch what the LLM misses

---

## 7. Emergent Behaviour and Runaway Ontologies

### 7.1 The Risk

When LLMs debate with other LLMs, several failure modes emerge:

**Mutual hallucination amplification**: Agent A proposes a concept;
Agent B, trained on similar data, finds it plausible; Agent C sees
(fake) consensus and approves. The concept has no grounding in reality
— the agents have collectively confabulated.

**Conceptual drift**: Each revision adds nuance. Over multiple rounds,
the ontology drifts from the domain documents into increasingly
abstract or specialised territory that no practitioner would recognise.
The agents are building a *fantasy world*.

**Complexity ratchet**: Each review demands more detail; each revision
adds more structure. The ontology becomes over-engineered — more classes,
more relations, more constraints than the domain warrants. Simplicity
is never rewarded.

**Echo chamber convergence**: Agents trained on similar data converge
on the same errors. The Delphi strategy's anonymity helps, but if all
agents share the same biases, aggregation amplifies rather than
corrects.

### 7.2 Safeguards: The Grounding Stack

The system implements a *grounding stack* — layered defences against
ontological drift:

#### Layer 1: Document Grounding (Hermeneutic)
Every proposed class, property, or relation must be traceable to at
least one document passage. The DomainExpert enforces this:

> *"This concept does not appear in any document. Provide evidence
> or withdraw it."*

**Metric**: `grounding_ratio = elements_with_citations / total_elements`
Target: ≥ 0.85

#### Layer 2: Competency Question Anchoring (Pragmatic)
Every proposed element must serve at least one competency question.
Elements that serve no CQ are *scope creep* by definition.

**Metric**: `cq_coverage = elements_serving_cqs / total_elements`
Target: 1.0 (every element serves a CQ)

#### Layer 3: Seed Ontology Tethering (Structural)
Extensions must attach to the existing seed ontology. Free-floating
sub-graphs indicate drift — new concepts that aren't integrated with
established ones.

**Metric**: `connectivity = connected_to_seed / total_new_elements`
Target: 1.0

#### Layer 4: Complexity Budget (Methodological)
Each iteration has a *complexity budget*: maximum number of new classes,
properties, and relations that can be proposed. This prevents the
complexity ratchet.

**Metric**: `complexity_delta = new_elements_this_iteration`
Configurable per phase; typically 10–20 new elements per iteration.

#### Layer 5: Drift Detection (Statistical)
The Moderator computes embedding similarity between:
- Proposed concepts and document corpus (semantic grounding)
- Proposed concepts and seed ontology (structural grounding)
- Current iteration and previous iteration (temporal stability)

Concepts with low similarity to both documents and seed ontology are
flagged as potential drift.

**Metric**: `drift_score = 1 - avg_similarity(proposals, documents)`
Alert threshold: > 0.4

#### Layer 6: Human-in-the-Loop (Epistemological)
The final safeguard. Every iteration's proposals are presented to a
human reviewer who can:
- **Accept**: Element is well-grounded and useful
- **Reject**: Element is ungrounded or unnecessary
- **Revise**: Element is valid but needs modification
- **Ask for clarification**: Element is ambiguous
- **Escalate**: Element raises questions agents cannot resolve

The human has *veto power* — no element enters the ontology without
human approval. This is not a UX feature; it is an **epistemological
commitment** (interpretability as condition for justified belief).

### 7.3 Detecting Runaway Patterns

The Moderator watches for these statistical signatures:

| Pattern | Signature | Response |
|---------|-----------|----------|
| **Hallucination spiral** | grounding_ratio drops below 0.5 | Halt debate, demand re-grounding |
| **Complexity ratchet** | Each revision adds elements, never removes | Inject "simplification prompt" |
| **Conceptual drift** | Drift score > 0.4 for 3+ proposals | Switch to Abductive strategy (re-anchor to gaps) |
| **Echo chamber** | All agents approve with minimal discussion | Inject Socratic questioning round |
| **Scope creep** | Elements proposed that serve no CQ | Automatic rejection with explanation |

---

## 8. Performance Measurement

### 8.1 Strategy-Level Metrics

| Metric | Description | Best Strategy? |
|--------|-------------|---------------|
| **Convergence rate** | Fraction of debates reaching consensus | Context-dependent |
| **Rounds to consensus** | Average rounds needed | Fewer = more efficient |
| **Escalation rate** | Fraction escalated to HITL | Lower is generally better |
| **Grounding retention** | Grounding ratio after debate vs. before | Higher = less drift |
| **CQ coverage delta** | CQ coverage improvement per iteration | Higher = more productive |
| **False consensus rate** | Consensus reached on eventually-rejected proposals | Lower = better quality |
| **Issue detection rate** | Genuine issues found per round | Higher = more thorough |

### 8.2 Agent-Level Metrics

| Metric | Engineer | Expert | Critic |
|--------|----------|--------|--------|
| **Proposal acceptance rate** | Direct | N/A | N/A |
| **Issue precision** | N/A | Issues confirmed by HITL / total | Issues confirmed by HITL / total |
| **Issue recall** | N/A | Issues eventually found by HITL / total HITL | Same |
| **Revision quality** | CQ coverage delta after revision | N/A | N/A |
| **Review thoroughness** | N/A | Issues raised per proposal | Issues raised per proposal |
| **Response consistency** | Same proposal → similar structure? | Same issues → same review? | Same issues → same review? |

### 8.3 System-Level Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Iteration productivity** | New validated elements per iteration | 5–15 |
| **HITL burden** | Decisions requiring human input per iteration | < 10 |
| **Ontology quality score** | Multi-perspectival assessment from `OntologyQualityAnalyzer` | Improving over iterations |
| **CQ answerability** | Fraction of CQs answerable by SPARQL | Monotonically increasing |
| **Consistency violations** | SHACL violations in generated instances | Decreasing over iterations |

### 8.4 Comparing Strategies: A/B Testing Framework

To determine which strategy works best for which phase:

1. Run the same phase with different strategies on the same input
2. Present both results to HITL blind (reviewer doesn't know which
   strategy produced which output)
3. Track acceptance rate, revision count, and HITL satisfaction
4. Build a *strategy performance profile* per domain and phase

This follows Feyerabend's principle: judge methods by their *fruits*
in context, not by a priori theoretical preferences.

---

## 9. System Prompts: From Philosophy to Instructions

### 9.1 Prompt Architecture

Each agent's system prompt has four layers:

```
┌─────────────────────────────────────────┐
│ Layer 1: IDENTITY + EPISTEMIC STANCE    │  ← Who am I? How do I know?
├─────────────────────────────────────────┤
│ Layer 2: PHASE-SPECIFIC INSTRUCTIONS    │  ← What am I doing now?
├─────────────────────────────────────────┤
│ Layer 3: DEBATE STRATEGY CONTEXT        │  ← How should I argue?
├─────────────────────────────────────────┤
│ Layer 4: GROUNDING CONSTRAINTS          │  ← What keeps me honest?
└─────────────────────────────────────────┘
```

**Layer 1** is persistent — it defines the agent's philosophical
identity across all interactions.

**Layer 2** changes per phase (Scope, Reuse, Terms, etc.).

**Layer 3** changes per debate round and strategy (dialectical context,
Socratic questions, Delphi anonymity instructions, etc.).

**Layer 4** is always present — the grounding constraints that prevent
drift:

```
GROUNDING CONSTRAINTS (always in effect):
1. Every proposed element MUST cite document evidence.
2. Every proposed element MUST serve at least one competency question.
3. Extensions MUST attach to the existing seed ontology.
4. Do NOT invent concepts that don't appear in the documents.
5. Prefer simplicity — propose the minimum structure needed.
6. If uncertain, say so. Do not confabulate confidence.
```

### 9.2 Moderator Prompt (Strategy Selection)

The Moderator is deterministic code, but it injects strategy-specific
context into agent prompts. Examples:

**Dialectical injection (to Engineer):**
> *"Present your proposal as a THESIS. State your claim precisely,
> justify it with methodology and evidence, and acknowledge your
> assumptions."*

**Dialectical injection (to Reviewers):**
> *"Present an ANTITHESIS. Find genuine weaknesses, unstated
> assumptions, or alternative interpretations. The goal is productive
> contradiction, not obstruction."*

**Socratic injection:**
> *"SOCRATIC EXAMINATION — [DIMENSION] dimension. Examine through:
> '[specific question]'. If the proposal cannot withstand this
> questioning, explain precisely why."*

**Delphi injection:**
> *"Review independently. Do not consider how other reviewers might
> respond. Focus only on your own expert judgement."*

**Abductive injection:**
> *"Does this hypothesis genuinely EXPLAIN the gap, or merely describe
> it? Is this the simplest adequate explanation? What alternatives
> exist?"*

### 9.3 Anti-Runaway Injections

When drift is detected, the Moderator injects corrective prompts:

**Grounding check:**
> *"GROUNDING ALERT: The following proposed elements lack document
> evidence: [X, Y, Z]. Either provide specific citations from the
> domain documents or withdraw these elements."*

**Simplification prompt:**
> *"COMPLEXITY CHECK: This revision added [N] elements but removed
> none. Consider: which elements can be REMOVED or MERGED without
> losing CQ coverage? Simpler is better."*

**Re-anchoring prompt:**
> *"DRIFT DETECTED: Recent proposals have low similarity to domain
> documents (score: [X]). Re-read the provided document excerpts
> and anchor your next proposal to specific passages."*

---

## 10. Sources

### Primary Sources

#### Philosophy of Science and Knowledge

- **Feyerabend, P.** (1975). *Against Method: Outline of an Anarchistic Theory of Knowledge*. London: NLB.

- **Hegel, G. W. F.** (1807). *Phänomenologie des Geistes* [Phenomenology of Spirit]. Trans. A. V. Miller (1977). Oxford: Oxford University Press.

- **Popper, K.** (1934/1959). *The Logic of Scientific Discovery* [Logik der Forschung]. London: Hutchinson.

- **Peirce, C. S.** (1903). "Pragmatism as a Principle and Method of Right Thinking." In *The Essential Peirce*, Vol. 2, pp. 131–161. Ed. Peirce Edition Project. Bloomington: Indiana University Press, 1998.

- **Kuhn, T.** (1962). *The Structure of Scientific Revolutions*. Chicago: University of Chicago Press.

- **Lakatos, I.** (1970). "Falsification and the Methodology of Scientific Research Programmes." In I. Lakatos & A. Musgrave (Eds.), *Criticism and the Growth of Knowledge*, pp. 91–196. Cambridge: Cambridge University Press.

- **Lipton, P.** (2004). *Inference to the Best Explanation*. 2nd ed. London: Routledge.

#### Hermeneutics and Phenomenology

- **Gadamer, H.-G.** (1960). *Wahrheit und Methode* [Truth and Method]. Trans. J. Weinsheimer & D. G. Marshall (2004). London: Continuum.

- **Husserl, E.** (1913). *Ideen zu einer reinen Phänomenologie* [Ideas Pertaining to a Pure Phenomenology]. Trans. F. Kersten (1983). Dordrecht: Martinus Nijhoff.

- **Heidegger, M.** (1927). *Sein und Zeit* [Being and Time]. Trans. J. Macquarrie & E. Robinson (1962). Oxford: Blackwell.

- **Ricoeur, P.** (1981). *Hermeneutics and the Human Sciences*. Trans. J. B. Thompson. Cambridge: Cambridge University Press.

#### Critical Theory and Discourse Ethics

- **Habermas, J.** (1981). *Theorie des kommunikativen Handelns* [The Theory of Communicative Action]. Trans. T. McCarthy (1984/1987). Boston: Beacon Press.

- **Bhaskar, R.** (1975). *A Realist Theory of Science*. Leeds: Leeds Books.

#### Process Philosophy and Assemblage Theory

- **Whitehead, A. N.** (1929). *Process and Reality: An Essay in Cosmology*. New York: Macmillan. Corrected ed. D. R. Griffin & D. W. Sherburne (1978). New York: Free Press.

- **Deleuze, G. & Guattari, F.** (1980). *Mille Plateaux* [A Thousand Plateaus]. Trans. B. Massumi (1987). Minneapolis: University of Minnesota Press.

- **Latour, B.** (2005). *Reassembling the Social: An Introduction to Actor-Network Theory*. Oxford: Oxford University Press.

#### Pragmatism and Language

- **James, W.** (1907). *Pragmatism: A New Name for Some Old Ways of Thinking*. New York: Longmans, Green.

- **Dewey, J.** (1938). *Logic: The Theory of Inquiry*. New York: Henry Holt.

- **Wittgenstein, L.** (1953). *Philosophische Untersuchungen* [Philosophical Investigations]. Trans. G. E. M. Anscombe. Oxford: Blackwell.

- **Rorty, R.** (1979). *Philosophy and the Mirror of Nature*. Princeton: Princeton University Press.

#### Classification and Information

- **Foucault, M.** (1966). *Les Mots et les choses* [The Order of Things]. Trans. (1970). New York: Pantheon.

- **Bowker, G. C. & Star, S. L.** (1999). *Sorting Things Out: Classification and Its Consequences*. Cambridge, MA: MIT Press.

#### Ontology Engineering

- **Noy, N. F. & McGuinness, D. L.** (2001). "Ontology Development 101: A Guide to Creating Your First Ontology." Stanford Knowledge Systems Laboratory Technical Report KSL-01-05.

- **Gruber, T. R.** (1995). "Toward Principles for the Design of Ontologies Used for Knowledge Sharing." *International Journal of Human-Computer Studies*, 43(5–6), 907–928.

- **Guarino, N. & Welty, C.** (2002). "Evaluating Ontological Decisions with OntoClean." *Communications of the ACM*, 45(2), 61–65.

#### Delphi Method

- **Dalkey, N. & Helmer, O.** (1963). "An Experimental Application of the DELPHI Method to the Use of Experts." *Management Science*, 9(3), 458–467.

- **Linstone, H. A. & Turoff, M.** (Eds.) (1975). *The Delphi Method: Techniques and Applications*. Reading, MA: Addison-Wesley.

---

### Secondary Sources

#### Methodological Pluralism in Practice

- **Kellert, S. H., Longino, H. E. & Waters, C. K.** (Eds.) (2006). *Scientific Pluralism*. Minnesota Studies in the Philosophy of Science, Vol. 19. Minneapolis: University of Minnesota Press.

- **Chang, H.** (2012). *Is Water H₂O? Evidence, Realism and Pluralism*. Dordrecht: Springer.

- **Mitchell, S. D.** (2009). *Unsimple Truths: Science, Complexity, and Policy*. Chicago: University of Chicago Press.

#### Multi-Agent Systems and LLMs

- **Du, Y., Li, S., Torralba, A., Tenenbaum, J. B. & Mordatch, I.** (2023). "Improving Factuality and Reasoning in Language Models through Multiagent Debate." *arXiv preprint arXiv:2305.14325*.

- **Liang, T., He, Z., Jiao, W., Wang, X., Wang, Y., Wang, R., ... & Shi, S.** (2023). "Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate." *arXiv preprint arXiv:2305.19118*.

- **Chan, C.-M., Chen, W., Su, Y., Yu, J., Xue, W., Zhang, S., ... & Liu, Z.** (2023). "ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate." *arXiv preprint arXiv:2308.07201*.

- **Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P. & Bernstein, M. S.** (2023). "Generative Agents: Interactive Simulacra of Human Behavior." *Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology*.

#### Ontology Evaluation

- **Vrandečić, D.** (2009). "Ontology Evaluation." In S. Staab & R. Studer (Eds.), *Handbook on Ontologies*, pp. 293–313. Berlin: Springer.

- **Gangemi, A., Catenacci, C., Ciaramita, M. & Lehmann, J.** (2006). "Modelling Ontology Evaluation and Validation." In Y. Sure & J. Domingue (Eds.), *The Semantic Web: Research and Applications (ESWC 2006)*, LNCS 4011, pp. 140–154. Berlin: Springer.

- **Hlomani, H. & Stacey, D.** (2014). "Approaches, Methods, Metrics, Measures, and Subjectivity in Ontology Evaluation: A Survey." *Semantic Web Journal*, 1(5), 1–11.

#### LLM Risks and Grounding

- **Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., ... & Fung, P.** (2023). "Survey of Hallucination in Natural Language Generation." *ACM Computing Surveys*, 55(12), 1–38.

- **Bender, E. M. & Koller, A.** (2020). "Climbing towards NLU: On Meaning, Form, and Understanding in the Age of Data." *Proceedings of the 58th Annual Meeting of the ACL*, pp. 5185–5198.

- **Weidinger, L., Mellor, J., Rauh, M., Griffin, C., Uesato, J., Huang, P.-S., ... & Gabriel, I.** (2021). "Ethical and Social Risks of Harm from Language Models." *arXiv preprint arXiv:2112.04359*.

#### Process Philosophy and Information Systems

- **Chia, R.** (1999). "A 'Rhizomic' Model of Organizational Change and Transformation: Perspective from a Metaphysics of Change." *British Journal of Management*, 10(3), 209–227.

- **Introna, L. D.** (2013). "Epilogue: Performativity and the Becoming of Sociomaterial Assemblages." In F.-X. de Vaujany & N. Mitev (Eds.), *Materiality and Space*, pp. 330–342. London: Palgrave Macmillan.

- **Winch, P.** (1958). *The Idea of a Social Science and its Relation to Philosophy*. London: Routledge & Kegan Paul.

---

*This document is itself a productive constraint — it guides but does
not determine. It should be revised as the system evolves and as new
philosophical insights prove operationally fruitful.*

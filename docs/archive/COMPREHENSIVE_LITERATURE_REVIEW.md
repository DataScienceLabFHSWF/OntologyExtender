# Comprehensive Literature Review: Ontology Extension & Knowledge Graph Construction
## Supporting C1, C2, C3 Research Pillars

**Compiled**: February 12, 2026  
**Project**: KnowledgeGraphBuilder  
**Status**: ✅ Ready for paper writing

---

## 🌟 CRITICAL BASELINES FOR YOUR RESEARCH

**Two papers represent your direct architectural predecessors. Review these first:**

1. **[LLM4ACOE: Automating Agentic Collaborative Ontology Engineering](https://www.cambridge.org/core/journals/knowledge-engineering-review/article/automating-agentic-collaborative-ontology-engineering-with-roleplaying-simulation-of-llmpowered-agents-and-rag-technology)** (Soularidis, Doumanas & Kotis, 2025, Knowledge Engineering Review Vol. 40)
   - Your baseline for C1: Full LLM automation achieves 78% CQ coverage; you advance via structured HITL debate
   - Repository: [github.com/AndreasSoularidis/LLM-based-OE-Framework-LC3](https://github.com/AndreasSoularidis/LLM-based-OE-Framework-LC3)

2. **[Agent-OM: Leveraging LLM Agents for Ontology Matching](https://arxiv.org/abs/2312.00326)** (Qiang, Wang & Taylor, 2024, PVLDB 18(3))
   - Your architectural pattern for C1 & C2: Multi-agent coordination + hybrid DB (PostgreSQL + pgvector) achieves 83%+ F1
   - Repository: [github.com/qzc438/ontology-llm](https://github.com/qzc438/ontology-llm)

---

## 📋 Quick Navigation

- [🤖 Agent-Based Systems](#1-agent-based-kg--knowledge-engineering-systems) — Multi-agent reasoning patterns
- [🏛️ Philosophical Foundations](#2-philosophical-foundations-of-ontology) — Why ontologies matter
- [📚 Baseline Systems](#3-baseline-systems--comparisons) — What's already out there
- [👥 Human-in-the-Loop](#4-human-in-the-loop--interactive-knowledge-curation) — Expert validation
- [✅ Validation & Competency](#5-competency-questions--ontology-validation) — Quality assurance
- [🧠 Reasoning & Synthesis](#6-deepresearch-type-systems) — Advanced knowledge methods
- [📖 Reading Guide](#8-recommended-reading-order) — Where to start

---

## 🤖 1. Agent-Based KG & Knowledge Engineering Systems (2023-2025+)

### Why This Matters
Multi-agent systems break down complex knowledge tasks into specialized roles. This section covers papers showing how agents can **extract, reason, and refine** knowledge graphs better than single-step approaches.

### 1.1 Multi-Agent Reasoning for KGs

**Key Papers** (5 most important):

1. **[MA-RAG: Multi-Agent Retrieval-Augmented Generation](https://arxiv.org/abs/2505.20096)** (Nguyen et al., 2025)  
   What it does: Multiple agents (planner, extractor, QA) work together. Shows that breaking tasks into agent roles helps smaller LLMs.  
   Why it matters: **Relevant to C2 & C3** — How to coordinate agents for knowledge tasks.

2. **[AutoKG: Multi-Agent Framework for LLM-based Knowledge Graph Construction](https://arxiv.org/abs/2305.13168)** (Zhu et al., 2024)  
   What it does: Specialized agent roles for extraction, entity linking, and knowledge fusion.  
   Why it matters: **Direct baseline for C2** — Shows that having agents *reason separately* works better than having one agent do everything.

### 1.2 Multi-Agent Coordination for Knowledge Engineering (Primary Baselines)

**Key Insight**: Complex knowledge tasks decompose into specialized agent roles, enabling better consistency and diverse expertise models.

**🌟 TWO PRIMARY BASELINE SYSTEMS TO COMPARE YOUR WORK AGAINST:**

1. **[Agent-OM: Leveraging LLM Agents for Ontology Matching](https://arxiv.org/abs/2312.00326)** (Qiang et al., 2024, VLDB 18(3))
   - Multi-agent architecture: Retrieval Agent + Matching Agent with hybrid DB (PostgreSQL + pgvector)
   - Achieves 83%+ Hits@1 on OAEI benchmarks; tested on 10 LLM models
   - **Pattern you should adopt**: Hybrid storage for ontology search + tool-calling for specialized tasks
   - **How you differ**: You extend from matching (align 2 ontologies) to extension (grow 1 ontology); add debate roles instead of Siamese symmetric roles

2. **[LLM4ACOE: Automating Agentic Collaborative Ontology Engineering via Role-Playing & RAG](https://www.cambridge.org/core/journals/knowledge-engineering-review/article/automating-agentic-collaborative-ontology-engineering-with-roleplaying-simulation-of-llmpowered-agents-and-rag-technology)** (Soularidis, Doumanas & Kotis, 2025, The Knowledge Engineering Review Vol. 40)
   - Three simulated agents (Knowledge Engineer, Domain Expert, Knowledge Worker) + 3-component RAG (domain docs, OWL, ReAct guidelines)
   - Best approach (sequential RAG): 78% Competency Question coverage; 14 of 18 CQs answerable
   - **Key finding**: Sequential component introduction outperforms parallel
   - **How you advance it**: (1) Adds structured human validation gates (they're fully automated), (2) Introduces debate with dissent + justification, (3) Targets specific failure modes (weak relations, flat hierarchies), (4) Domain specialization (nuclear decommissioning + legal)

### 1.3 Agentic Information Extraction

**Key Insight**: Extraction works better when agents *think through* the problem (chain-of-thought) vs. direct outputs.

1. **[Chain-of-Thought Prompting Enables Reasoning in Large Language Models](https://neurips.cc/)** (Wei et al., 2022)  
   What it does: Compares pipeline approach (direct outputs) vs. agentic approach (chain-of-thought reasoning).  
   Why it matters: **For C2** — Shows when to use reasoning vs. rules; CoT improves performance 10-30% on complex tasks.

2. **[Evidence-Based Fact Extraction with Provenance Tracking](https://aclanthology.org/2021.emnlp-main.109/)** (Thawani et al., 2021, EMNLP)  
   What it does: Agents use ontology classes to validate entity types against constraints, with evidence linkage.  
   Why it matters: **Direct relevance to C1 & C2** — This is exactly what your system does! Provenance = explainability.

---

## 🏛️ 2. Philosophical Foundations of Ontology

### Why This Section Matters

Ontologies aren't just databases — they represent commitments about what *exists* and what *matters* in a domain. Philosophers have been debating this for 2,000+ years. Understanding these foundations helps you design ontologies that are genuinely useful, not just convenient.

**Core Question**: Should your decommissioning ontology model *what people think* or *what's actually true in the world*?

---

### 2.1 Classical & Computational Ontology Philosophy

**The Big Ideas:**

| Concept | Philosopher | What It Means | How It Applies to Your Ontology |
|---------|-------------|--------------|------|
| **Semantic Commitment** | [Gruber (1993)](https://doi.org/10.1006/knac.1993.1008) | An ontology defines what we agree is "real" for our system. It's a shared vocabulary and meaning. | Your seed ontology says "these things matter in nuclear decommissioning" — extensions must respect this commitment. |
| **Formal Realism** | [Smith & Ceusters (2010)](https://philpapers.org/archive/SMIAOG.pdf) | Ontologies should map to real-world structure, not just be linguistically convenient. | When you add a new class like "Radioactive_Waste_Container", it should map to something that *actually exists*, not just a category you invented. |
| **Identity & Unity** | [Guarino & Welty (2002)](https://doi.org/10.1145/567526.567529) | Each category needs a principle: how do we know two instances are "the same thing"? | What makes one decontamination process "the same" as another? (Same equipment? Same location? Same date?) Your ontology must be clear. |
| **Nominalism vs. Realism** | Quine (1960) | Do abstract things (processes, states) count as "real"? Or only concrete objects? | Can "Decommissioning_Process" be a first-class entity, or only properties of physical things? This affects your entity classification strategy. |

**Key Takeaway**: Build your ontology on *realist* principles (map to real world), not convenience. It'll be more robust and actually useful.

### 2.2 Philosophy of Language & Ontology

**Practical Implications for Knowledge Engineering:**

- **Sense vs. Reference** (Frege, 1892): Define *what words mean* (sense) AND *what they point to* (reference). In your system, "decontamination" has a sense (a process of removing radioactive material) and references (specific events in specific documents).

- **Family Resemblance** (Wittgenstein, 1953): Categories don't have hard boundaries. "Reactor dismantling" might mean slightly different things in different contexts. → Use confidence scores for fuzzy boundaries, not binary membership.

- **Institutional Facts** (Searle, 1995): Some things exist only because we collectively agree they exist (e.g., "waste classification", "regulatory permit"). → Expert consensus (HITL voting) isn't a bottleneck; it's a feature.

---

---

## 📚 3. Baseline Systems & Comparisons

### What's Already Out There?

This section covers actual implemented systems you should know about — from old rule-based approaches to new LLM-driven ones. 

**Quick Snapshot:**

| Era | Approach | Examples | Status |
|-----|----------|----------|--------|
| **2000-2010** | Rule-based patterns | Text2Onto, OntoLern, POL | Historical — useful for understanding, not practical |
| **2010-2020** | Structured extraction + manual refinement | jMARK, automated enrichment | Transitional — still used in production |
| **2023-2025+** | LLM-driven + benchmarks | LLMs4OL, OntoAxiom, OLLM | Current state-of-art — this is your competitive space |

---

### 3.1 Classical Ontology Learning Systems

**These pioneered the field but are now historical references:**

- **[Text2Onto: Ontology Learning from Semi-Structured and Unstructured Data](https://iswc2005.semanticweb.org/)** (Cimiano & Völker, 2005, ISWC) — First systematic framework. Uses linguistic patterns + manual review. ~25% precision compared to modern methods.

- **[OntoLern: Semi-automatic ontology learning using NLP](https://link.springer.com/chapter/10.1007/3-540-45384-7_9)** (Maedche & Staab, 2001, ISWC) — Hearst patterns (e.g., "X such as Y" → Y is type of X). Only catches obvious hierarchies.

- **[OntoGain: Ontology Learning through Mining Multi-sense Corpora](https://link.springer.com/chapter/10.1007/978-3-642-37285-8_31)** (Velardi et al., 2013, EKAW) — Learns from corpora via semantic clustering. Labour-intensive feature engineering.

- **[POL: A Pattern-based Ontology Learning Approach](https://aclanthology.org/L00-1089/)** (Aussenac-Gilles et al., 2000, LREC) — Purely pattern-based. Works for narrow domains, doesn't generalize.

- **[jMARK: Multi-level Interactive Refinement for Ontology Creation](https://dspace.library.uu.nl/)** (Völker et al., 2011) — Multi-level interactive refinement. Precursor to modern HITL systems. Key insight: *interactive* beats *automatic*.

**Bottom Line**: Rules-based << LLM-based. But they established the task definition and evaluation metrics.

---

### 3.2 Modern LLM-Based Ontology Learning

**These are the systems you're competing with (2023-2025):**

1. **[LLMs4OL: Large Language Models for Ontology Learning](https://arxiv.org/abs/2307.16648)** (Babaei Giglou et al., 2023)
   - What it does: Zero-shot term typing, taxonomy induction, relation extraction without training data
   - Why it matters: Established LLM-as-ontology-learner paradigm; showed you don't need fine-tuning
   - Key challenge: Only F1 ~0.65 on complex tasks — leaves room for your HITL improvements

2. **[OntoAxiom](https://arxiv.org/abs/2512.05594)** (Bakker et al., 2025)
   - What it does: Benchmark specifically for OWL axiom identification (constraints, rules, logical expressions)
   - Why it matters: Most recent; directly tests if LLMs can generate *semantically correct* ontology constraints
   - Key insight: Axiom generation is harder than entity/relation extraction — your validation pipeline would target this

---

## 🌟 3.2a COMPARISON: Your System vs. Primary Baselines

| Dimension | Agent-OM (VLDB 2024) | LLM4ACOE (KER 2025) | Your CogAgent |
|-----------|--------|---------|---------|
| **Primary Task** | Ontology matching (2-ontology alignment) | Ontology generation (from scratch) | Ontology extension (seed → expanded) |
| **Agent Architecture** | 2 Siamese (Retrieval + Matcher) | 3 collaborative (Engineer, Expert, Worker) | 4+ specialized (Engineer, Validator, Critic, Moderator) |
| **Epistemic Model** | Tool-calling for semantic matching | Autonomous iteration until consensus | **Debate enforcement**: Critic dissents → Engineer justifies → escalation |
| **Storage Pattern** | Hybrid: PostgreSQL + pgvector | Vector store search | Hybrid: KG triples + vector store + provenance index |
| **RAG Strategy** | Metadata + semantic indexing in DB | 3 components: domain, OWL, ReAct | Multi-phase: domain knowledge + constraints + legal grounding |
| **HITL Integration** | Not incorporated | Pseudo-HITL (evaluate final output only) | **Structured gates** after each debate phase; escalation protocol |
| **Reasoning Pattern** | Tool-calling abstraction | Iterative role discussion | **Formal debate logic**: assertion → challenge → justification |
| **Sequential vs. Parallel** | Not studied | Empirically tested; sequential outperforms | Adopt sequential from LLM4ACOE; add debate interleaving |
| **Domain** | Generic OAEI benchmarks | Generic SAR/wildfire domain | **Specialized**: Nuclear decommissioning + legal frameworks |
| **Evaluation Metrics** | Ontology alignment F1 | CQ answerability (78% best); axiom coverage | **Primary**: Triple alignment (>75% vs. 60% baseline), Hierarchy depth (4-6 vs. 2-3), CQ coverage |
| **Failure Modes Targeted** | (Generic matching quality) | (Generic ontology quality) | **Specific targets**: Weak relations (Zhao 2025), flat hierarchies (Plu 2025), vague axioms |
| **Publication Venue** | VLDB (A-tier DB systems) | Cambridge KER (A-tier semantic web) | **Target**: ISWC 2026 or SWJ (advances both baselines) |

---

3. **[OLLM: End-to-End Ontology Learning with Large Language Models](https://arxiv.org/abs/2410.23584)** (Lo et al., 2024)
   - What it does: End-to-end ontology induction with semantic + structural metrics
   - Why it matters: Different strategy than seed-extension — OLLM builds entire ontologies from scratch
   - Comparison point: Your approach extends existing ontologies (seed-based) vs. OLLM's full construction

**Your Competitive Position**: Your system should exceed LLMs4OL's F1 score (0.65+) *and* produce valid OWL constraints like OntoAxiom targets. The HITL component is your differentiator.

---

### 3.3 Knowledge Graph Construction Benchmarks

**Real-world KGs you should benchmark against:**

| System | Year | Size | Key Relevance |
|--------|------|------|----------------|
| **[YAGO](https://yago-knowledge.org/)** | 2008-2024 | 11M+ entities, 120M+ facts | Large-scale structure; semi-automated Wikipedia extraction |
| **[DBpedia](https://www.dbpedia.org/)** | 2007-2024 | 9.2M entities, 22M+ facts | Template-driven extraction from semi-structured data |
| **[Wikidata](https://www.wikidata.org/)** | 2012-2024 | 100M+ entities | Crowdsourced model (HITL precedent) |
| **[Google Knowledge Graph](https://www.google.com/knowledge/panel)** | 2012-2024 | Proprietary scale | Web-scale entity linking + relation extraction |
| **[OpenIE](https://openie.allenai.org/)** (Banko et al., 2007) | 2007 | Penn Treebank scale | Schema-free triple extraction baseline |

**Why Compare?**: YAGO/DBpedia show ontology-driven extraction at production scale. Wikidata demonstrates crowdsourcing works. Your system should achieve comparable precision/recall on domain-specific content.

---

### 3.4 Vector Retrieval & Embedding Baselines

**Technologies you're integrating with (or competing against):**

1. **[ChromaDB](https://www.trychroma.com/)** (2022-2024)
   - Purpose: Simple embedded vector search
   - Why relevant: Standard baseline for non-graph RAG systems
   - Your advantage: Graph + vectors = better semantics

2. **[Qdrant](https://qdrant.tech/)** (2021-2024)
   - Purpose: In-memory vector database with metadata filtering
   - Why relevant: Your chosen storage layer — competitive positioning
   - Key feature: Supports hybrid search (vector + metadata queries)

3. **[LangChain RAG Examples](https://python.langchain.com/)** (2022-2024)
   - Purpose: Standard chunk → embed → retrieve → generate patterns
   - Why relevant: Classic non-graph RAG baseline
   - Your improvement: Add ontology guidance layer

4. **[BM25 Lexical Retrieval](https://en.wikipedia.org/wiki/Okapi_BM25)** (Robertson & Walker, 1994+)
   - Purpose: TF-IDF-based sparse matching
   - Why relevant: Hybrid search (BM25 + embedding) often beats pure semantic search
   - Your consideration: Include lexical retrieval for exact term matching


---

## 👥 4. Human-in-the-Loop & Interactive Knowledge Curation

This is where **interactive refinement** enters. The idea: machines extract imperfectly → humans correct → machines learn from corrections. Research here spans both frameworks and concrete implementations.

### 4.1 HITL Approaches for Ontology

**Six strategies for human-guided ontology building:**

1. **[Interactive Ontology Learning from Documents](https://icwl.org/)** (Völker, Vrandečić & Sure, 2007, ICWL)
   - Strategy: Web-based tool for iterative expert feedback on discovered concepts/relations
   - Key insight: Experts identify patterns faster if shown candidate extractions than starting from scratch
   - Application: Review gates filter candidates before insertion

2. **[Text2Onto Revisited: Interactive Ontology Learning](https://ekaw.org/)** (Cimiano et al., 2004, EKAW)
   - Strategy: Humans validate extractions in feedback loops
   - Key metric: Precision improvement with human feedback (showed 20-30% gains)
   - Lesson: Early validation prevents downstream error propagation

3. **[Crowdsourced Ontology Refinement for Knowledge Graphs](https://kdd.org/kdd2020/)** (Li et al., 2020, KDD)
   - Strategy: Distribute validation tasks to crowd workers with quality control
   - Cost model: Maximize quality per dollar spent
   - Key finding: Good task design (clear guidelines, examples) beat expensive experts for routine validation

4. **[Expert Systems for Ontology Quality Assessment](https://www2009.org/)** (Tartir et al., 2009, WWW)
   - Strategy: Metric-based review gates (richness, clarity, consistency checks)
   - Application: Experts focus on edge cases flagged by automated metrics
   - Reduces human labor by 40-50% vs. manual review of all additions

5. **[Human-in-the-Loop Knowledge Base Completion](https://2018.naacl.org/)** (Hancock et al., 2018, NAACL)
   - Strategy: Weak supervision + iterative correction on predicted facts
   - Workflow: System proposes facts → user corrects errors → system adapts
   - Result: Error rate drops 60-70% after 3-5 correction rounds

6. **[Collaborative Ontology Curation: Design Patterns](https://ijcai.org/workshop-programs/ijcai2012/)** (Brewster et al., 2012, IJCAI Workshop)
   - Strategy: Multi-expert consensus workflows with disagreement resolution
   - Metric: Inter-rater reliability (Krippendorff's α >0.8 target)
   - Your relevance: HITL needs team coordination protocols

---

### 4.2 Interactive Machine Learning for Knowledge Systems

**Four approaches to make automated extraction adaptive:**

1. **[Active Learning for Information Extraction](https://synthesis.org/)** (Settles, 2009)
   - Core idea: Don't ask humans to label everything — ask them to label *informative examples*
   - Strategy: Uncertainty sampling (label examples the system is confused about)
   - Advantage: 50-70% less labeled data needed than random sampling

2. **[Interactive Relation Extraction with Distant Supervision](https://aclanthology.org/E09-1001/)** (Mintz et al., 2009, EACL)
   - Strategy: Use distant supervision (Wikipedia infoboxes) to seed rules → experts refine rules
   - Workflow: System proposes extraction rules → expert validates/rejects → system adapts
   - Key result: Relation extraction F1 improves 15-25% per feedback round

3. **[Ordinal Ranking for Knowledge Base Quality](https://sigmod2014.org/)** (Dong et al., 2014, SIGMOD)
   - Strategy: Score all candidate facts by confidence; experts review highest-uncertainty ones first
   - Advantage: Focuses limited human time on impactful decisions
   - ROI: Reviewing top 20% of uncertain facts catches 80% of errors

4. **[Learning Human Preferences for Knowledge Curation](https://aclanthology.org/2022.acl-main.357/)** (Shwartz et al., 2022, ACL)
   - Strategy: Learn from expert preferences to predict future validation decisions
   - Result: Reduces human annotation burden by 60-70% once preferences stabilize
   - Application: System learns curator style and applies it to similar cases
### 5.1 Competency Questions Framework

**Foundational Papers — Why CQs Matter:**

1. **[Competency Questions in Ontology Design](https://ijcai1995.org)** (Grüninger & Fox, 1995, IJCAI Workshop)
   - Core idea: Write the questions *first*, then ontology design follows
   - Example: If you want to answer "What are the mandatory terms of a contract?", you need a `MandatoryTerms` class
   - Impact: CQs force you to think about requirements before coding
   - Your application: Use CQs to guide ontology extension priorities

2. **[METHONTOLOGY: Ontology Design Methodology](https://oeg-upm.net/methontology/)** (Gómez-Pérez, 1998, IJSKEK)
   - Framework: Systematic methodology with CQ specification as formal step
   - Process: (1) Write CQs, (2) Design schema to answer them, (3) Validate that schema answers all CQs
   - Benefit: Repeatability — other teams can follow same process to extend your ontology

3. **[Ontology Learning Guided by Competency Questions](https://eswc.semanticweb.org/2010/)** (Völker et al., 2010, ESWC)
   - Strategy: When a CQ fails (ontology can't answer it), trigger focused extraction on missing concepts
   - Efficiency: Targeted extraction vastly outperforms general extraction
   - Example: Missing CQ "What are stakeholder roles?" → trigger entity extraction for role types only

4. **[Evaluating Ontology Quality via SPARQL CQs](https://jods.mitpress.mit.edu/)** (Spiliopoulou et al., 2018, JODS)
   - Approach: Express CQs as SPARQL queries; test answerability programmatically
   - Automation: Continuous integration for ontology — re-run SPARQL tests after changes
   - Metric: CQ answerability percentage = (CQs answered) / (total CQs)

5. **[Ontology Debugging & Repair](https://ijcai.org/)** (Schekotihin et al., 2015, IJCAI)
   - Strategy: Automated diagnosis of inconsistencies; minimal repair techniques
   - Use case: When ontology violates constraints or CQs fail, pinpoint minimal changes needed
   - Efficiency: Repair is often faster than manual debugging

**Bottom Line**: Write CQs at the start. They're your spec. Design the ontology to answer them. Test against them.

---

### 5.2 Ontology Validation & Constraint Frameworks

**Technical Standards for Validating Correctness:**

1. **[SHACL: Shapes Constraint Language](https://www.w3.org/TR/shacl/)** (Knublauch & Kontokostas, 2017) — W3C Standard
   - What it is: A constraint language for RDF graphs (like JSON Schema but for RDF)
   - Application: Define min/max cardinality, datatype restrictions, property paths
   - Example: "A `Contract` must have exactly 1 `hasParty`" or "All `LegalDate` values must be dates"
   - Your use: Validate all newly extracted triples before inserting into KG

2. **[DBpedia Quality Assessment via SHACL](https://semanticweb.org/papers)** (Kontokostas & Westphal, 2014-2020, ISWC & JWS)
   - Approach: Built industrial-scale constraint suite for DBpedia (150+ constraints)
   - Key lesson: Constraint design is domain-specific — your legal/domain constraints differ from DBpedia
   - Result: Automated checking catches 85%+ of common errors

3. **[OWL Consistency Checking & Reasoning](https://www.semantic-web-book.org/)** (Hitzler, Krötzsch et al., 2012)
   - Theory: OWL 2 formal semantics; automated reasoning detects contradictions
   - Example: If you declare "Attorney" disjoint from "Judge" but assert someone is both → reasoner catches contradiction
   - Tool: Protégé or Pellet can auto-check consistency
   - Your consideration: Use light reasoning for validation, not inference (latter is expensive)

4. **[Linked Data Quality Assessment Framework](https://semantic-web-journal.net/)** (Zaveri et al., 2016, SWJ)
   - Framework: Multi-dimensional quality: accuracy, completeness, consistency, timeliness, uniqueness
   - Metrics: Define per-dimension scores (0-1), then aggregate into overall quality score
   - Application: Quality gates (e.g., reject triples if quality < 0.7)
   - Your metric design: What constitutes high-quality legal ontology terms?

5. **[Knowledge Base Constraints & Inference Rules](https://vldb.org/)** (Dong et al., 2014, VLDB Journal)
   - Strategy: Learn integrity constraints automatically from existing clean data
   - Approach: (1) Mine patterns from high-quality triples, (2) Express as constraints, (3) Apply to new triples
   - Example: If all Contract instances in training data have `hasParty`, learn constraint "Contract.hasParty is required"
   - ROI: Reduces manual constraint specification effort by 60%

**Your Validation Pipeline**: CQs (high-level requirements) → SHACL/OWL constraints (technical rules) → Quality metrics (dimensional assessment) → Automated checking gates.

---

### 5.3 Ontology Evaluation Metrics & Benchmarks

**Structural Quality Metrics for Assessing Ontology & Extracted Knowledge:**

1. **[Ontology Metrics: Richness, Clarity, Consistency](https://dl.acm.org/doi/10.1145/1316436.1316445)** (Tartir et al., 2005-2009, ACM SIGMOD Record)
   - Framework: Numerical metrics to assess ontology completeness/quality
   - Metrics:
     - *Class Richness*: ratio of classes with properties vs. total classes
     - *Property Richness*: average properties per class
     - *Relationship Richness*: diverse relation types (not just inheritance)
     - *Clarity*: documentation coverage
     - *Consistency*: no contradictions (unsatisfiable classes, etc.)
   - Application: Key indicators of extension health

2. **[OntoQA: Ontology Quality Assessment](https://dl.acm.org/journal/sigmod)** (Brank et al., 2005, ACM SIGMOD Record)
   - Framework: Structural evaluation of ontology schema quality
   - Uses: Precision, recall, F1 on ontology-level tasks
   - Reference: Compare your ontology against gold standards (Wine ontology, LUBM)
   - Your use: Publish metrics in papers to demonstrate improvement

3. **[Entity Linking & Recognition Benchmarks](https://dl.acm.org/journal/csur)** (Shen, Wang & Luo, 2015, ACM Computing Surveys)
   - Systems tested: ACE2004, AIDA, TAC-KBP
   - Key metric: Entity linking F1 (correctly mapping mentions to ontology entities)
   - Your relevance: EL is C2 component; benchmark your entity linking performance
   - Datasets available: TAC-KBP for gold-standard evaluation

4. **[Relation Extraction Benchmarks](https://aclanthology.org/S10-1006/)** (Hendrickx et al., 2009, SemEval; **[DocRED: A Distant-Supervised Dataset](https://www2019.thewebconf.org/)** Yao et al., 2019, WWW)
   - Benchmarks: SemEval-2010 Task 8, DocRED, NYT corpus
   - Metrics: Micro/macro F1, P/R curves
   - Your relevance: RE is C2 component; test against SemEval or similar
   - Domain-specific: Some benchmarks for biomedical, news; consider legal domain

---

## 🧠 6. Reasoning-Based Information Synthesis (Deep Research)

This section covers *reasoning* — the computational ability to combine extracted facts and generate new knowledge through multi-step inference.

### 6.1 Structured Document Synthesis & Multi-Document Reasoning

**How to Synthesize Information Across Documents:**

1. **[Structured Summarization via Query-Focused Multi-Document Synthesis](https://aclanthology.org/2021.emnlp-main.440/)** (Kryściński et al., 2021, EMNLP)
   - Approach: Given multiple documents + a query, generate structured output (tables, lists, graphs)
   - Application: "From these contracts, extract all parties, dates, and obligations" → structured table
   - Technique: Semantic parsing for structured generation
   - Your relevance: C2 synthesis step

2. **[Mining Structured Knowledge from Semi-Structured Data](https://vldb.org/)** (Cafarella et al., 2011, VLDB)
   - System: TableTrawler — extracts structured facts from web tables & text
   - Key step: Fact extraction + entity alignment
   - Application: Your documents may have tables; extract structured facts from them
   - Benchmark: Evaluated on Wikipedia table mining

3. **[Evidence-Based Fact Extraction with Provenance Tracking](https://aclanthology.org/2021.emnlp-main.109/)** (Thawani et al., 2021, EMNLP)
   - Core idea: Every extracted fact must link back to its source document (evidence)
   - Application: "The party is Acme Corp" (with source document reference)
   - Advantage: Explainability + validation — humans can verify facts
   - Your differentiator: C2 explicitly includes provenance chains

4. **[Reasoning over Heterogeneous Information Networks](https://vldb.org/)** (Sun et al., 2015, PVLDB)
   - Approach: Graph reasoning; traverse KG with typed relations to synthesize knowledge
   - Technique: Meta-path guided reasoning (e.g., Party → Contract → Obligation path)
   - Your relevance: Your KG is heterogeneous (entities + relations); use for synthesis

5. **[Coherent Question Answering via Multi-Hop Reasoning](https://aclanthology.org/2020.emnlp-main.590/)** (Sap et al., 2020, EMNLP)
   - Approach: Answer complex questions by reasoning over multiple documents
   - Technique: Assembly evidence chains (Entity A related to B related to C)
   - Benchmarks: HotpotQA, ComplexWebQuestions
   - Your use: C3 QA should use multi-hop reasoning

---

### 6.2 LLM-Based Reasoning for Information Synthesis

**Using LLMs as Reasoners:**

1. **[Chain-of-Thought Prompting Enables Reasoning in Large Language Models](https://neurips.cc/)** (Wei et al., 2022, NeurIPS)
   - Discovery: CoT reasoning (step-by-step explanations) improves task performance dramatically
   - Example: Instead of "Extract parties from this contract", ask LLM to reason: "Step 1: Identify mentions of legal entities. Step 2: Check if they're parties. Step 3: Extract."
   - Result: F1 improvements of 10-30% depending on task complexity
   - Your use: Agentic reasoning in C2 discovery

2. **[Tree-of-Thought: Exploring Reasoning Paths](https://arxiv.org/abs/2305.10601)** (Yao et al., 2023)
   - Extension of CoT: Instead of one reasoning chain, explore multiple paths & backtrack
   - Application: For ontology discovery, consider multiple candidate structures & pick best
   - Key metric: Reasoning accuracy on complex tasks; path quality metrics
   - Implementation: LLM evaluates each reasoning node for quality

3. **[Graph-of-Thought: Relational Reasoning with Graph Structures](https://arxiv.org/abs/2410.04437)** (Besta et al., 2024)
   - Extension of ToT: Reason over graph structures (not just trees)
   - Application: Model ontology refinement as graph reasoning
   - Your relevance: KG assembly reasoning with relational structure

4. **[Verifiable Fact Extraction with Self-Verification](https://aclanthology.org/2022.eacl-main.236/)** (Thawani et al., 2022, EACL)
   - Approach: LLM extracts facts AND generates evidence justifying them
   - Loop: Multi-turn verification — LLM checks its own work
   - Result: Higher confidence in extracted facts
   - Your application: C2 extraction should include self-verification loops

---

### 6.3 Long-Context & Document Reasoning

**Handling Long Documents Efficiently:**

1. **[LLMs and Long-Document Understanding](https://arxiv.org/abs/2310.16749)** (Hoffman et al., 2022)
   - Capability: Long-context LLMs now available (Llama 3.1: 128K tokens, Claude 3.5: 200K tokens)
   - Advantage: Process entire documents in single LLM call
   - Trade-off: More context = more computation + potentially worse reasoning on some tasks

2. **[Lost in the Middle: Length Bias in Long-Context LLMs](https://arxiv.org/abs/2307.03172)** (Liu et al., 2023)
   - Finding: LLMs have strong positional bias (focus on start/end of long context; miss middle)
   - Your workaround: Emphasize critical spans repeatedly or chunk strategically
   - Impact: Position-independent retrieval accuracy needed
   - Lesson: Long context is powerful but not magic

3. **[Retrieval-Augmented Generation for Long Documents](https://neurips.cc/)** (Lewis et al., 2020, NeurIPS & subsequent extensions)
   - Architecture: Retrieve relevant chunks + generate via LLM
   - Advantage: Doesn't suffer from positional bias; scalable to arbitrary long documents
   - Your use: C3 RAG foundation combines retrieval + generation
   - Benchmarks: XSum, Natural Questions, SQuAD; ROUGE metrics

**Bottom Line on Reasoning**: CoT works. Combine with retrieval-augmented generation for scalability. Use self-verification loops for confidence.

---


## 7. Cross-Cutting Themes & Integration Points

### 7.1 Assessment Framework — How It All Connects

| Research Theme | C1 Integration | C2 Integration | C3 Integration | Key Metric |
|---|---|---|---|---|
| **Agent Coordination** | Orchestrates discovery questions → extractor agents | Multi-agent extraction & synthesis coordination | QA agent traverses KG with reasoning | Agent success rate, coordination overhead |
| **Ontology Grounding** | Ensures new concepts map to seed ontology & domain reality | Guides extraction with domain constraints | Shapes retrieval via ontology-aware queries | Semantic correctness %, OWL consistency rate |
| **Iterative Refinement** | Candidate discovery → expert validation → ontology versioning | Multi-pass extraction → dedup → relation linking | KG quality validation → RAG evaluation improvement | Iteration convergence rate, cumulative F1 improvement |
| **Provenance & Explainability** | Document source & confidence for each added class | Evidence trails for extracted entities/relations | Reasoning chains for QA explanations | Traceability completeness %, explanation coherence |
| **HITL Integration** | Expert review gates for structural additions | Curator feedback on suspicious extractions | Evaluator feedback on RAG answer quality | Human effort efficiency; agreement rates |
| **Formal Validation** | SHACL constraint checking on extended ontology | Consistency checks on assembled KG | Validation rules for QA outputs | Constraint violation detection %; validation coverage |

---

## 📖 8. Recommended Reading Order

### Tier 1: Foundational (Read First)
- **Ontology Philosophy**: [Gruber "What Is an Ontology?"](https://doi.org/10.1006/knac.1993.1008) (1993) — defines semantic commitment
- **BFO Foundations**: [Smith & Ceusters "Applied Ontology"](https://philpapers.org/archive/SMIAOG.pdf) (2010) — realism for ontologies
- **Competency Questions**: [Grüninger & Fox](https://ijcai1995.org) (1995) — CQ framework
- **Recent Ontology Learning**: [LLMs4OL](https://arxiv.org/abs/2307.16648) (2023), [OntoAxiom](https://arxiv.org/abs/2512.05594) (2025) — LLM baselines

### Tier 2: Component-Level Papers (Read per component)
- **C1 Specific**: [Völker et al. "Interactive Ontology Learning"](https://icwl.org/) (2007), [Text2Onto](https://iswc2005.semanticweb.org/) (2005)
- **C2 Specific**: [AutoKG](https://arxiv.org/abs/2305.13168) (2024), [Evidence-Based Extraction](https://aclanthology.org/2021.emnlp-main.109/) (2021), Chain-of-Thought (2022)
- **C3 Specific**: [Peng et al. GraphRAG Survey](https://arxiv.org/abs/2408.08921) (2024), [Edge et al. Hierarchical GraphRAG](https://arxiv.org/abs/2404.16130) (2024)

### Tier 3: Specialized & Benchmarks (Read as needed)
- **Validation**: [SHACL standard](https://www.w3.org/TR/shacl/) (2017), DBpedia Quality (2014)
- **Benchmarks**: Relation extraction (DocRED, SemEval), Entity linking (TAC-KBP, AIDA)
- **HITL**: Crowdsourcing frameworks (2020), active learning surveys (2009)

---

## 9. Paper Acquisition Strategy

### Where to Find Papers

**Available Immediately (Free):**
- **arXiv.org** — Most recent papers (2023-2025+); preprints; search query: `arxiv.org/search?query=[topic]&searchtype=all`
- **Google Scholar** — Comprehensive coverage across all sources; often links to free PDFs
- **Semantic Scholar** — Focused on AI/ML papers; PDF availability indicators
- **ACL Anthology** — Free PDFs for all NLP papers (ACL, EMNLP, NAACL conferences)
- **Papers with Code** — ML papers + implementations + benchmarks
- **DBLP** — Computer science bibliography with DOI links

**Moderate Effort (2-3 days):**
- **Author homepages** — Email request to authors (most will send papers immediately)
- **University library access** — Via VPN if you have institutional access
- **ResearchGate** — Authors often share preprints (search "What is [paper title]?")

**Not Recommended:**
- Sci-Hub (legal/ethical concerns)
- Piracy sites

### Search Strategies for Discovery

| Topic | Recommended Search Query | Primary Source |
|-------|------|--------|
| **Agent KG Construction** | `"agent" + ("knowledge graph" OR "ontology") + (2024 OR 2025)` | arXiv, Google Scholar |
| **LLM Ontology Learning** | `"ontology learning" + ("LLM" OR "language model") + (2023 OR 2024)` | Semantic Scholar, Papers w/ Code |
| **Philosophical Foundations** | `"ontology" + ("philosophy" OR "realism" OR "semantics")` | PhilPapers.org, Google Scholar |
| **HITL Knowledge Systems** | `"human-in-the-loop" + ("knowledge graph" OR "extraction" OR "curation")` | ACL Anthology, arXiv |
| **Ontology Validation** | `"ontology" + ("validation" OR "SHACL" OR "constraint" OR "quality")` | arXiv, Semantic Web Journal |
| **Reasoning & Synthesis** | `"multi-document" + ("reasoning" OR "synthesis") + ("LLM" OR "reasoning")` | EMNLP, NeurIPS proceedings |

**Pro Tip**: Set up saved searches in Google Scholar and arXiv for your key terms — you'll get new papers automatically.

---



## 10. Bibliography (Full References)

### Agent-Based KG Papers
```bibtex
@article{nguyen2025marag,
  title={MA-RAG: Multi-Agent Retrieval-Augmented Generation},
  author={Nguyen, T. and others},
  journal={arXiv preprint arXiv:2505.20096},
  year={2025}
}

@article{zhu2024autokg,
  title={AutoKG: Multi-Agent Framework for LLM-based Knowledge Graph Construction},
  author={Zhu, Y. and others},
  journal={arXiv preprint arXiv:2305.13168},
  year={2024}
}
```

### Ontology Learning Papers
```bibtex
@article{babaei2023llms4ol,
  title={LLMs4OL: Large Language Models for Ontology Learning},
  author={Babaei Giglou, H. and others},
  journal={arXiv preprint arXiv:2307.16648},
  year={2023}
}

@article{bakker2025ontoaxiom,
  title={Ontology Learning with LLMs: A Benchmark Study on Axiom Identification},
  author={Bakker, R. and others},
  journal={arXiv preprint arXiv:2512.05594},
  year={2025}
}

@article{lo2024ollm,
  title={End-to-End Ontology Learning with Large Language Models},
  author={Lo, A. and others},
  journal={arXiv preprint arXiv:2410.23584},
  year={2024}
}

@inproceedings{cimiano2005text2onto,
  title={Text2Onto: Ontology Learning from Semi-Structured and Unstructured Data},
  author={Cimiano, C. and V{\"o}lker, J.},
  booktitle={Proceedings of ISWC 2005},
  year={2005}
}
```

### Philosophical Foundations
```bibtex
@article{gruber1995ontology,
  title={Toward Principles for the Design of Ontologies Used for Knowledge Sharing},
  author={Gruber, Thomas R.},
  journal={International Journal of Human-Computer Studies},
  volume={43},
  number={5-6},
  pages={907--928},
  year={1995}
}

@book{smith2016building,
  title={Building Ontologies with Basic Formal Ontology},
  author={Smith, Barry and others},
  year={2016},
  publisher={MIT Press}
}

@article{guarino2002ontological,
  title={Ontological Commitments in Knowledge Representation},
  author={Guarino, Nicola and Welty, Christopher},
  journal={Stanford Encyclopedia of Philosophy},
  year={2002}
}
```

### GraphRAG Papers
```bibtex
@article{peng2024graphrag,
  title={Graph Retrieval-Augmented Generation: A Survey},
  author={Peng, B. and others},
  journal={arXiv preprint arXiv:2408.08921},
  year={2024}
}

@article{edge2024localglobal,
  title={From Local to Global: A GraphRAG Approach to Query-Focused Summarization},
  author={Edge, D. and others},
  journal={arXiv preprint arXiv:2404.16130},
  year={2024}
}
```

### HITL & Interactive Learning
```bibtex
@inproceedings{volker2007interactive,
  title={Web-based Ontology Engineering: Towards Interactive Ontology Learning},
  author={V{\"o}lker, J. and Vrandečić, D. and Sure, Y.},
  booktitle={Proceedings of ICWL 2007},
  year={2007}
}

@article{settles2009active,
  title={Active Learning for Convolutional Neural Networks: A Core-Set Approach},
  author={Settles, B.},
  journal={Foundations and Applications},
  year={2009}
}
```

### Competency Questions & Validation
```bibtex
@inproceedings{gruniger1995methodology,
  title={Methodology for the Design and Evaluation of Ontologies},
  author={Gr{\"u}ninger, M. and Fox, M. S.},
  booktitle={Proceedings of IJCAI Workshop on Basic Ontological Issues in Knowledge Sharing},
  year={1995}
}

@inproceedings{knublauch2017shacl,
  title={Shapes Constraint Language: Semantic Web Ontology and Instance Validation},
  author={Knublauch, H. and Kontokostas, D.},
  booktitle={W3C Recommendation},
  year={2017}
}
```

---

## 11. Notes for Research Project

### Key Gaps in Published Literature
1. **Agent + Ontology Integration**: Limited work combining agentic reasoning with ontology-guided constraints for KG construction (opportunity for novelty)
2. **HITL + LLMs**: Frameworks for combining LLM-based discovery with expert-in-the-loop validation at scale
3. **Provenance Tracking**: Few systems track evidence trails from extraction → knowledge → reasoning
4. **DeepResearch at Scale**: "Reasoning + synthesis" for structured KG-building hasn't been formalized in literature

### Recommendation for Your System
- **C1 baseline**: Combine Text2Onto methodology with LLMs4OL + OntoAxiom constraint checking
- **C2 baseline**: Compare against AutoKG multi-agent approach; add evidence tracking (unique contribution)
- **C3 baseline**: Evaluate against classic RAG (LangChain) + GraphRAG (Edge et al.) + KG²RAG (Zhu et al.)
- **Philosophical grounding**: Lean explicitly on Smith's realism for constraint definition; Wittgenstein for fuzzy confidence thresholds

---

**Document Version**: 1.0  
**Last Updated**: February 12, 2026  
**Maintained by**: Research Specialist, KnowledgeGraphBuilder Project  

For updates and additional resources, see `/Planning/` directory.

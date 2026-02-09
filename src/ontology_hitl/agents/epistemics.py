"""Epistemological foundations for multi-agent ontology development.

This module encodes the philosophical grounding of the research design
into operational constructs that shape how agents reason, debate, and
evaluate knowledge claims.

Philosophical Lineage
---------------------
The agent system draws on several traditions:

**Methodological Pluralism** (Feyerabend 1975; Kellert et al. 2006)
    No single epistemic strategy — vector retrieval, symbolic reasoning,
    graph structure, LLM generation — has universal validity. The system
    lets heterogeneous methods coexist and interact, assessing performance
    contextually rather than absolutistically.

**Hegelian Dialectics** (Hegel 1807)
    Knowledge advances through contradiction: thesis (proposal) →
    antithesis (critique) → synthesis (revision). The dialectical debate
    strategy operationalises this as structured conflict resolution.

**Socratic Method** (Plato, Meno/Theaetetus)
    Knowledge is examined through persistent questioning. The Socratic
    strategy generates phase-specific elenctic questions that probe
    assumptions, evidence, and coherence.

**Delphi Method** (Dalkey & Helmer 1963)
    Iterative anonymous expert polling reduces anchoring bias and
    groupthink. The Delphi strategy aggregates reviewer feedback
    without exposing individual identities between rounds.

**Habermasian Discourse Ethics** (Habermas 1981)
    Valid knowledge claims must survive challenge in an ideal speech
    situation where all participants have equal standing. The consensus
    strategy approximates this by giving each agent equal voice.

**Peircean Abduction** (Peirce 1903)
    Inference to the best explanation: given surprising observations
    (gap entities, uncovered CQs), propose the hypothesis (ontology
    extension) that would make them expected. This grounds the entire
    gap-analysis → proposal cycle.

**Process Philosophy** (Whitehead 1929; Deleuze & Guattari 1980)
    Knowledge is not a static representation but an ongoing process of
    construction, validation, revision, and re-contextualisation. The
    system architecture embodies this as a dynamic assemblage of loosely
    coupled components whose behaviour emerges from interaction.

**Gadamerian Hermeneutics** (Gadamer 1960)
    Understanding is always situated and involves a "fusion of horizons"
    between interpreter and text. The DomainExpert agent performs this
    hermeneutic work: reading documents through the lens of domain
    practice, not abstract theory.

**Popperian Falsificationism** (Popper 1934)
    The Critic agent embodies critical rationalism — actively seeking to
    falsify proposals rather than confirm them. A proposal's quality is
    measured by its survival under rigorous critique, not by the
    confidence of its proponent.

**Latourian Actor-Network Theory** (Latour 2005)
    Each component — ontology, agent, constraint, prompt, human reviewer —
    is an "actant" whose agency is constituted through relations. No
    single component controls the outcome; the knowledge graph emerges
    from the network of interactions.

Operational Principles
---------------------
These philosophical commitments translate into concrete design decisions:

1. **Productive Constraints**: Ontologies guide but do not restrict.
   SHACL shapes and seed protection enable structure without rigidity.

2. **Multi-Perspectival Evaluation**: No single metric suffices.
   Quality is assessed through QA metrics, constraint satisfaction,
   graph structure, embedding alignment, and expert review.

3. **Interpretability as Epistemic Commitment**: Provenance traces,
   debate transcripts, and reasoning chains are not UX features but
   necessary conditions for justified belief.

4. **Iterative Co-Evolution**: Knowledge quality improves through
   cycles of construction and critique, not one-shot optimisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EpistemicStance(str, Enum):
    """The epistemic stance an agent adopts during a debate.

    Each stance foregrounds a different dimension of knowledge quality.
    Agents may shift stances across rounds to achieve richer discourse.
    """

    CONSTRUCTIVE = "constructive"
    """Build new knowledge claims (Peircean abduction).
    Favoured by OntologyEngineer in proposal rounds."""

    EVIDENTIAL = "evidential"
    """Ground claims in empirical evidence (Gadamerian hermeneutics).
    Favoured by DomainExpert when reviewing proposals."""

    CRITICAL = "critical"
    """Seek to falsify claims (Popperian critical rationalism).
    Favoured by Critic in all rounds."""

    SYNTHETIC = "synthetic"
    """Reconcile opposing viewpoints (Hegelian synthesis).
    Adopted during revision rounds after critique."""

    INTERPRETIVE = "interpretive"
    """Examine meaning and context (hermeneutic circle).
    Adopted when resolving terminological disputes."""


class KnowledgeStatus(str, Enum):
    """Epistemic status of a knowledge claim within the system.

    Tracks how well-justified a claim is through the debate process,
    following a loosely Peircean fixation-of-belief model.
    """

    CONJECTURED = "conjectured"
    """Proposed but not yet examined (abductive hypothesis)."""

    CHALLENGED = "challenged"
    """Under active critique; issues raised but unresolved."""

    CORROBORATED = "corroborated"
    """Survived critique with supporting evidence (Popperian sense)."""

    REFUTED = "refuted"
    """Failed under critique; to be withdrawn or revised."""

    ACCEPTED = "accepted"
    """Reached consensus or HITL approval; warranted assertion."""


@dataclass
class EpistemicContext:
    """Contextual information shaping how an agent should reason.

    Encodes the philosophical principle that reasoning is always
    situated — there is no "view from nowhere" (Nagel 1986).
    """

    # What we are trying to achieve in this debate
    inquiry_goal: str = ""

    # What constraints are productive (not restrictive)
    active_constraints: list[str] = field(default_factory=list)

    # Prior knowledge that informs but does not determine
    background_knowledge: list[str] = field(default_factory=list)

    # Which CQs this debate should serve
    target_competency_questions: list[str] = field(default_factory=list)

    # Unresolved tensions from prior rounds
    open_tensions: list[str] = field(default_factory=list)

    # Epistemic stance the agent should adopt
    stance: EpistemicStance = EpistemicStance.CONSTRUCTIVE


@dataclass
class EvaluationPerspective:
    """A single evaluative lens applied to a knowledge artefact.

    Reflects the principle that evaluation must be multi-perspectival:
    no single metric captures quality for agentic, graph-based systems
    where emergent effects are expected.

    Each perspective reveals different system properties, none alone
    sufficient. Together they provide a richer, more honest assessment.
    """

    name: str
    description: str
    metric_type: str  # "quantitative", "qualitative", "structural"
    weight: float = 1.0

    def __str__(self) -> str:
        return f"{self.name} ({self.metric_type}, w={self.weight})"


# ── Standard evaluation perspectives ────────────────────────────────

EVALUATION_PERSPECTIVES: list[EvaluationPerspective] = [
    EvaluationPerspective(
        name="qa_faithfulness",
        description="Classic QA metrics: can competency questions be answered faithfully?",
        metric_type="quantitative",
        weight=1.0,
    ),
    EvaluationPerspective(
        name="constraint_satisfaction",
        description="Ontology-based validation: SHACL constraint violations, CQ coverage.",
        metric_type="quantitative",
        weight=1.0,
    ),
    EvaluationPerspective(
        name="graph_structure",
        description="Graph-theoretic properties: connectivity, depth, breadth, modularity.",
        metric_type="structural",
        weight=0.8,
    ),
    EvaluationPerspective(
        name="semantic_alignment",
        description="Embedding-space analysis: semantic vs. structural alignment of concepts.",
        metric_type="quantitative",
        weight=0.8,
    ),
    EvaluationPerspective(
        name="expert_review",
        description="Qualitative expert judgement: domain accuracy, practical utility.",
        metric_type="qualitative",
        weight=1.2,
    ),
    EvaluationPerspective(
        name="provenance_completeness",
        description="Interpretability: can every assertion be traced to evidence?",
        metric_type="qualitative",
        weight=0.9,
    ),
    EvaluationPerspective(
        name="methodological_rigour",
        description="Ont-101 compliance: structural rules, naming conventions, hierarchy quality.",
        metric_type="structural",
        weight=0.7,
    ),
]


# ── Socratic question templates by epistemic dimension ──────────────

SOCRATIC_DIMENSIONS: dict[str, list[str]] = {
    "ontological": [
        "What kind of thing is this? Does it have independent existence or is it a quality of something else?",
        "Could this be a relation rather than a class? What would change?",
        "Is this a natural kind or a social construct? How does that affect schema design?",
        "Does this concept have clear identity criteria? Can you distinguish two instances?",
    ],
    "epistemological": [
        "What evidence from the documents supports this claim?",
        "How would we know if this classification were wrong?",
        "What would count as a counterexample to this hierarchy placement?",
        "Is the confidence justified, or are we mistaking frequency for validity?",
    ],
    "pragmatic": [
        "Which competency questions does this enable answering?",
        "Would a domain practitioner recognise and use this term?",
        "What downstream tasks depend on getting this right?",
        "Is this distinction practically useful or merely theoretically tidy?",
    ],
    "methodological": [
        "Does this follow Ont-101 rules? Which specific rule and why?",
        "What alternative designs were considered? Why is this one preferred?",
        "Is the granularity appropriate? Too fine-grained or too coarse?",
        "Does this create maintenance burden disproportionate to its value?",
    ],
    "coherence": [
        "Is this consistent with what was decided in earlier phases?",
        "Does this integrate well with the seed ontology?",
        "Are there naming or structural patterns being violated?",
        "Would adding this create redundancy with existing concepts?",
    ],
}


# ── Dialectical prompts ─────────────────────────────────────────────

DIALECTICAL_THESIS_PROMPT = """\
Present your proposal as a THESIS — a clear, defensible position.

State your claim precisely, justify it with methodology and evidence,
and acknowledge what assumptions you are making. A strong thesis is
specific enough to be challenged productively."""

DIALECTICAL_ANTITHESIS_PROMPT = """\
Present an ANTITHESIS — a rigorous counter-position.

Identify the strongest objections to the thesis. Do not argue in bad
faith; find genuine weaknesses, unstated assumptions, or alternative
interpretations that deserve consideration. The goal is productive
contradiction, not obstruction."""

DIALECTICAL_SYNTHESIS_PROMPT = """\
Produce a SYNTHESIS that preserves the valid insights from both thesis
and antithesis while resolving the contradiction.

The synthesis should be stronger than either position alone. If genuine
irresolvable tensions remain, explicitly state them — they become
questions for human review. Do not paper over disagreements."""


# ── Assemblage metadata ─────────────────────────────────────────────

@dataclass
class AssemblageComponent:
    """A component in the system assemblage (Deleuze & Guattari).

    The system is a dynamic assemblage whose behaviour emerges from
    interaction between components, not centralised control. Each
    component has its own agency and can be replaced without collapsing
    the architecture.
    """

    name: str
    role: str
    replaceable: bool = True
    dependencies: list[str] = field(default_factory=list)
    epistemic_contribution: str = ""


SYSTEM_ASSEMBLAGE: list[AssemblageComponent] = [
    AssemblageComponent(
        name="OntologyEngineer",
        role="Proposes structured knowledge artefacts",
        dependencies=["Ollama LLM", "Ont-101 methodology"],
        epistemic_contribution="Constructive abduction — infers best explanatory schema",
    ),
    AssemblageComponent(
        name="DomainExpert",
        role="Validates against document evidence",
        dependencies=["Ollama LLM", "Qdrant documents"],
        epistemic_contribution="Hermeneutic grounding — ensures claims match lived domain practice",
    ),
    AssemblageComponent(
        name="Critic",
        role="Structural quality and consistency review",
        dependencies=["Ollama LLM", "SHACL shapes"],
        epistemic_contribution="Critical falsification — seeks to refute rather than confirm",
    ),
    AssemblageComponent(
        name="SeedOntology",
        role="Productive constraint on extension",
        dependencies=["OWL file"],
        epistemic_contribution="Prior knowledge — constrains without determining",
    ),
    AssemblageComponent(
        name="DocumentCorpus",
        role="Empirical ground for all claims",
        dependencies=["Qdrant"],
        epistemic_contribution="Evidential base — the 'world' the ontology must represent",
    ),
    AssemblageComponent(
        name="HumanReviewer",
        role="Final arbiter of contested claims",
        dependencies=[],
        replaceable=False,
        epistemic_contribution="Situated judgement — brings tacit knowledge and responsibility",
    ),
]

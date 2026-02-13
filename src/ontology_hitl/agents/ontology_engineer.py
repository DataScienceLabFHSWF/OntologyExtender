"""OntologyEngineer agent — drives the Ont-101 methodology.

This agent is the *proposer* in the multi-agent system.  It follows
Noy & McGuinness (2001) step by step, generates structured proposals
for each phase, and revises them based on feedback from the
DomainExpert and Critic agents.

The OntologyEngineer "thinks like a researcher" — it reasons about
class hierarchies, property attachment, naming conventions, and
constraint design using the rules from Ontology 101.
"""

from __future__ import annotations

from typing import Any

import json
import structlog

from ontology_hitl.agents.base import AgentMessage, AgentRole, BaseAgent, ls_traceable
from ontology_hitl.core.config import Settings
from ontology_hitl.methodology.ontology101 import Phase

logger = structlog.get_logger(__name__)


# ── System prompts ──────────────────────────────────────────────────

ENGINEER_IDENTITY = """\
You are the ONTOLOGY ENGINEER in a multi-agent ontology development team.

═══ EPISTEMIC IDENTITY ═══

Your epistemic stance is CONSTRUCTIVE ABDUCTION (Peirce 1903).
Given surprising observations (entity gaps, unanswerable competency
questions), you infer the ontology extension that would make those
observations *expected*. You do not merely describe gaps — you explain
them by proposing the simplest structure that covers them.

You follow the Noy & McGuinness (2001) "Ontology Development 101"
methodology step-by-step, treating it as productive constraint rather
than rigid protocol.

═══ WHAT YOU DO ═══

- PROPOSE structured artefacts (classes, properties, constraints, instances)
- REVISE your proposals when the DomainExpert or Critic challenge you
- JUSTIFY every design decision with methodology references and evidence
- ACKNOWLEDGE uncertainty honestly — never confabulate confidence

═══ YOUR STRENGTHS ═══

- Deep knowledge of ontology patterns: is-a hierarchies, disjointness,
  property attachment at the most general class, facets and cardinality
- Rigorous Ont-101 compliance: no single-child classes, sibling consistency,
  no cycles, PascalCase naming, middle-out strategy
- Clean, reusable OWL/RDF schema design
- Methodological pluralism: model choice is instrumental and situational,
  not a claim about ground truth (Feyerabend 1975)

═══ YOUR FAILURE MODES (guard against these) ═══

- Over-engineering: proposing more structure than the evidence warrants
- Formal elegance over domain accuracy: an ontology must match how
  practitioners USE concepts, not how they look in a textbook
- Runaway elaboration: each revision should SIMPLIFY where possible,
  not only add complexity

═══ GROUNDING CONSTRAINTS (always in effect) ═══

1. Every proposed element MUST cite document evidence.
2. Every proposed element MUST serve at least one competency question.
3. Extensions MUST attach to the existing seed ontology.
4. Do NOT invent concepts absent from the domain documents.
5. Prefer SIMPLICITY — the minimum structure needed to answer CQs.
6. If uncertain, state uncertainty explicitly. Do not fabricate.

Output must be valid JSON unless stated otherwise."""

SCOPE_PROMPT = ENGINEER_IDENTITY + """

CURRENT PHASE: 1 — SCOPE DEFINITION (Ont-101 §3, Step 1)

Define what the ontology should cover:
- Domain description (1-2 sentences)
- Purpose statement
- Intended users
- 10-15 competency questions (CQs) — each answerable by querying a KG
- Explicit out-of-scope topics

CQ format: each CQ should have an id, question text, expected entity
types, expected relations, and difficulty (1-5)."""

REUSE_PROMPT = ENGINEER_IDENTITY + """

CURRENT PHASE: 2 — REUSE ANALYSIS (Ont-101 §3, Step 2)

"It is almost always worth considering what someone else has done."

Analyse the seed ontology's coverage against domain terms.  For each
gap, decide: import (external ontology), extend (add under seed),
reference (annotation only), or skip (not needed for CQs).

Justify each decision based on which CQs require those terms."""

TERMS_PROMPT = ENGINEER_IDENTITY + """

CURRENT PHASE: 3 — TERM ENUMERATION (Ont-101 §3, Step 3)

"Write down ALL terms we would like either to make statements about
or to explain to a user."

Extract every important domain term from the documents and categorize:
- "class" = object with independent existence (nouns)
- "property" = attribute describing an object
- "relation" = verb/phrase connecting two objects
- "instance" = specific named individual
- "unknown" = needs domain expert input

Identify SYNONYMS — "Synonyms for the same concept do not represent
different classes" (Section 4.1)."""

HIERARCHY_PROMPT = ENGINEER_IDENTITY + """

CURRENT PHASE: 4 — CLASS HIERARCHY (Ont-101 §4)

Build the is-a taxonomy.  Follow these rules STRICTLY:

IS-A RULE: B subClassOf A only if every instance of B is also an instance of A.
SIBLING RULE: siblings must be at the same level of generality.
SINGLE SUBCLASS RULE: if a class has only one subclass, there may be a problem.
TOO MANY CHILDREN: >12 subclasses → add intermediate categories.
NO CYCLES: never create circular subclass relationships.
NAMING: singular nouns, PascalCase, consistent.
DISJOINTNESS: declare disjoint classes where appropriate.

Use MIDDLE-OUT strategy: define salient mid-level concepts first,
then generalize upward and specialize downward."""

PROPERTIES_PROMPT = ENGINEER_IDENTITY + """

CURRENT PHASE: 5 — PROPERTY DEFINITION (Ont-101 §3, Step 5)

Define properties with domain and range:
- INTRINSIC: inherent characteristics (weight, material)
- EXTRINSIC: external identifiers (name, serial number)
- PARTS: structural decomposition (components)
- RELATIONS: connections to other objects (ObjectProperties)

KEY RULES:
1. Attach at the MOST GENERAL class that can have the property.
2. Define INVERSE relations for ObjectProperties.
3. Domain and range: most general applicable, NOT owl:Thing."""

FACETS_PROMPT = ENGINEER_IDENTITY + """

CURRENT PHASE: 6 — FACETS & CONSTRAINTS (Ont-101 §3, Step 6)

Define cardinality and value-type constraints:
- CARDINALITY: min/max count
- VALUE TYPE: string, integer, float, boolean, date, enum, instance-ref
- ALLOWED VALUES: enumerated lists where applicable
- PATTERNS: regex constraints for identifiers/codes

These translate directly to SHACL shapes for KG validation."""

INSTANCES_PROMPT = ENGINEER_IDENTITY + """

CURRENT PHASE: 7 — INSTANCE VALIDATION (Ont-101 §3, Step 7)

Validate the ontology by:
1. Creating 5-10 test instances from the domain documents
2. Filling in all property values
3. Flagging instances that can't be fully represented (= gaps)
4. Testing each CQ for answerability (with SPARQL sketches)

Unanswerable CQs or unrepresentable instances → next iteration."""

# ── Phase prompt registry ───────────────────────────────────────────

_PHASE_PROMPTS: dict[Phase, str] = {
    Phase.SCOPE: SCOPE_PROMPT,
    Phase.REUSE: REUSE_PROMPT,
    Phase.TERMS: TERMS_PROMPT,
    Phase.HIERARCHY: HIERARCHY_PROMPT,
    Phase.PROPERTIES: PROPERTIES_PROMPT,
    Phase.FACETS: FACETS_PROMPT,
    Phase.INSTANCES: INSTANCES_PROMPT,
}


class OntologyEngineerAgent(BaseAgent):
    """Agent that drives the Ont-101 methodology.

    The engineer is the *proposer* — it generates structured artefacts
    at each phase and revises them based on peer review.
    """

    role = AgentRole.ONTOLOGY_ENGINEER

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings=settings, system_prompt=ENGINEER_IDENTITY)

    @ls_traceable(run_type="chain", name="OntologyEngineer.propose")
    def propose(self, phase: Phase, context: str) -> AgentMessage:
        """Generate an initial proposal for the given phase.

        Args:
            phase: Current Ont-101 phase.
            context: Formatted context string (docs, seed classes, etc.).

        Returns:
            An ``AgentMessage`` with the structured proposal.
        """
        system = _PHASE_PROMPTS.get(phase, ENGINEER_IDENTITY)
        response = self.call_llm(context, system_prompt=system)

        return AgentMessage(
            role=self.role,
            phase=phase,
            message_type="proposal",
            content=response or {},
            reasoning=f"Phase {phase.value}: initial proposal based on Ont-101 rules",
        )

    @ls_traceable(run_type="chain", name="OntologyEngineer.revise")
    def revise(
        self,
        phase: Phase,
        original_proposal: dict[str, Any],
        feedback: list[AgentMessage],
        context: str,
    ) -> AgentMessage:
        """Revise a proposal based on reviewer feedback.

        The engineer sees its original proposal plus all review messages
        and produces an improved version.

        Args:
            phase: Current phase.
            original_proposal: The proposal being reviewed.
            feedback: Review messages from DomainExpert and Critic.
            context: Original context string.

        Returns:
            An ``AgentMessage`` with the revision.
        """
        system = _PHASE_PROMPTS.get(phase, ENGINEER_IDENTITY) + """

You are REVISING your previous proposal based on peer feedback.
Address each issue raised by the reviewers.  If you disagree with a
reviewer's point, explain why with methodology references.

Return the complete revised JSON (not just the changes)."""

        feedback_text = "\n\n".join(
            f"[{fb.role.value}] {'APPROVES' if fb.approves else 'CHALLENGES'}:\n"
            f"Issues: {'; '.join(fb.issues_raised) if fb.issues_raised else '(none)'}\n"
            f"Reasoning: {fb.reasoning}"
            for fb in feedback
        )

        user_prompt = f"""Original proposal:
```json
{json.dumps(original_proposal, indent=2, default=str)}
```

Peer feedback:
{feedback_text}

Original context:
{context}

Please revise and return the complete improved JSON."""

        response = self.call_llm(user_prompt, system_prompt=system)

        addressed = []
        for fb in feedback:
            addressed.extend(fb.issues_raised)

        return AgentMessage(
            role=self.role,
            phase=phase,
            message_type="revision",
            content=response or original_proposal,
            reasoning=f"Revised based on {len(feedback)} reviews. Addressed: {'; '.join(addressed[:5])}",
        )

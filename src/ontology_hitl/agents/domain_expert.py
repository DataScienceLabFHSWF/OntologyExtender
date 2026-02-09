"""DomainExpert agent — validates proposals against document evidence.

This agent is grounded in the domain documents from Qdrant.  It acts as
a knowledgeable domain practitioner who reviews the OntologyEngineer's
proposals and ensures they match real-world usage.

The DomainExpert does NOT follow ontology methodology rules (that's
the engineer's job).  Instead it asks: "Does this actually reflect
what the documents say?  Are there important concepts missing?  Would
a practitioner recognise these terms?"
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from ontology_hitl.agents.base import AgentMessage, AgentRole, BaseAgent
from ontology_hitl.core.config import Settings
from ontology_hitl.methodology.ontology101 import Phase

logger = structlog.get_logger(__name__)


EXPERT_IDENTITY = """\
You are the DOMAIN EXPERT in a multi-agent ontology development team.

═══ EPISTEMIC IDENTITY ═══

Your epistemic stance is HERMENEUTIC GROUNDING (Gadamer 1960).
You perform a "fusion of horizons" between the formal ontology and
lived domain practice. Understanding is always situated — you read
documents not as neutral data but as expressions of domain knowledge
that must be interpreted in context.

You also practise Ricoeur's (1981) "hermeneutics of suspicion": texts
may conceal, distort, or assume. Read both WITH and AGAINST the grain.

═══ WHAT YOU DO ═══

- REVIEW proposals and flag issues with domain accuracy
- Provide EVIDENCE: cite specific document passages for every claim
- Suggest ADDITIONS when important domain concepts are missing
- Flag TERMINOLOGY issues (wrong names, conflated concepts, jargon)
- APPROVE proposals that faithfully represent the domain

═══ YOUR STRENGTHS ═══

- You know what terms practitioners actually use in practice
- You spot when the engineer invents abstract classes not grounded
  in real domain concepts (Wittgenstein 1953: meaning is use)
- You catch missing concepts that appear prominently in documents
- You verify that definitions match real-world usage, not textbook
  definitions (Heidegger 1927: entities are encountered as equipment)
- You validate that competency questions match what users really need
  (Dewey 1938: pragmatic adequacy)

═══ YOUR FAILURE MODES (guard against these) ═══

- Over-reliance on surface text: important concepts may be implied
  rather than stated explicitly
- Missing implicit knowledge: domain practitioners share tacit
  understandings that documents may not spell out
- Uncritical acceptance: just because a term appears frequently does
  not mean the proposed formalisation is correct

═══ SCOPE BOUNDARY ═══

You do NOT critique ontology structure (that is the Critic's job).
You focus purely on DOMAIN ACCURACY and COMPLETENESS.

═══ GROUNDING CONSTRAINTS (always in effect) ═══

1. Every claim you make MUST cite document evidence.
2. If you suggest additions, provide the document passage that
   motivates them.
3. If a proposed element has NO document support, flag it explicitly.
4. Do not approve elements that seem plausible but lack evidence.
5. Prefer terminology that practitioners would recognise.
6. If uncertain about domain usage, say so. Do not fabricate.

Output must be valid JSON."""


REVIEW_PROMPT_TEMPLATE = """\
The Ontology Engineer has proposed the following for Phase {phase}:

```json
{proposal}
```

Domain documents for reference:

{documents}

Review this proposal from a DOMAIN EXPERT perspective:

1. ACCURACY: Do the proposed terms/definitions match how they're used
   in the documents?  Flag any misrepresentations.

2. COMPLETENESS: Are there important domain concepts MISSING from
   the proposal that appear in the documents?  List them.

3. TERMINOLOGY: Are the names/labels what a domain practitioner would
   actually use?  Suggest corrections.

4. EVIDENCE: For each issue, cite the relevant document text.

5. VERDICT: Do you approve this proposal for this phase?

Return JSON:
{{
  "approves": true|false,
  "accuracy_issues": [
    {{"term": "...", "issue": "...", "evidence": "..."}}
  ],
  "missing_concepts": [
    {{"concept": "...", "evidence": "...", "importance": "high|medium|low"}}
  ],
  "terminology_fixes": [
    {{"current": "...", "suggested": "...", "reason": "..."}}
  ],
  "overall_assessment": "...",
  "confidence": 0.0-1.0
}}"""


class DomainExpertAgent(BaseAgent):
    """Agent that validates proposals against domain documents.

    The DomainExpert is a *reviewer* — it checks the OntologyEngineer's
    proposals against evidence from the corpus and flags domain-accuracy
    issues.

    Parameters
    ----------
    settings:
        Application configuration.
    document_context:
        Pre-fetched document excerpts from Qdrant. This grounds the
        agent in real domain knowledge.
    """

    role = AgentRole.DOMAIN_EXPERT

    def __init__(
        self,
        settings: Settings | None = None,
        document_context: str = "",
    ) -> None:
        super().__init__(settings=settings, system_prompt=EXPERT_IDENTITY)
        self.document_context = document_context

    def set_documents(self, document_context: str) -> None:
        """Update the document context (e.g. between iterations)."""
        self.document_context = document_context

    def review(
        self,
        phase: Phase,
        proposal: dict[str, Any],
    ) -> AgentMessage:
        """Review a proposal from the OntologyEngineer.

        Args:
            phase: Current Ont-101 phase.
            proposal: The structured proposal to review.

        Returns:
            An ``AgentMessage`` with the review assessment.
        """
        user_prompt = REVIEW_PROMPT_TEMPLATE.format(
            phase=phase.value,
            proposal=json.dumps(proposal, indent=2, default=str),
            documents=self.document_context[:6000],
        )

        response = self.call_llm(user_prompt)

        # Parse the review
        issues: list[str] = []
        approves = True
        if response:
            approves = response.get("approves", True)
            for acc in response.get("accuracy_issues", []):
                issues.append(f"Accuracy: {acc.get('term', '?')} — {acc.get('issue', '')}")
            for mc in response.get("missing_concepts", []):
                issues.append(f"Missing: {mc.get('concept', '?')} (importance: {mc.get('importance', '?')})")
            for tf in response.get("terminology_fixes", []):
                issues.append(f"Rename: '{tf.get('current', '?')}' → '{tf.get('suggested', '?')}'")

        return AgentMessage(
            role=self.role,
            phase=phase,
            message_type="review",
            content=response or {},
            reasoning=response.get("overall_assessment", "") if response else "",
            issues_raised=issues,
            approves=approves,
        )

    def answer_question(self, question: str) -> AgentMessage:
        """Answer a domain-specific question from the engineer.

        Used when the engineer needs domain clarification during
        proposal generation (e.g., "Is X a type of Y in this domain?").

        Args:
            question: The domain question.

        Returns:
            An ``AgentMessage`` with the answer and evidence.
        """
        user_prompt = f"""Domain question from the Ontology Engineer:

{question}

Domain documents for reference:

{self.document_context[:6000]}

Answer this question based on the domain documents.  Provide:
1. Your answer
2. Evidence from the documents
3. Confidence level (0.0-1.0)

Return JSON:
{{
  "answer": "...",
  "evidence": ["..."],
  "confidence": 0.0-1.0,
  "notes": "..."
}}"""

        response = self.call_llm(user_prompt)

        return AgentMessage(
            role=self.role,
            phase=Phase.SCOPE,  # generic
            message_type="assessment",
            content=response or {},
            reasoning=response.get("answer", "") if response else "",
        )

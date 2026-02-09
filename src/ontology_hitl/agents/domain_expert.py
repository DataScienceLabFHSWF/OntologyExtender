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

Your role: you represent deep knowledge of the domain as evidenced by
the provided documents.  You review proposals from the Ontology Engineer
and validate them against REAL-WORLD usage in the domain.

Your strengths:
- You know what terms practitioners actually use
- You spot when the engineer invents abstract classes that don't
  reflect real domain concepts
- You catch missing concepts that appear prominently in documents
- You verify that definitions match how terms are used in practice
- You validate that competency questions capture what users really need

Your working style:
- You REVIEW proposals and flag issues with domain accuracy
- You provide EVIDENCE from the documents for your assessments
- You suggest ADDITIONS when important concepts are missing
- You flag TERMINOLOGY issues (wrong names, conflated concepts)
- You APPROVE proposals that faithfully represent the domain

You do NOT critique ontology structure (that's the Critic's job) —
you focus purely on domain accuracy and completeness.

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

"""Critic agent — quality reviewer and devil's advocate.

The Critic reviews proposals and debates between the OntologyEngineer
and DomainExpert.  It focuses on *structural quality* and *consistency*
rather than domain accuracy (that's the DomainExpert's job).

The Critic catches:
- Over-generalization or over-specification
- Redundant classes or properties
- Naming inconsistencies
- Missing disjointness declarations
- Hierarchy depth/breadth issues
- Proposals that don't actually help answer CQs
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from ontology_hitl.agents.base import AgentMessage, AgentRole, BaseAgent
from ontology_hitl.core.config import Settings
from ontology_hitl.methodology.ontology101 import Phase

logger = structlog.get_logger(__name__)


CRITIC_IDENTITY = """\
You are the CRITIC in a multi-agent ontology development team.

Your role: you are the quality gate.  You review proposals and the
debate between the Ontology Engineer and Domain Expert, focusing on
STRUCTURAL QUALITY and CONSISTENCY.

Your strengths:
- You spot over-generalization (classes too abstract to be useful)
- You catch redundancy (duplicate concepts under different names)
- You verify naming consistency (PascalCase classes, camelCase props)
- You check that the hierarchy follows Ont-101 structural rules
- You ensure every proposed element serves at least one competency question
- You identify missing disjointness declarations
- You flag when proposals are too ambitious or too conservative for the
  current iteration

Your working style:
- You are constructive but thorough — the devil's advocate
- You focus on STRUCTURAL and METHODOLOGICAL issues
- You do NOT question domain accuracy (that's the DomainExpert's job)
- You suggest concrete improvements, not vague criticisms
- You APPROVE only when the proposal is structurally sound
- When Engineer and Expert disagree, you provide a tiebreaker opinion

Output must be valid JSON."""


REVIEW_PROMPT_TEMPLATE = """\
Phase {phase} — Review the proposal and any prior discussion:

PROPOSAL from the Ontology Engineer:
```json
{proposal}
```

{prior_discussion}

Competency questions that should be answerable:
{competency_questions}

Review from a STRUCTURAL QUALITY perspective:

1. STRUCTURE: Does the hierarchy follow Ont-101 rules? (single-child,
   sibling consistency, depth, cycles, naming)

2. REDUNDANCY: Any duplicate or near-duplicate concepts?

3. CQ COVERAGE: Does every proposed element help answer at least
   one CQ?  Are there CQs that still can't be answered?

4. CONSISTENCY: Naming conventions, definition style, property
   attachment level — all consistent?

5. SCOPE CREEP: Is the proposal trying to do too much or too little
   for this iteration?

6. VERDICT: Do you approve?

Return JSON:
{{
  "approves": true|false,
  "structural_issues": [
    {{"type": "...", "element": "...", "issue": "...", "suggestion": "..."}}
  ],
  "redundancies": [
    {{"elements": ["...", "..."], "reason": "..."}}
  ],
  "uncovered_cqs": ["CQ_001", "CQ_003"],
  "consistency_issues": [
    {{"type": "naming|definition|attachment", "details": "..."}}
  ],
  "scope_assessment": "appropriate|too_broad|too_narrow",
  "overall_assessment": "...",
  "confidence": 0.0-1.0
}}"""


class CriticAgent(BaseAgent):
    """Agent that reviews structural quality and consistency.

    The Critic is a *reviewer* that focuses on methodology compliance,
    naming consistency, and ensuring the proposal serves the CQs.

    Parameters
    ----------
    settings:
        Application configuration.
    competency_questions:
        The CQs from Phase 1 — used to verify every element has a purpose.
    """

    role = AgentRole.CRITIC

    def __init__(
        self,
        settings: Settings | None = None,
        competency_questions: list[dict] | None = None,
    ) -> None:
        super().__init__(settings=settings, system_prompt=CRITIC_IDENTITY)
        self.competency_questions = competency_questions or []

    def set_competency_questions(self, cqs: list[dict]) -> None:
        """Update CQs (typically after Phase 1 completes)."""
        self.competency_questions = cqs

    def review(
        self,
        phase: Phase,
        proposal: dict[str, Any],
        prior_discussion: list[AgentMessage] | None = None,
    ) -> AgentMessage:
        """Review a proposal for structural quality.

        Args:
            phase: Current Ont-101 phase.
            proposal: The structured proposal to review.
            prior_discussion: Previous messages between Engineer and Expert.

        Returns:
            An ``AgentMessage`` with the quality assessment.
        """
        discussion_text = ""
        if prior_discussion:
            discussion_text = "Prior discussion:\n" + "\n\n".join(
                f"[{m.role.value}] ({m.message_type}):\n"
                f"Reasoning: {m.reasoning}\n"
                f"Issues: {'; '.join(m.issues_raised) if m.issues_raised else '(none)'}"
                for m in prior_discussion
            )

        cqs_text = json.dumps(self.competency_questions[:15], indent=2) \
            if self.competency_questions else "(not yet defined)"

        user_prompt = REVIEW_PROMPT_TEMPLATE.format(
            phase=phase.value,
            proposal=json.dumps(proposal, indent=2, default=str),
            prior_discussion=discussion_text,
            competency_questions=cqs_text,
        )

        response = self.call_llm(user_prompt)

        # Parse the review
        issues: list[str] = []
        approves = True
        if response:
            approves = response.get("approves", True)
            for si in response.get("structural_issues", []):
                issues.append(
                    f"Structure [{si.get('type', '?')}]: {si.get('element', '?')} "
                    f"— {si.get('issue', '')}; fix: {si.get('suggestion', '')}"
                )
            for r in response.get("redundancies", []):
                issues.append(
                    f"Redundancy: {', '.join(r.get('elements', []))} — {r.get('reason', '')}"
                )
            for ci in response.get("consistency_issues", []):
                issues.append(f"Consistency [{ci.get('type', '?')}]: {ci.get('details', '')}")

            uncovered = response.get("uncovered_cqs", [])
            if uncovered:
                issues.append(f"CQs not covered: {', '.join(uncovered)}")

        return AgentMessage(
            role=self.role,
            phase=phase,
            message_type="review",
            content=response or {},
            reasoning=response.get("overall_assessment", "") if response else "",
            issues_raised=issues,
            approves=approves,
        )

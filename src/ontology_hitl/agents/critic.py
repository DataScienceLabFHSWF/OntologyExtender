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

═══ EPISTEMIC IDENTITY ═══

Your epistemic stance is CRITICAL FALSIFICATION (Popper 1934).
You actively seek to REFUTE proposals rather than confirm them.
A proposal's quality is measured by its survival under rigorous
critique, not by the confidence of its proponent.

You embody Lakatos's (1970) refinement: you track whether the
ontology's evolution is *progressive* (extending coverage of CQs)
or *degenerating* (merely shifting problems around). You also
check claims against Guarino & Welty's (2002) OntoClean criteria.

═══ WHAT YOU DO ═══

- REVIEW proposals for structural quality and methodology compliance
- SEEK COUNTEREXAMPLES: what instances would break this hierarchy?
- CHECK FALSIFIABILITY: can this proposal be tested against CQs?
- DETECT REDUNDANCY: duplicate concepts under different names
- EVALUATE SCOPE: too ambitious or too conservative for this iteration?
- APPROVE only when structurally sound; reject with specific reasons

═══ YOUR STRENGTHS ═══

- Over-generalization detection: classes too abstract to be useful
- Redundancy detection: duplicate or near-duplicate concepts
- Naming consistency: PascalCase classes, camelCase properties
- Ont-101 structural rules: single-child, sibling consistency,
  depth/breadth balance, no cycles
- CQ coverage verification: every element must serve a CQ
- Missing disjointness declarations
- Complexity assessment: is the proposal proportionate to the need?

═══ YOUR FAILURE MODES (guard against these) ═══

- Being too conservative: blocking valid innovation because it is
  novel or unconventional
- Structural pedantry: enforcing rules that don't serve the domain
- Missing the forest for the trees: perfect structure but wrong content

═══ SCOPE BOUNDARY ═══

You do NOT question domain accuracy (that is the DomainExpert's job).
You focus on STRUCTURAL QUALITY and METHODOLOGICAL CONSISTENCY.
When Engineer and Expert disagree, you provide a tiebreaker opinion.
Irresolvable tensions are escalated honestly, not suppressed.

═══ GROUNDING CONSTRAINTS (always in effect) ═══

1. Flag any proposed element that serves NO competency question.
2. Flag any element that creates a single-child class or violates
   sibling consistency.
3. Check that the complexity budget is respected — are there too
   many new elements for one iteration?
4. Verify that extensions attach to the seed ontology.
5. If you approve, state specifically WHAT structural checks passed.
6. If you reject, provide the SPECIFIC rule or criterion violated.

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
        if isinstance(response, dict):
            approves = response.get("approves", True)
            for si in response.get("structural_issues", []):
                if isinstance(si, dict):
                    issues.append(
                        f"Structure [{si.get('type', '?')}]: {si.get('element', '?')} "
                        f"— {si.get('issue', '')}; fix: {si.get('suggestion', '')}"
                    )
                else:
                    issues.append(f"Structure issue: {str(si)}")
            
            for r in response.get("redundancies", []):
                if isinstance(r, dict):
                    elements = r.get('elements', [])
                    elements_str = ", ".join(elements) if isinstance(elements, list) else str(elements)
                    issues.append(f"Redundancy: {elements_str} — {r.get('reason', '')}")
                elif isinstance(r, list):
                    issues.append(f"Redundancy: {', '.join(map(str, r))}")
                else:
                    issues.append(f"Redundancy: {str(r)}")

            for ci in response.get("consistency_issues", []):
                if isinstance(ci, dict):
                    issues.append(f"Consistency [{ci.get('type', '?')}]: {ci.get('details', '')}")
                else:
                    issues.append(f"Consistency: {str(ci)}")

            uncovered = response.get("uncovered_cqs", [])
            if uncovered:
                # Handle cases where uncovered_cqs is a list of dicts instead of strings
                uncovered_labels = []
                for cq in uncovered:
                    if isinstance(cq, dict):
                        # Try to get id, then question, then label, then stringify
                        label = cq.get("id") or cq.get("question") or cq.get("label") or str(cq)
                        uncovered_labels.append(str(label))
                    else:
                        uncovered_labels.append(str(cq))
                issues.append(f"CQs not covered: {', '.join(uncovered_labels)}")

        return AgentMessage(
            role=self.role,
            phase=phase,
            message_type="review",
            content=response or {},
            reasoning=response.get("overall_assessment", "") if isinstance(response, dict) else str(response),
            issues_raised=issues,
            approves=approves,
        )

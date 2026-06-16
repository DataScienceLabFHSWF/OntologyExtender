"""Reasoner agent — formal logical consistency checker.

The Reasoner is the team's *logician*. Unlike the Critic (who reasons about
structural quality and methodology) the Reasoner runs an actual OWL reasoner
over each candidate extension and reports machine-verified logical defects:
unsatisfiable classes, disjointness violations, subclass cycles, and
domain/range conflicts.

Its verdict is **deterministic** — it approves a proposal only when the
materialised graph is logically consistent. The LLM is used solely to phrase
the findings into actionable guidance for the Engineer; the *decision* comes
from the reasoner, never from the model. This gives the debate a hard,
non-negotiable correctness signal that the other (LLM-judgement) agents lack.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from rdflib import Graph

from ontology_hitl.agents.base import AgentMessage, AgentRole, BaseAgent, ls_traceable
from ontology_hitl.core.config import Settings
from ontology_hitl.methodology.ontology101 import Phase
from ontology_hitl.reasoning import ConsistencyChecker, ConsistencyReport

logger = structlog.get_logger(__name__)


REASONER_IDENTITY = """\
You are the REASONER in a multi-agent ontology development team.

═══ EPISTEMIC IDENTITY ═══

Your epistemic stance is FORMAL LOGIC (Description Logic, Baader et al. 2017).
You do not argue about taste, domain nuance, or naming style. You verify
LOGICAL CONSISTENCY: whether the asserted axioms can have a model at all.

A class that is subsumed by two disjoint classes is UNSATISFIABLE — it can
never have an instance. A class disjoint with its own superclass is a
contradiction. Subclass cycles collapse distinct classes into equivalence.
These are not opinions; they are entailments.

═══ WHAT YOU DO ═══

- RECEIVE a structured report from an OWL reasoner run over the proposal.
- TRANSLATE each detected defect into clear, specific guidance the Ontology
  Engineer can act on (which axiom to drop, weaken, or rephrase).
- APPROVE only when the reasoner reports the graph is consistent.
- NEVER invent defects the reasoner did not find, and never approve a graph
  the reasoner flagged as inconsistent.

═══ SCOPE BOUNDARY ═══

You do NOT judge domain accuracy (DomainExpert) or structural style (Critic).
You judge ONLY logical satisfiability and consistency.

Output must be valid JSON."""


EXPLAIN_PROMPT_TEMPLATE = """\
Phase {phase} — An OWL reasoner analysed the current proposal.

REASONER VERDICT: {verdict}
Reasoner: {reasoner} | classes: {num_classes} | axioms: {num_axioms} | \
inferred triples: {inferred}

DETECTED LOGICAL ISSUES (authoritative — do not add or remove any):
```json
{issues}
```

For each issue, give the Engineer a concrete fix. Do not question the
reasoner's findings; explain and remediate them.

Return JSON:
{{
  "approves": {approves},
  "summary": "one-sentence logical assessment",
  "fixes": [
    {{"issue": "...", "affected": ["..."], "recommended_fix": "..."}}
  ]
}}"""


class ReasonerAgent(BaseAgent):
    """Agent that verifies logical consistency of ontology proposals.

    Parameters
    ----------
    settings:
        Application configuration.
    seed_ontology_path:
        Optional path to the seed ontology. When provided, proposals are
        merged with the seed before reasoning so cross-ontology
        contradictions (e.g. a new class disjoint with a seed class it also
        specialises) are caught.
    use_llm_explanations:
        If ``True`` (default), call the LLM to phrase remediation guidance.
        When ``False`` the agent returns the reasoner findings verbatim
        (faster, fully deterministic, no LLM dependency).
    """

    role = AgentRole.REASONER

    def __init__(
        self,
        settings: Settings | None = None,
        seed_ontology_path: str | Path | None = None,
        use_llm_explanations: bool = True,
    ) -> None:
        super().__init__(settings=settings, system_prompt=REASONER_IDENTITY)
        self.checker = ConsistencyChecker()
        self.use_llm_explanations = use_llm_explanations
        self._seed_graph: Graph | None = None
        if seed_ontology_path:
            try:
                g = Graph()
                g.parse(str(seed_ontology_path))
                self._seed_graph = g
                logger.info("reasoner_seed_loaded", triples=len(g))
            except Exception as e:
                logger.warning("reasoner_seed_load_failed", error=str(e))

    @ls_traceable(run_type="chain", name="Reasoner.review")
    def review(
        self,
        phase: Phase,
        proposal: dict[str, Any],
        prior_discussion: list[AgentMessage] | None = None,
    ) -> AgentMessage:
        """Run the reasoner over a proposal and return its verdict.

        The ``approves`` flag is set strictly from the reasoner's consistency
        result — the LLM cannot override it.
        """
        report = self.checker.check_proposal(proposal, seed_graph=self._seed_graph)
        approves = report.consistent
        issues = [i.to_dict() for i in report.issues]

        logger.info(
            "reasoner_review",
            phase=phase.value,
            consistent=report.consistent,
            errors=len(report.errors),
            warnings=len(report.warnings),
            reasoner=report.reasoner,
        )

        reasoning, issue_strings = self._format_findings(phase, report)

        return AgentMessage(
            role=AgentRole.REASONER,
            phase=phase,
            message_type="review",
            content={
                "approves": approves,
                "consistent": report.consistent,
                "report": report.to_dict(),
            },
            reasoning=reasoning,
            issues_raised=issue_strings,
            approves=approves,
        )

    def check(self, proposal: dict[str, Any]) -> ConsistencyReport:
        """Run a raw consistency check without producing an AgentMessage."""
        return self.checker.check_proposal(proposal, seed_graph=self._seed_graph)

    # ── Internal helpers ────────────────────────────────────────────

    def _format_findings(
        self,
        phase: Phase,
        report: ConsistencyReport,
    ) -> tuple[str, list[str]]:
        issue_strings = [
            f"{i.kind.value} [{i.severity}]: {i.message}" for i in report.issues
        ]

        if report.consistent and not report.issues:
            return ("Reasoner: proposal is logically consistent.", [])

        if not self.use_llm_explanations or not report.issues:
            verdict = "consistent" if report.consistent else "INCONSISTENT"
            return (f"Reasoner verdict: {verdict}.", issue_strings)

        try:
            user_prompt = EXPLAIN_PROMPT_TEMPLATE.format(
                phase=phase.value,
                verdict="CONSISTENT" if report.consistent else "INCONSISTENT",
                reasoner=report.reasoner,
                num_classes=report.num_classes,
                num_axioms=report.num_axioms,
                inferred=report.inferred_triples,
                issues=json.dumps([i.to_dict() for i in report.issues], indent=2),
                approves=str(report.consistent).lower(),
            )
            response = self.call_llm(user_prompt)
            if isinstance(response, dict) and response.get("summary"):
                fixes = response.get("fixes", [])
                fix_lines = [
                    f"Fix: {f.get('recommended_fix', '')}"
                    for f in fixes
                    if isinstance(f, dict) and f.get("recommended_fix")
                ]
                reasoning = str(response["summary"])
                return reasoning, issue_strings + fix_lines
        except Exception as e:  # pragma: no cover - LLM optional
            logger.debug("reasoner_llm_explain_failed", error=str(e))

        verdict = "consistent" if report.consistent else "INCONSISTENT"
        return (f"Reasoner verdict: {verdict}.", issue_strings)

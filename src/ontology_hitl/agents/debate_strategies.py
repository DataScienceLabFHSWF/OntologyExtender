"""Advanced debate strategies grounded in philosophy of knowledge.

This module implements sophisticated debate approaches for multi-agent
ontology development. Each strategy is rooted in a philosophical
tradition about how knowledge is produced, validated, and revised:

- **Dialectical** (Hegel): Thesis → Antithesis → Synthesis.
  Knowledge advances through productive contradiction.

- **Socratic** (Plato): Elenctic questioning that probes assumptions,
  evidence, and coherence across multiple epistemic dimensions.

- **Delphi** (Dalkey & Helmer): Anonymous iterative consensus.
  Reduces anchoring bias and groupthink through aggregation.

- **Abductive** (Peirce): Inference to the best explanation.
  Given surprising gaps, propose the hypothesis that makes them expected.

- **Consensus Building** (Habermas): Discourse ethics.
  All participants have equal standing; validity through challenge.

See ``epistemics.py`` for the full philosophical grounding.
"""

from __future__ import annotations

import random
from typing import Any, List

import structlog

from ontology_hitl.agents.base import (
    AgentMessage,
    AgentRole,
    Debate,
    DebateOutcome,
    DebateStrategy,
    DebateVerdict,
)
from ontology_hitl.agents.epistemics import (
    DIALECTICAL_ANTITHESIS_PROMPT,
    DIALECTICAL_SYNTHESIS_PROMPT,
    DIALECTICAL_THESIS_PROMPT,
    SOCRATIC_DIMENSIONS,
    EpistemicStance,
    KnowledgeStatus,
)
from ontology_hitl.methodology.ontology101 import AgentQuestion, Phase

logger = structlog.get_logger(__name__)


class DebateStrategist:
    """Implements different philosophical debate strategies."""

    def __init__(self, strategy: DebateStrategy = DebateStrategy.CONSENSUS_BUILDING):
        self.strategy = strategy

    def orchestrate_debate(
        self,
        debate: Debate,
        propose_func,
        review_funcs: dict[AgentRole, callable],
        revise_func,
    ) -> DebateOutcome:
        """Orchestrate a debate using the selected strategy."""

        if self.strategy == DebateStrategy.DIALECTICAL:
            return self._dialectical_debate(debate, propose_func, review_funcs, revise_func)
        elif self.strategy == DebateStrategy.SOCRATIC:
            return self._socratic_debate(debate, propose_func, review_funcs, revise_func)
        elif self.strategy == DebateStrategy.DELPHI:
            return self._delphi_debate(debate, propose_func, review_funcs, revise_func)
        elif self.strategy == DebateStrategy.ABDUCTIVE:
            return self._abductive_debate(debate, propose_func, review_funcs, revise_func)
        else:  # CONSENSUS_BUILDING
            return self._consensus_debate(debate, propose_func, review_funcs, revise_func)

    def _dialectical_debate(
        self,
        debate: Debate,
        propose_func,
        review_funcs: dict[AgentRole, callable],
        revise_func,
    ) -> DebateOutcome:
        """Hegelian dialectic: Thesis → Antithesis → Synthesis.

        Knowledge advances through productive contradiction (Hegel 1807).
        The thesis is not merely criticised but *sublated* (aufgehoben):
        its valid content is preserved while its limitations are overcome.

        The synthesis should be stronger than either position alone.
        Irresolvable tensions become HITL escalations — genuine
        underdetermination, not failure.
        """
        logger.info("dialectical_debate_start", phase=debate.phase.value)

        # ── Thesis: Engineer presents a defensible claim ───────────
        thesis = propose_func(debate.phase, DIALECTICAL_THESIS_PROMPT)
        debate.add_message(thesis)
        logger.info("dialectic_thesis", phase=debate.phase.value,
                     keys=list(thesis.content.keys()) if thesis.content else [])

        # ── Antithesis: Reviewers mount genuine counter-positions ──
        antithesis_messages = []
        for role, review_func in review_funcs.items():
            review = review_func(
                debate.phase, thesis.content,
                context=DIALECTICAL_ANTITHESIS_PROMPT,
            )
            antithesis_messages.append(review)
            debate.add_message(review)

        # ── Synthesis: Engineer reconciles thesis and antithesis ────
        criticisms = [msg for msg in antithesis_messages if msg.issues_raised]
        if criticisms:
            synthesis = revise_func(
                debate.phase,
                thesis.content,
                criticisms,
                context=DIALECTICAL_SYNTHESIS_PROMPT,
            )
            debate.add_message(synthesis)

            # ── Aufhebung check: is the synthesis genuinely higher? ─
            for role, review_func in review_funcs.items():
                final_review = review_func(
                    debate.phase, synthesis.content,
                    context=(
                        "Evaluate this SYNTHESIS. Does it genuinely resolve the "
                        "contradictions, or merely paper over them? Irresolvable "
                        "tensions should be explicitly stated for human review."
                    ),
                )
                debate.add_message(final_review)

        return self._determine_outcome(debate)

    def _socratic_debate(
        self,
        debate: Debate,
        propose_func,
        review_funcs: dict[AgentRole, callable],
        revise_func,
    ) -> DebateOutcome:
        """Socratic method: elenctic questioning across epistemic dimensions.

        The Socratic elenchus (Plato, Meno 80d-86c) proceeds by:
        1. Eliciting a clear claim from the interlocutor
        2. Examining it through targeted questioning
        3. Revealing hidden assumptions or contradictions
        4. Arriving at a more justified position — or honest aporia

        We extend this with multi-dimensional questioning drawn from
        five epistemic dimensions (see SOCRATIC_DIMENSIONS):
        ontological, epistemological, pragmatic, methodological, coherence.

        Each round selects a different dimension, ensuring the proposal
        is examined from all angles rather than fixating on one concern.
        """
        logger.info("socratic_debate_start", phase=debate.phase.value)

        # Elicit initial claim
        proposal = propose_func(
            debate.phase,
            "State your proposal clearly and precisely. What claim are you "
            "making about how the ontology should be structured, and why?",
        )
        debate.add_message(proposal)

        # Cycle through epistemic dimensions
        dimensions = list(SOCRATIC_DIMENSIONS.keys())
        for round_num in range(debate.max_rounds):
            # Select dimension for this round (cycle through them)
            dimension = dimensions[round_num % len(dimensions)]
            dim_questions = SOCRATIC_DIMENSIONS[dimension]

            # Each reviewer examines through a different question
            for i, (role, review_func) in enumerate(review_funcs.items()):
                question = dim_questions[i % len(dim_questions)]
                review = review_func(
                    debate.phase,
                    proposal.content,
                    context=(
                        f"SOCRATIC EXAMINATION — {dimension.upper()} dimension.\n\n"
                        f"Examine the proposal through this question:\n"
                        f"  \"{question}\"\n\n"
                        f"If the proposal cannot withstand this questioning, "
                        f"explain precisely why. If it can, show how."
                    ),
                )
                debate.add_message(review)

            # Check if proposal withstands examination
            recent = [m for m in debate.messages[-len(review_funcs):]
                      if m.approves is not None]
            if recent and all(r.approves for r in recent):
                logger.info("socratic_aporia_resolved", dimension=dimension,
                            round=round_num + 1)
                break

            # Revise in light of questioning
            if round_num < debate.max_rounds - 1:
                proposal = revise_func(
                    debate.phase,
                    proposal.content,
                    debate.messages[-len(review_funcs):],
                    context=(
                        "The Socratic examination has revealed issues. "
                        "Revise your proposal to address the questions raised. "
                        "If a question genuinely cannot be answered, state that "
                        "honestly — aporia (productive puzzlement) is a valid "
                        "outcome that leads to HITL escalation."
                    ),
                )
                debate.add_message(proposal)

        return self._determine_outcome(debate)

    def _delphi_debate(
        self,
        debate: Debate,
        propose_func,
        review_funcs: dict[AgentRole, callable],
        revise_func,
    ) -> DebateOutcome:
        """Delphi method: anonymous iterative expert consensus.

        The Delphi technique (Dalkey & Helmer 1963) achieves convergence
        by isolating individual judgements, aggregating them, then feeding
        the aggregate back for revision. This reduces:

        - **Anchoring bias**: reviewers don't see each other's initial opinions
        - **Bandwagon effects**: no social pressure toward early consensus
        - **Dominance effects**: no single agent's charisma drives the outcome

        The method converges when inter-reviewer agreement exceeds 80%.
        """
        logger.info("delphi_debate_start", phase=debate.phase.value)

        proposal = propose_func(debate.phase, "Provide your expert opinion")
        debate.add_message(proposal)

        for round_num in range(1, debate.max_rounds + 1):
            reviews = []
            for role, review_func in review_funcs.items():
                context = (
                    f"DELPHI ROUND {round_num}: Review independently. "
                    f"Do not consider how other reviewers might respond — "
                    f"focus only on your own expert judgement."
                )
                if round_num > 1:
                    prev_feedback = self._aggregate_feedback(
                        debate.messages[-len(review_funcs):]
                    )
                    context += (
                        f"\n\nAggregated anonymous feedback from previous round:\n"
                        f"{prev_feedback}\n\n"
                        f"Revise your position if the aggregate reveals something "
                        f"you missed, but do not conform merely to reach agreement."
                    )

                review = review_func(debate.phase, proposal.content, context=context)
                reviews.append(review)
                debate.add_message(review)

            if self._check_delphi_convergence(reviews):
                logger.info("delphi_converged", round=round_num)
                break

            if round_num < debate.max_rounds:
                aggregated = self._aggregate_feedback(reviews)
                proposal = revise_func(
                    debate.phase,
                    proposal.content,
                    reviews,
                    context=(
                        f"Incorporate aggregated anonymous feedback:\n{aggregated}\n\n"
                        f"Genuine disagreement is acceptable — do not force "
                        f"artificial consensus. State what remains contested."
                    ),
                )
                debate.add_message(proposal)

        return self._determine_outcome(debate)

    def _consensus_debate(
        self,
        debate: Debate,
        propose_func,
        review_funcs: dict[AgentRole, callable],
        revise_func,
    ) -> DebateOutcome:
        """Habermasian discourse ethics: communicative rationality.

        In the ideal speech situation (Habermas 1981), a claim is valid
        only if it could be accepted by all affected parties under
        conditions of free and equal discourse. We approximate this by:

        - Giving each agent equal voice (no hierarchy of authority)
        - Requiring explicit justification for every objection
        - Allowing revision without penalty (no sunk-cost bias)
        - Escalating only when genuine underdetermination persists
        """
        logger.info("consensus_debate_start", phase=debate.phase.value)

        proposal = propose_func(debate.phase, "")
        debate.add_message(proposal)

        for round_num in range(debate.max_rounds):
            reviews = []
            for role, review_func in review_funcs.items():
                review = review_func(debate.phase, proposal.content)
                reviews.append(review)
                debate.add_message(review)

            if debate.has_consensus:
                break

            if round_num < debate.max_rounds - 1:
                proposal = revise_func(debate.phase, proposal.content, reviews)
                debate.add_message(proposal)

        return self._determine_outcome(debate)

    # ── Abductive strategy (Peirce) ────────────────────────────────

    def _abductive_debate(
        self,
        debate: Debate,
        propose_func,
        review_funcs: dict[AgentRole, callable],
        revise_func,
    ) -> DebateOutcome:
        """Peircean abduction: inference to the best explanation.

        Given a surprising observation (gap entities that the ontology
        doesn't cover, CQs that can't be answered), propose the
        hypothesis (ontology extension) that would make these
        observations *expected*.

        The cycle is:
        1. State the surprising fact (the gap or unmet CQ)
        2. Propose an explanatory hypothesis (new class/relation)
        3. Examine whether the hypothesis actually explains the fact
        4. Compare with alternative hypotheses
        5. Select the most parsimonious adequate explanation

        This is closest to how scientists actually reason about
        extending a theory to accommodate new data.
        """
        logger.info("abductive_debate_start", phase=debate.phase.value)

        # Step 1–2: Propose explanatory hypothesis
        proposal = propose_func(
            debate.phase,
            "You have observed a GAP — entities or questions that the "
            "current ontology cannot handle. Propose the simplest ontology "
            "extension that would make this gap EXPECTED (i.e., that would "
            "naturally cover the previously uncoverable entities/CQs). "
            "State: (a) the surprising fact, (b) your hypothesis, "
            "(c) why this is the best explanation, not just *an* explanation.",
        )
        debate.add_message(proposal)

        for round_num in range(debate.max_rounds):
            # Step 3: Does the hypothesis actually explain the observation?
            for role, review_func in review_funcs.items():
                review = review_func(
                    debate.phase,
                    proposal.content,
                    context=(
                        "ABDUCTIVE EXAMINATION:\n"
                        "1. Does this hypothesis genuinely EXPLAIN the gap, "
                        "or merely describe it?\n"
                        "2. Is this the SIMPLEST adequate explanation "
                        "(Ockham's razor)?\n"
                        "3. What ALTERNATIVE hypotheses could explain the "
                        "same observations? Are they better?\n"
                        "4. Does this hypothesis generate NEW predictions "
                        "that we can check?"
                    ),
                )
                debate.add_message(review)

            recent = [m for m in debate.messages[-len(review_funcs):]
                      if m.approves is not None]
            if recent and all(r.approves for r in recent):
                break

            if round_num < debate.max_rounds - 1:
                proposal = revise_func(
                    debate.phase,
                    proposal.content,
                    debate.messages[-len(review_funcs):],
                    context=(
                        "Your hypothesis was challenged. Revise it to better "
                        "explain the observations, or propose an alternative "
                        "hypothesis that the reviewers will find more adequate."
                    ),
                )
                debate.add_message(proposal)

        return self._determine_outcome(debate)

    def _aggregate_feedback(self, reviews: List[AgentMessage]) -> str:
        """Aggregate feedback from multiple reviewers anonymously."""
        issues = []
        approvals = []

        for review in reviews:
            if review.issues_raised:
                issues.extend(review.issues_raised)
            if review.approves is not None:
                approvals.append("approved" if review.approves else "rejected")

        feedback = []
        if issues:
            feedback.append(f"Issues raised: {', '.join(issues[:3])}")  # Top 3 issues
        if approvals:
            approval_count = approvals.count("approved")
            feedback.append(f"Approval rate: {approval_count}/{len(approvals)}")

        return "; ".join(feedback)

    def _check_delphi_convergence(self, reviews: List[AgentMessage]) -> bool:
        """Check if Delphi method has converged (high agreement)."""
        approvals = [r.approves for r in reviews if r.approves is not None]
        if len(approvals) < 2:
            return False

        agreement_rate = sum(approvals) / len(approvals)
        return agreement_rate >= 0.8  # 80% agreement = convergence

    def _determine_outcome(self, debate: Debate) -> DebateOutcome:
        """Determine the final debate outcome."""
        latest_proposal = debate.latest_proposal or {}
        messages = debate.messages

        # Check for consensus
        recent_reviews = [m for m in messages[-3:] if m.message_type == "review"]  # Last 3 reviews
        if recent_reviews and all(m.approves for m in recent_reviews if m.approves is not None):
            return DebateOutcome(
                phase=debate.phase,
                verdict=DebateVerdict.CONSENSUS,
                final_proposal=latest_proposal,
                messages=messages,
                rounds=len([m for m in messages if m.message_type == "proposal"]),
            )

        # Check for revisions
        revisions = [m for m in messages if m.message_type == "revision"]
        if revisions:
            return DebateOutcome(
                phase=debate.phase,
                verdict=DebateVerdict.REVISED,
                final_proposal=latest_proposal,
                messages=messages,
                rounds=len(revisions) + 1,
            )

        # Escalate if no resolution
        escalated_questions = [
            AgentQuestion(
                phase=debate.phase,
                question="Agents could not reach consensus on this proposal. Human review needed.",
                context=f"Debate strategy: {debate.strategy.value}, Rounds: {debate.max_rounds}"
            )
        ]

        return DebateOutcome(
            phase=debate.phase,
            verdict=DebateVerdict.ESCALATED,
            final_proposal=latest_proposal,
            messages=messages,
            escalated_questions=escalated_questions,
            rounds=debate.max_rounds,
        )
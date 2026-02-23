"""AgentTeam — orchestrates multi-agent debates for each Ont-101 phase.

The team manages the structured debate pattern:
    1. OntologyEngineer PROPOSES
    2. DomainExpert REVIEWS (domain accuracy)
    3. Critic REVIEWS (structural quality)
    4. If issues raised → OntologyEngineer REVISES
    5. Re-review until consensus or max rounds
    6. Unresolved issues → escalated as AgentQuestions for HITL

This replaces the single-agent pipeline with a collaborative process
that produces higher-quality ontologies with less human intervention.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from ontology_hitl.agents.base import (
    AgentMessage,
    AgentRole,
    Debate,
    DebateOutcome,
    DebateVerdict,
    AgentPerformanceMetrics,
)
from ontology_hitl.agents.ontology_engineer import OntologyEngineerAgent
from ontology_hitl.agents.domain_expert import DomainExpertAgent
from ontology_hitl.agents.critic import CriticAgent
from ontology_hitl.core.config import Settings
from ontology_hitl.methodology.ontology101 import AgentQuestion, Phase
from ontology_hitl.sources.law_collection_source import LawCollectionSource
from ontology_hitl.sources.law_graph_source import LawGraphSource

logger = structlog.get_logger(__name__)


class AgentTeam:
    """Orchestrates multi-agent collaboration for ontology development.

    The team consists of three agents:
    - **OntologyEngineer**: proposes ontology artefacts
    - **DomainExpert**: validates against document evidence
    - **Critic**: checks structural quality and consistency

    Optionally enriched with literature-inspired modules:
    - **FeedbackLearner** (F): augments prompts with HITL history
    - **ProvenanceTracker** (D): records evidence citations from debates

    Parameters
    ----------
    settings:
        Application configuration (Ollama URL, model, etc.).
    document_context:
        Domain document excerpts from Qdrant.
    max_debate_rounds:
        Maximum propose→review→revise cycles per phase (default 2).
    output_dir:
        Where to persist debate transcripts.
    feedback_learner:
        Optional FeedbackLearner for prompt augmentation.
    provenance:
        Optional ProvenanceTracker for evidence recording.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        document_context: str = "",
        max_debate_rounds: int = 2,
        output_dir: Path | None = None,
        feedback_learner: "FeedbackLearner | None" = None,
        provenance: "ProvenanceTracker | None" = None,
    ) -> None:
        self.settings = settings or Settings()
        self.max_debate_rounds = max_debate_rounds
        self.output_dir = output_dir
        self.feedback_learner = feedback_learner
        self.provenance = provenance

        # Performance analytics
        self.performance_metrics: dict[AgentRole, AgentPerformanceMetrics] = {
            AgentRole.ONTOLOGY_ENGINEER: AgentPerformanceMetrics(AgentRole.ONTOLOGY_ENGINEER),
            AgentRole.DOMAIN_EXPERT: AgentPerformanceMetrics(AgentRole.DOMAIN_EXPERT),
            AgentRole.CRITIC: AgentPerformanceMetrics(AgentRole.CRITIC),
        }

        # Create agents
        law_collection: LawCollectionSource | None = None
        law_graph: LawGraphSource | None = None
        if self.settings.legal_enrichment_enabled:
            law_collection = LawCollectionSource(
                qdrant_url=self.settings.qdrant_url,
                law_collection="lawgraph",  # Dedicated legal documents collection
            )
            law_graph = LawGraphSource(
                graph_url=self.settings.neo4j_http_url,
                graph_user=self.settings.neo4j_username,
                graph_password=self.settings.neo4j_password,
            )
        
        self.engineer = OntologyEngineerAgent(settings=self.settings)
        self.domain_expert = DomainExpertAgent(
            settings=self.settings,
            document_context=document_context,
            law_collection=law_collection,
            law_graph=law_graph,
        )
        self.critic = CriticAgent(settings=self.settings)

    def set_document_context(self, context: str) -> None:
        """Update document context for the DomainExpert."""
        self.domain_expert.set_documents(context)

    def set_competency_questions(self, cqs: list[dict]) -> None:
        """Forward CQs to the Critic for evaluation-aware reviews."""
        self.critic.set_competency_questions(cqs)

    def get_performance_analytics(self) -> dict[str, Any]:
        """Get comprehensive performance analytics for all agents."""
        return {
            role.value: {
                "total_debates": metrics.total_debates,
                "consensus_contributions": metrics.consensus_contributions,
                "revisions_requested": metrics.revisions_requested,
                "escalations_caused": metrics.escalations_caused,
                "avg_response_time": metrics.avg_response_time,
                "issues_raised_per_debate": metrics.issues_raised_per_debate,
                "approval_rate": metrics.approval_rate,
                "debate_participation": metrics.debate_participation,
            }
            for role, metrics in self.performance_metrics.items()
        }

    # ── Main debate orchestration ───────────────────────────────────

    def run_debate(
        self,
        phase: Phase,
        context: str,
    ) -> DebateOutcome:
        """Run a structured debate for a single Ont-101 phase.

        Flow:
            1. Engineer proposes
            2. Expert + Critic review (in parallel conceptually)
            3. If issues → Engineer revises
            4. Expert + Critic re-review
            5. Repeat until consensus or max rounds
            6. Produce DebateOutcome

        Args:
            phase: The Ont-101 phase to debate.
            context: Formatted context string for the engineer's prompt.

        Returns:
            ``DebateOutcome`` with the final proposal and any escalations.
        """
        logger.info("debate_start", phase=phase.value, max_rounds=self.max_debate_rounds)
        debate = Debate(phase=phase, max_rounds=self.max_debate_rounds)

        # Module F: Augment context with feedback learner history
        augmented_context = context
        if self.feedback_learner:
            try:
                augmented_context = self.feedback_learner.augment_prompt(
                    context, phase=phase.value,
                )
            except Exception as e:
                logger.warning("feedback_augmentation_failed", error=str(e))

        # Round 1: Engineer proposes
        proposal_msg = self.engineer.propose(phase, augmented_context)
        debate.add_message(proposal_msg)

        # Module D: Record provenance from proposal
        if self.provenance and proposal_msg.content:
            try:
                for key in ("nodes", "terms", "properties"):
                    for item in proposal_msg.content.get(key, []):
                        label = item.get("label", item.get("name", item.get("term", "")))
                        uri = item.get("uri", f"plan:{label}")
                        if label:
                            self.provenance.record_from_agent_message(
                                element_uri=uri,
                                element_label=label,
                                agent_content=item,
                                agent_role="ontology_engineer",
                                phase=phase.value,
                            )
            except Exception as e:
                logger.debug("provenance_record_failed", error=str(e))

        if not proposal_msg.content:
            logger.warning("engineer_proposal_empty", phase=phase.value)
            return DebateOutcome(
                phase=phase,
                verdict=DebateVerdict.ESCALATED,
                final_proposal={},
                messages=debate.messages,
                escalated_questions=[AgentQuestion(
                    phase=phase,
                    question=f"The Ontology Engineer couldn't generate a proposal for {phase.value}. Manual input needed.",
                    context="LLM call returned empty response",
                )],
            )

        logger.info("engineer_proposed", phase=phase.value,
                     keys=list(proposal_msg.content.keys()) if isinstance(proposal_msg.content, dict) and proposal_msg.content else [])

        # Review rounds
        for round_num in range(1, self.max_debate_rounds + 1):
            current_proposal = debate.latest_proposal or {}

            # DomainExpert reviews
            expert_review = self.domain_expert.review(phase, current_proposal)
            debate.add_message(expert_review)

            # Critic reviews (sees expert's review too)
            critic_review = self.critic.review(
                phase, current_proposal,
                prior_discussion=[m for m in debate.messages if m.role != AgentRole.CRITIC],
            )
            debate.add_message(critic_review)

            logger.info(
                "reviews_complete",
                phase=phase.value,
                round=round_num,
                expert_approves=expert_review.approves,
                critic_approves=critic_review.approves,
                expert_issues=len(expert_review.issues_raised),
                critic_issues=len(critic_review.issues_raised),
            )

            # Check for consensus
            if debate.has_consensus:
                logger.info("consensus_reached", phase=phase.value, round=round_num)
                return self._build_outcome(
                    debate, DebateVerdict.CONSENSUS, round_num,
                )

            # If not last round, let engineer revise
            if round_num < self.max_debate_rounds:
                feedback = [expert_review, critic_review]
                revision = self.engineer.revise(
                    phase, current_proposal, feedback, context,
                )
                debate.add_message(revision)
                logger.info("engineer_revised", phase=phase.value, round=round_num)

        # Max rounds reached — determine outcome
        return self._finalize_debate(debate)

    # ── Phase-specific context builders ─────────────────────────────

    def build_scope_context(
        self,
        docs_text: str,
        seed_classes: str,
    ) -> str:
        """Build context for Phase 1: Scope."""
        return f"""Domain documents (excerpts):

{docs_text[:4000]}

Current seed ontology classes: {seed_classes}

Generate:
1. A 1-2 sentence domain description
2. A 1-2 sentence purpose statement
3. A list of intended users
4. 10-15 competency questions (CQs) with:
   - id, question, expected_entity_types, expected_relations, difficulty (1-5)
5. A list of topics explicitly out of scope

Return JSON:
{{
  "domain": "...",
  "purpose": "...",
  "intended_users": ["..."],
  "competency_questions": [{{...}}],
  "out_of_scope": ["..."]
}}"""

    def build_reuse_context(
        self,
        seed_cls: str,
        seed_props: str,
        term_preview: str,
        cqs_text: str,
    ) -> str:
        """Build context for Phase 2: Reuse."""
        return f"""Seed ontology classes and properties:
Classes: {seed_cls}
Properties: {seed_props}

Domain terms extracted (preliminary):
{term_preview}

Competency questions from Phase 1:
{cqs_text}

For each uncovered term cluster, decide: import / extend / reference / skip.
Justify each decision based on which CQs require those terms.

Return JSON:
{{
  "terms_already_covered": ["..."],
  "terms_still_needed": ["..."],
  "reuse_candidates": [
    {{
      "ontology_name": "...",
      "uri": "...",
      "overlap_terms": ["..."],
      "decision": "import|extend|reference|skip",
      "rationale": "..."
    }}
  ]
}}"""

    def build_terms_context(
        self,
        docs_text: str,
        seed_classes: str,
    ) -> str:
        """Build context for Phase 3: Terms."""
        return f"""Document excerpts from the domain:

{docs_text[:6000]}

Current ontology classes for reference: {seed_classes}

Extract ALL important domain terms.  For each term:
- term, category (class/property/relation/instance/unknown)
- frequency estimate (how often it appears)
- synonyms (different words for the same concept)
- 1-2 evidence snippets

Return JSON:
{{
  "terms": [
    {{
      "term": "...",
      "category": "class|property|relation|instance|unknown",
      "frequency": N,
      "synonyms": ["..."],
      "evidence": ["..."]
    }}
  ]
}}"""

    def build_hierarchy_context(
        self,
        seed_hierarchy: str,
        class_terms: list[str],
        cqs_text: str,
    ) -> str:
        """Build context for Phase 4: Hierarchy."""
        return f"""Seed ontology class hierarchy:
{seed_hierarchy}

Terms categorized as classes (from Phase 3):
{', '.join(class_terms)}

Competency questions that need these classes:
{cqs_text}

Build a class hierarchy.  For each NEW class:
- label (PascalCase, singular)
- definition (1-2 sentences)
- parent class (from seed or newly created)
- disjoint_with (mutually exclusive classes)
- strategy: top-down / bottom-up / middle-out
- examples: 2-3 instance examples

Return JSON:
{{
  "nodes": [
    {{
      "uri": "plan:ClassName",
      "label": "ClassName",
      "definition": "...",
      "parent_uri": "plan:ParentClass",
      "parent_label": "ParentClass",
      "disjoint_with": ["plan:OtherClass"],
      "examples": ["instance1", "instance2"],
      "strategy": "middle-out"
    }}
  ]
}}"""

    def build_properties_context(
        self,
        hierarchy_text: str,
        prop_terms: list[str],
        rel_terms: list[str],
        docs_text: str,
    ) -> str:
        """Build context for Phase 5: Properties."""
        return f"""Class hierarchy from Phase 4:
{hierarchy_text}

Terms categorized as properties/relations (from Phase 3):
Properties: {', '.join(prop_terms)}
Relations: {', '.join(rel_terms)}

Document evidence:
{docs_text[:3000]}

For each property:
- name (camelCase), attached_to_class (most general), property_type,
  datatype/range_class, inverse_name, description, inherited_by

Return JSON:
{{
  "properties": [
    {{
      "name": "...",
      "attached_to_class": "...",
      "property_type": "datatype|object",
      "description": "...",
      "inherited_by": ["..."]
    }}
  ]
}}"""

    def build_facets_context(
        self,
        properties_text: str,
        hierarchy_text: str,
    ) -> str:
        """Build context for Phase 6: Facets."""
        return f"""Properties from Phase 5:
{properties_text}

Class hierarchy from Phase 4:
{hierarchy_text}

For each property, specify constraints:
- min_count, max_count, value_type, allowed_values, pattern, rationale

Return JSON:
{{
  "facets": [
    {{
      "property_name": "...",
      "on_class": "...",
      "min_count": null,
      "max_count": null,
      "value_type": "xsd:string",
      "allowed_values": null,
      "rationale": "..."
    }}
  ]
}}"""

    def build_instances_context(
        self,
        classes_text: str,
        props_text: str,
        facets_text: str,
        cqs_text: str,
        docs_text: str,
    ) -> str:
        """Build context for Phase 7: Instances."""
        return f"""Full ontology spec:
Classes: {classes_text}
Properties: {props_text}
Constraints: {facets_text}

Competency questions:
{cqs_text}

Document excerpts (for creating realistic instances):
{docs_text[:3000]}

1. Create 5-10 TEST INSTANCES from the domain documents.
2. For each CQ, determine answerability + SPARQL sketch.

Return JSON:
{{
  "test_instances": [
    {{
      "class_label": "...",
      "property_values": {{}},
      "representable": true,
      "issues": []
    }}
  ],
  "cq_results": [
    {{
      "cq_id": "...",
      "question": "...",
      "answerable": true,
      "required_classes": ["..."],
      "required_properties": ["..."],
      "missing_elements": [],
      "sparql_sketch": "SELECT ..."
    }}
  ]
}}"""

    # ── Internal helpers ────────────────────────────────────────────

    def _finalize_debate(self, debate: Debate) -> DebateOutcome:
        """Determine outcome when max rounds are reached.

        If at least one reviewer still disapproves, escalate their
        unresolved issues to HITL.  Otherwise treat as revised.
        """
        latest = debate.latest_proposal or {}
        unresolved = debate.unresolved_issues

        if not unresolved:
            # Reviewers had issues but they were addressed in revisions
            return self._build_outcome(debate, DebateVerdict.REVISED, debate.max_rounds)

        # Escalate unresolved issues
        escalated = []
        for issue in unresolved:
            escalated.append(AgentQuestion(
                phase=debate.phase,
                question=issue,
                context=f"Unresolved after {debate.max_rounds} debate rounds",
                auto_resolved=False,
            ))

        verdict = (
            DebateVerdict.PARTIAL if len(escalated) < 3
            else DebateVerdict.ESCALATED
        )

        return DebateOutcome(
            phase=debate.phase,
            verdict=verdict,
            final_proposal=latest,
            messages=debate.messages,
            resolved_issues=[
                i for i in self._all_raised_issues(debate) if i not in unresolved
            ],
            escalated_questions=escalated,
            rounds=debate.max_rounds,
        )

    def _build_outcome(
        self,
        debate: Debate,
        verdict: DebateVerdict,
        rounds: int,
    ) -> DebateOutcome:
        """Build a DebateOutcome from a completed debate."""
        return DebateOutcome(
            phase=debate.phase,
            verdict=verdict,
            final_proposal=debate.latest_proposal or {},
            messages=debate.messages,
            resolved_issues=self._all_raised_issues(debate),
            escalated_questions=[],
            rounds=rounds,
        )

    @staticmethod
    def _all_raised_issues(debate: Debate) -> list[str]:
        """Collect all issues raised across all reviews."""
        issues: list[str] = []
        for msg in debate.messages:
            if msg.message_type == "review":
                issues.extend(msg.issues_raised)
        return issues

    def save_debate(self, outcome: DebateOutcome) -> None:
        """Persist a debate transcript for reproducibility."""
        if not self.output_dir:
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"debate_{outcome.phase.value}.json"

        data = {
            "phase": outcome.phase.value,
            "verdict": outcome.verdict.value,
            "rounds": outcome.rounds,
            "resolved_issues": outcome.resolved_issues,
            "escalated_questions": [
                {"question": q.question, "context": q.context}
                for q in outcome.escalated_questions
            ],
            "messages": [
                {
                    "role": m.role.value,
                    "type": m.message_type,
                    "approves": m.approves,
                    "issues": m.issues_raised,
                    "reasoning": m.reasoning[:500],
                }
                for m in outcome.messages
            ],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.debug("debate_saved", phase=outcome.phase.value, path=str(path))

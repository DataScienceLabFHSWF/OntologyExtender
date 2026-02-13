"""Ont-101 pipeline runner — multi-agent 7-phase methodology.

Three specialised agents collaborate to build ontologies following
Noy & McGuinness (2001):

- **OntologyEngineer** — proposes artefacts at each phase
- **DomainExpert** — validates against document evidence
- **Critic** — checks structural quality and methodology compliance

Each phase runs as a *debate*: the Engineer proposes, the Expert and
Critic review, the Engineer revises, until consensus or HITL escalation.

Integration
-----------
The ``FeedbackLoopOrchestrator`` calls ``Ont101Pipeline.run_iteration()``
which in turn uses ``AgentTeam.run_debate()`` for each phase.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from ontology_hitl.agents.team import AgentTeam
from ontology_hitl.agents.base import DebateVerdict, ls_traceable
from ontology_hitl.core.config import Settings
from ontology_hitl.discovery.entity_linker import EntityLinker
from ontology_hitl.discovery.embedding_advisor import EmbeddingAdvisor
from ontology_hitl.discovery.ensemble_strategy import (
    EnsembleStrategy,
    StrategyName,
    StrategyVote,
)
from ontology_hitl.evaluation.provenance import ProvenanceTracker
from ontology_hitl.evaluation.feedback_learner import FeedbackLearner
from ontology_hitl.schema.seed_manager import SeedProtectedOntology
from ontology_hitl.methodology.ontology101 import (
    AgentQuestion,
    CQTestResult,
    ClassHierarchy,
    DomainTerm,
    FacetReport,
    FacetSpec,
    HierarchyNode,
    Ont101Iteration,
    OntologyScope,
    Phase,
    PropertyProposal,
    ReuseCandidate,
    ReuseReport,
    TermEnumeration,
    SampleInstance,
    ValidationReport,
)
from ontology_hitl.methodology.validation_rules import (
    validate_hierarchy,
)

logger = structlog.get_logger(__name__)


class Ont101Pipeline:
    """Execute one iteration of the 7-phase Ontology 101 methodology.

    Uses a multi-agent team (OntologyEngineer, DomainExpert, Critic)
    to collaboratively build each phase artefact through structured
    debates.

    Each phase:
    1. Builds context from previous phases + external data
    2. Runs a multi-agent debate (propose → review → revise)
    3. Parses the consensus proposal into typed artefacts
    4. Runs Ont-101 validation rules
    5. Escalates unresolved issues as ``AgentQuestion`` items

    Parameters
    ----------
    settings:
        Application configuration (Qdrant URL, Ollama URL, etc.).
    iteration:
        Current iteration number (affects prompt context).
    output_dir:
        Where to persist phase artefacts for reproducibility.
    max_debate_rounds:
        Maximum propose→review→revise cycles per phase.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        iteration: int = 1,
        output_dir: Path | None = None,
        max_debate_rounds: int = 2,
        seed_manager: SeedProtectedOntology | None = None,
        provenance: ProvenanceTracker | None = None,
        feedback_learner: FeedbackLearner | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.iteration = iteration
        self.output_dir = output_dir or Path(self.settings.iterations_dir) / f"v{iteration}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_debate_rounds = max_debate_rounds

        # Accumulated artefacts
        self.result = Ont101Iteration(iteration=iteration)

        # Agent team (created lazily with document context)
        self._team: AgentTeam | None = None

        # Literature-inspired modules (A–F)
        self.seed_manager = seed_manager
        self.provenance = provenance if provenance is not None else (
            ProvenanceTracker(settings=self.settings)
            if self.settings.provenance_enabled else None
        )
        self.feedback_learner = feedback_learner if feedback_learner is not None else (
            FeedbackLearner(
                max_few_shot=self.settings.feedback_max_few_shot,
                memory_path=Path(self.settings.feedback_memory_path),
            )
            if self.settings.feedback_learning_enabled else None
        )
        self.entity_linker: EntityLinker | None = (
            EntityLinker(
                settings=self.settings,
                similarity_threshold=self.settings.entity_linking_threshold,
            )
            if self.settings.entity_linking_enabled else None
        )
        self.embedding_advisor: EmbeddingAdvisor | None = (
            EmbeddingAdvisor(settings=self.settings)
            if self.settings.embedding_advisor_enabled else None
        )
        self.ensemble: EnsembleStrategy | None = (
            EnsembleStrategy(
                settings=self.settings,
                weights={
                    StrategyName.LLM: self.settings.ensemble_weight_llm,
                    StrategyName.EMBEDDING: self.settings.ensemble_weight_embedding,
                    StrategyName.COOCCURRENCE: self.settings.ensemble_weight_cooccurrence,
                },
            )
            if self.settings.ensemble_enabled else None
        )

    # ── Main entry point ────────────────────────────────────────────

    def _get_team(self, docs_text: str) -> AgentTeam:
        """Get or create the agent team with document context."""
        if self._team is None:
            self._team = AgentTeam(
                settings=self.settings,
                document_context=docs_text,
                max_debate_rounds=self.max_debate_rounds,
                output_dir=self.output_dir,
                feedback_learner=self.feedback_learner,
                provenance=self.provenance,
            )
        else:
            self._team.set_document_context(docs_text)
        return self._team

    @ls_traceable(run_type="chain", name="Ont101Pipeline.run_iteration")
    def run_iteration(
        self,
        document_excerpts: list[str] | None = None,
        seed_classes: list[str] | None = None,
        seed_properties: list[str] | None = None,
        seed_hierarchy: str | None = None,
        previous_iteration: Ont101Iteration | None = None,
    ) -> Ont101Iteration:
        """Run all 7 phases as multi-agent debates.

        Args:
            document_excerpts: Text chunks from Qdrant.
            seed_classes: Existing ontology class labels.
            seed_properties: Existing ontology property names.
            seed_hierarchy: Text representation of current hierarchy.
            previous_iteration: Results from the prior iteration.

        Returns:
            ``Ont101Iteration`` with all phase artefacts and questions.
        """
        logger.info("ont101_iteration_start", iteration=self.iteration)

        docs_text = "\n\n---\n\n".join(document_excerpts or ["(no documents provided)"])
        seed_cls = ", ".join(seed_classes or ["(none)"])
        seed_props = ", ".join(seed_properties or ["(none)"])
        seed_hier = seed_hierarchy or "(no hierarchy provided)"

        team = self._get_team(docs_text)

        # Phase 1: Scope & CQs
        self.result.scope = self._run_phase_scope(team, docs_text, seed_cls)

        # Update Critic with CQs from Phase 1
        if self.result.scope and self.result.scope.competency_questions:
            team.set_competency_questions(self.result.scope.competency_questions)

        # Phase 2: Reuse
        cqs_text = json.dumps(
            self.result.scope.competency_questions[:10], indent=2
        ) if self.result.scope else "[]"
        term_preview = self._quick_term_extract(docs_text)
        self.result.reuse = self._run_phase_reuse(
            team, seed_cls, seed_props, term_preview, cqs_text,
        )

        # ── Module B: Entity Linking (after reuse, before terms) ────
        if self.entity_linker and self.result.reuse:
            try:
                link_labels = self.result.reuse.terms_still_needed[:20]
                if link_labels:
                    link_report = self.entity_linker.link_classes(link_labels)
                    self._save_phase("2b_entity_links", {
                        "total_proposed": len(link_labels),
                        "linked_count": len(link_report.links),
                        "coverage_pct": link_report.coverage_pct,
                        "links": [
                            {"label": lk.proposed_label, "match": lk.external_label,
                             "uri": lk.external_uri, "source": lk.ontology_source,
                             "similarity": lk.similarity_score}
                            for lk in link_report.links
                        ],
                    })
                    logger.info(
                        "entity_linking_done",
                        linked=len(link_report.links),
                        total=len(link_labels),
                    )
            except Exception as e:
                logger.warning("entity_linking_failed", error=str(e))

        # Phase 3: Term enumeration
        self.result.terms = self._run_phase_terms(team, docs_text, seed_cls)

        # Phase 4: Class hierarchy
        class_terms = [
            t.term for t in (self.result.terms.terms if self.result.terms else [])
            if t.category == "class"
        ]
        self.result.hierarchy = self._run_phase_hierarchy(
            team, seed_hier, class_terms, cqs_text,
        )

        # ── Module C+E: Embedding Advisor + Ensemble (after hierarchy) ──
        if self.result.hierarchy and self.result.hierarchy.nodes:
            self._run_embedding_ensemble(
                class_terms, seed_classes or [], document_excerpts or [],
            )

        # Run Ont-101 validation on hierarchy
        if self.result.hierarchy:
            issues = validate_hierarchy(self.result.hierarchy)
            for issue in issues:
                self.result.questions.append(AgentQuestion(
                    phase=Phase.HIERARCHY,
                    question=issue.message,
                    context=f"[{issue.rule}] {issue.ont101_section}",
                    options=[issue.suggestion] if issue.suggestion else [],
                    auto_resolved=False,
                ))

        # Phase 5: Properties
        prop_terms = [
            t.term for t in (self.result.terms.terms if self.result.terms else [])
            if t.category == "property"
        ]
        rel_terms = [
            t.term for t in (self.result.terms.terms if self.result.terms else [])
            if t.category == "relation"
        ]
        self.result.properties = self._run_phase_properties(
            team, self.result.hierarchy, prop_terms, rel_terms, docs_text,
        )

        # Re-validate with properties
        if self.result.hierarchy and self.result.properties:
            prop_issues = validate_hierarchy(
                self.result.hierarchy, self.result.properties,
            )
            for issue in prop_issues:
                if issue.rule == "property-redundant-attachment":
                    self.result.questions.append(AgentQuestion(
                        phase=Phase.PROPERTIES,
                        question=issue.message,
                        context=f"[{issue.rule}] {issue.ont101_section}",
                        options=[issue.suggestion] if issue.suggestion else [],
                        auto_resolved=False,
                    ))

        # Phase 6: Facets
        self.result.facets = self._run_phase_facets(
            team, self.result.properties, self.result.hierarchy,
        )

        # Phase 7: Instance validation
        self.result.validation = self._run_phase_instances(
            team,
            self.result.hierarchy,
            self.result.properties,
            self.result.facets,
            self.result.scope,
            docs_text,
        )

        # Persist entire iteration
        self._save_iteration()

        # ── Module D: Provenance export ─────────────────────────────
        if self.provenance:
            try:
                prov_report = self.provenance.report()
                self._save_phase("provenance", self.provenance.to_json())
                logger.info(
                    "provenance_exported",
                    records=len(prov_report.records),
                    elements=prov_report.elements_with_evidence,
                )
            except Exception as e:
                logger.warning("provenance_export_failed", error=str(e))

        # Module F: feedback memory is auto-persisted on each record()

        logger.info(
            "ont101_iteration_complete",
            iteration=self.iteration,
            questions=len(self.result.questions),
            new_classes=self.result.hierarchy.new_classes_count if self.result.hierarchy else 0,
            cq_coverage=self.result.validation.cq_coverage_pct if self.result.validation else 0,
        )

        return self.result

    # ── Literature-inspired integration helpers ───────────────────

    def _run_embedding_ensemble(
        self,
        class_terms: list[str],
        seed_classes: list[str],
        document_excerpts: list[str],
    ) -> None:
        """Run embedding advisor and ensemble voting for hierarchy refinement.

        This enriches the hierarchy from Phase 4 with:
        - Module C: Embedding-based parent recommendations
        - Module E: Ensemble voting (LLM + Embedding + Co-occurrence)

        Results are saved as supplementary artefacts alongside the hierarchy.
        """
        hierarchy = self.result.hierarchy
        if not hierarchy:
            return

        proposed = [
            {"label": n.label, "definition": n.definition}
            for n in hierarchy.nodes if not n.is_from_seed
        ]
        if not proposed:
            return

        # Module C: Embedding Advisor
        embedding_votes: list[StrategyVote] = []
        if self.embedding_advisor:
            try:
                # Index seed classes
                seed_dicts = [
                    {"uri": f"seed:{lbl}", "label": lbl, "definition": ""}
                    for lbl in seed_classes
                ]
                # Also include seed nodes from hierarchy
                for n in hierarchy.nodes:
                    if n.is_from_seed:
                        seed_dicts.append({
                            "uri": n.uri, "label": n.label,
                            "definition": n.definition,
                        })

                self.embedding_advisor.index_seed_classes(seed_dicts)
                advisor_report = self.embedding_advisor.recommend_parents(proposed)

                self._save_phase("4c_embedding_advisor", {
                    "model": advisor_report.model_used,
                    "recommendations": [
                        {
                            "label": r.proposed_label,
                            "parent": r.recommended_parent_label,
                            "similarity": r.similarity,
                            "confidence": r.structural_confidence,
                        }
                        for r in advisor_report.recommendations
                    ],
                })

                # Convert to StrategyVotes for ensemble
                for rec in advisor_report.recommendations:
                    embedding_votes.append(StrategyVote(
                        strategy=StrategyName.EMBEDDING,
                        proposed_label=rec.proposed_label,
                        recommended_parent_uri=rec.recommended_parent_uri,
                        recommended_parent_label=rec.recommended_parent_label,
                        confidence=rec.similarity,
                    ))

                logger.info("embedding_advisor_done",
                            recommendations=len(advisor_report.recommendations))
            except Exception as e:
                logger.warning("embedding_advisor_failed", error=str(e))

        # Module E: Ensemble Strategy
        if self.ensemble:
            try:
                # Collect LLM votes (from the hierarchy debate)
                llm_votes: list[StrategyVote] = []
                for n in hierarchy.nodes:
                    if not n.is_from_seed and n.parent_label:
                        llm_votes.append(StrategyVote(
                            strategy=StrategyName.LLM,
                            proposed_label=n.label,
                            recommended_parent_uri=n.parent_uri or "",
                            recommended_parent_label=n.parent_label,
                            confidence=0.8,  # LLM debated → reasonable confidence
                        ))

                # Co-occurrence votes
                seed_for_cooc = [
                    {"uri": f"seed:{lbl}", "label": lbl}
                    for lbl in seed_classes
                ]
                cooc_votes = EnsembleStrategy.compute_cooccurrence_votes(
                    [{"label": p["label"]} for p in proposed],
                    document_excerpts,
                    seed_for_cooc,
                )

                # Group all votes by class
                all_votes: dict[str, list[StrategyVote]] = {}
                for v in llm_votes + embedding_votes + cooc_votes:
                    all_votes.setdefault(v.proposed_label, []).append(v)

                ensemble_report = self.ensemble.aggregate(all_votes)

                self._save_phase("4e_ensemble", {
                    "avg_agreement": ensemble_report.avg_agreement,
                    "avg_confidence": ensemble_report.avg_confidence,
                    "unanimous": ensemble_report.unanimous_count,
                    "split": ensemble_report.split_count,
                    "decisions": [
                        {
                            "label": d.proposed_label,
                            "parent": d.final_parent_label,
                            "confidence": d.final_confidence,
                            "agreement": d.agreement_score,
                        }
                        for d in ensemble_report.decisions
                    ],
                })

                logger.info(
                    "ensemble_done",
                    classes=len(ensemble_report.decisions),
                    unanimous=ensemble_report.unanimous_count,
                    split=ensemble_report.split_count,
                )
            except Exception as e:
                logger.warning("ensemble_failed", error=str(e))

    # ── Phase runners (multi-agent debates) ─────────────────────────

    def _run_phase_scope(
        self, team: AgentTeam, docs_text: str, seed_cls: str,
    ) -> OntologyScope:
        """Phase 1: Define domain scope and competency questions."""
        logger.info("phase_1_scope_start")

        context = team.build_scope_context(docs_text, seed_cls)
        outcome = team.run_debate(Phase.SCOPE, context)
        team.save_debate(outcome)

        # Collect escalated questions
        self.result.questions.extend(outcome.escalated_questions)

        response = outcome.final_proposal
        scope = OntologyScope()
        if isinstance(response, dict):
            scope.domain = response.get("domain", "")
            scope.purpose = response.get("purpose", "")
            scope.intended_users = response.get("intended_users", [])
            scope.competency_questions = response.get("competency_questions", [])
            scope.out_of_scope = response.get("out_of_scope", [])

        self._save_phase("1_scope", scope.__dict__)
        logger.info(
            "phase_1_scope_done",
            cqs=len(scope.competency_questions),
            verdict=outcome.verdict.value,
        )
        return scope

    def _run_phase_reuse(
        self,
        team: AgentTeam,
        seed_cls: str,
        seed_props: str,
        term_preview: str,
        cqs_text: str,
    ) -> ReuseReport:
        """Phase 2: Analyse what we can reuse from existing ontologies."""
        logger.info("phase_2_reuse_start")

        context = team.build_reuse_context(seed_cls, seed_props, term_preview, cqs_text)
        outcome = team.run_debate(Phase.REUSE, context)
        team.save_debate(outcome)

        self.result.questions.extend(outcome.escalated_questions)

        response = outcome.final_proposal
        report = ReuseReport()
        if isinstance(response, dict):
            report.terms_already_covered = response.get("terms_already_covered", [])
            report.terms_still_needed = response.get("terms_still_needed", [])
            for rc in response.get("reuse_candidates", []):
                if isinstance(rc, dict):
                    report.candidates.append(ReuseCandidate(
                        ontology_name=rc.get("ontology_name", ""),
                        uri=rc.get("uri", ""),
                        overlap_terms=rc.get("overlap_terms", []),
                        decision=rc.get("decision", "skip"),
                        rationale=rc.get("rationale", ""),
                    ))
        elif isinstance(response, list):
            # If LLM returned just a list, assume it's terms_already_covered
            report.terms_already_covered = [str(x) for x in response]

        self._save_phase("2_reuse", {
            "terms_already_covered": report.terms_already_covered,
            "terms_still_needed": report.terms_still_needed,
            "candidates": [c.__dict__ for c in report.candidates],
        })
        logger.info("phase_2_reuse_done",
                     covered=len(report.terms_already_covered),
                     needed=len(report.terms_still_needed),
                     verdict=outcome.verdict.value)
        return report

    def _run_phase_terms(
        self, team: AgentTeam, docs_text: str, seed_cls: str,
    ) -> TermEnumeration:
        """Phase 3: Enumerate all important domain terms."""
        logger.info("phase_3_terms_start")

        context = team.build_terms_context(docs_text, seed_cls)
        outcome = team.run_debate(Phase.TERMS, context)
        team.save_debate(outcome)

        self.result.questions.extend(outcome.escalated_questions)

        response = outcome.final_proposal
        enum = TermEnumeration()
        if isinstance(response, dict):
            for t in response.get("terms", []):
                if isinstance(t, dict):
                    dt = DomainTerm(
                        term=t.get("term", ""),
                        category=t.get("category", "unknown"),
                        frequency=t.get("frequency", 1),
                        synonyms=t.get("synonyms", []),
                        evidence_snippets=t.get("evidence", []),
                    )
                    enum.terms.append(dt)

            enum.class_candidates = [t.term for t in enum.terms if t.category == "class"]
            enum.property_candidates = [t.term for t in enum.terms if t.category == "property"]
            enum.relation_candidates = [t.term for t in enum.terms if t.category == "relation"]
            enum.ambiguous_terms = [t.term for t in enum.terms if t.category == "unknown"]

        self._save_phase("3_terms", {
            "total": len(enum.terms),
            "classes": len(enum.class_candidates),
            "properties": len(enum.property_candidates),
            "relations": len(enum.relation_candidates),
            "ambiguous": len(enum.ambiguous_terms),
            "terms": [t.__dict__ for t in enum.terms],
        })
        logger.info("phase_3_terms_done", total=len(enum.terms),
                     classes=len(enum.class_candidates),
                     verdict=outcome.verdict.value)
        return enum

    def _run_phase_hierarchy(
        self, team: AgentTeam, seed_hier: str,
        class_terms: list[str], cqs_text: str,
    ) -> ClassHierarchy:
        """Phase 4: Build class hierarchy from terms."""
        logger.info("phase_4_hierarchy_start")

        context = team.build_hierarchy_context(seed_hier, class_terms, cqs_text)
        outcome = team.run_debate(Phase.HIERARCHY, context)
        team.save_debate(outcome)

        self.result.questions.extend(outcome.escalated_questions)

        response = outcome.final_proposal
        hierarchy = ClassHierarchy()
        if isinstance(response, dict):
            for n in response.get("nodes", []):
                if isinstance(n, dict):
                    node = HierarchyNode(
                        uri=n.get("uri", ""),
                        label=n.get("label", ""),
                        definition=n.get("definition", ""),
                        parent_uri=n.get("parent_uri"),
                        parent_label=n.get("parent_label"),
                        disjoint_with=n.get("disjoint_with", []),
                        examples=n.get("examples", []),
                        strategy=n.get("strategy", "middle-out"),
                        is_from_seed=n.get("is_from_seed", False),
                    )
                    hierarchy.nodes.append(node)

            hierarchy.new_classes_count = sum(
                1 for n in hierarchy.nodes if not n.is_from_seed
            )
            hierarchy.seed_classes_count = sum(
                1 for n in hierarchy.nodes if n.is_from_seed
            )

            # Compute depths
            uri_to_node = {n.uri: n for n in hierarchy.nodes}
            for node in hierarchy.nodes:
                depth = 0
                current = node
                visited: set[str] = set()
                while current.parent_uri and current.parent_uri in uri_to_node:
                    if current.uri in visited:
                        break
                    visited.add(current.uri)
                    depth += 1
                    current = uri_to_node[current.parent_uri]
                node.depth = depth
            hierarchy.total_depth = max(
                (n.depth for n in hierarchy.nodes), default=0
            )

        self._save_phase("4_hierarchy", {
            "nodes": [n.__dict__ for n in hierarchy.nodes],
            "total_depth": hierarchy.total_depth,
            "new_classes": hierarchy.new_classes_count,
            "seed_classes": hierarchy.seed_classes_count,
        })
        logger.info("phase_4_hierarchy_done",
                     new=hierarchy.new_classes_count,
                     depth=hierarchy.total_depth,
                     verdict=outcome.verdict.value)
        return hierarchy

    def _run_phase_properties(
        self,
        team: AgentTeam,
        hierarchy: ClassHierarchy | None,
        prop_terms: list[str],
        rel_terms: list[str],
        docs_text: str,
    ) -> list[PropertyProposal]:
        """Phase 5: Define properties with domain and range."""
        logger.info("phase_5_properties_start")

        hier_text = json.dumps(
            [{"label": n.label, "parent": n.parent_label}
             for n in (hierarchy.nodes if hierarchy else [])],
            indent=2,
        )

        context = team.build_properties_context(hier_text, prop_terms, rel_terms, docs_text)
        outcome = team.run_debate(Phase.PROPERTIES, context)
        team.save_debate(outcome)

        self.result.questions.extend(outcome.escalated_questions)

        response = outcome.final_proposal
        properties: list[PropertyProposal] = []
        if isinstance(response, dict):
            for p in response.get("properties", []):
                if isinstance(p, dict):
                    prop = PropertyProposal(
                        name=p.get("name", ""),
                        attached_to_class=p.get("attached_to_class", ""),
                        property_type=p.get("property_type", "datatype"),
                        description=p.get("description", ""),
                        datatype=p.get("datatype", "xsd:string"),
                        range_class=p.get("range_class"),
                        inverse_name=p.get("inverse_name"),
                        inherited_by=p.get("inherited_by", []),
                        source_evidence=p.get("source_evidence", []),
                    )
                    properties.append(prop)

        self._save_phase("5_properties", {
            "count": len(properties),
            "properties": [p.__dict__ for p in properties],
        })
        logger.info("phase_5_properties_done", count=len(properties),
                     verdict=outcome.verdict.value)
        return properties

    def _run_phase_facets(
        self,
        team: AgentTeam,
        properties: list[PropertyProposal],
        hierarchy: ClassHierarchy | None,
    ) -> FacetReport:
        """Phase 6: Define cardinality and value-type constraints."""
        logger.info("phase_6_facets_start")

        props_text = json.dumps(
            [{"name": p.name, "on": p.attached_to_class, "type": p.property_type}
             for p in properties],
            indent=2,
        )
        hier_text = json.dumps(
            [{"label": n.label, "parent": n.parent_label}
             for n in (hierarchy.nodes if hierarchy else [])],
            indent=2,
        )

        context = team.build_facets_context(props_text, hier_text)
        outcome = team.run_debate(Phase.FACETS, context)
        team.save_debate(outcome)

        self.result.questions.extend(outcome.escalated_questions)

        response = outcome.final_proposal
        report = FacetReport()
        if isinstance(response, dict):
            for f in response.get("facets", []):
                if isinstance(f, dict):
                    spec = FacetSpec(
                        property_name=f.get("property_name", ""),
                        on_class=f.get("on_class", ""),
                        min_count=f.get("min_count"),
                        max_count=f.get("max_count"),
                        value_type=f.get("value_type", "xsd:string"),
                        allowed_values=f.get("allowed_values"),
                        pattern=f.get("pattern"),
                        rationale=f.get("rationale", ""),
                    )
                    report.facets.append(spec)

        self._save_phase("6_facets", {
            "count": len(report.facets),
            "facets": [f.__dict__ for f in report.facets],
        })
        logger.info("phase_6_facets_done", count=len(report.facets),
                     verdict=outcome.verdict.value)
        return report

    def _run_phase_instances(
        self,
        team: AgentTeam,
        hierarchy: ClassHierarchy | None,
        properties: list[PropertyProposal],
        facets: FacetReport | None,
        scope: OntologyScope | None,
        docs_text: str,
    ) -> ValidationReport:
        """Phase 7: Validate with test instances and CQ answerability."""
        logger.info("phase_7_instances_start")

        classes_text = json.dumps(
            [{"label": n.label, "definition": n.definition}
             for n in (hierarchy.nodes if hierarchy else [])],
            indent=2,
        )
        props_text = json.dumps(
            [{"name": p.name, "on": p.attached_to_class, "type": p.property_type}
             for p in properties],
            indent=2,
        )
        facets_text = json.dumps(
            [{"prop": f.property_name, "on": f.on_class,
              "min": f.min_count, "max": f.max_count}
             for f in (facets.facets if facets else [])],
            indent=2,
        )
        cqs_text = json.dumps(
            scope.competency_questions[:15] if scope else [],
            indent=2,
        )

        context = team.build_instances_context(
            classes_text, props_text, facets_text, cqs_text, docs_text,
        )
        outcome = team.run_debate(Phase.INSTANCES, context)
        team.save_debate(outcome)

        self.result.questions.extend(outcome.escalated_questions)

        response = outcome.final_proposal
        report = ValidationReport()
        if isinstance(response, dict):
            for inst in response.get("test_instances", []):
                if isinstance(inst, dict):
                    report.instances_tested.append(SampleInstance(
                        class_uri="",
                        class_label=inst.get("class_label", ""),
                        property_values=inst.get("property_values", {}),
                        expected_valid=inst.get("representable", True),
                        validation_errors=inst.get("issues", []),
                    ))

            for cq in response.get("cq_results", []):
                if isinstance(cq, dict):
                    report.cq_results.append(CQTestResult(
                        cq_id=cq.get("cq_id", ""),
                        question=cq.get("question", ""),
                        answerable=cq.get("answerable", False),
                        required_classes=cq.get("required_classes", []),
                        required_properties=cq.get("required_properties", []),
                        missing_elements=cq.get("missing_elements", []),
                        sparql_sketch=cq.get("sparql_sketch", ""),
                    ))

            if report.cq_results:
                answerable = sum(1 for c in report.cq_results if c.answerable)
                report.cq_coverage_pct = answerable / len(report.cq_results)

            if report.instances_tested:
                valid = sum(
                    1 for i in report.instances_tested
                    if not i.validation_errors
                )
                report.instance_pass_rate = valid / len(report.instances_tested)

        self._save_phase("7_validation", {
            "cq_coverage_pct": report.cq_coverage_pct,
            "instance_pass_rate": report.instance_pass_rate,
            "instances": [i.__dict__ for i in report.instances_tested],
            "cq_results": [c.__dict__ for c in report.cq_results],
        })
        logger.info("phase_7_instances_done",
                     cq_coverage=f"{report.cq_coverage_pct:.0%}",
                     instance_pass=f"{report.instance_pass_rate:.0%}",
                     verdict=outcome.verdict.value)
        return report

    # ── Helpers ─────────────────────────────────────────────────────

    def _quick_term_extract(self, docs_text: str) -> str:
        """Quick term extraction for Phase 2 context (before full Phase 3)."""
        words = docs_text[:2000].split()
        # Simple: return capitalized multi-word terms
        terms: set[str] = set()
        for i, w in enumerate(words):
            if w and w[0].isupper() and len(w) > 2 and not w.startswith("("):
                terms.add(w.strip(".,;:()[]"))
        return ", ".join(sorted(terms)[:30])

    def _save_phase(self, phase_name: str, data: dict) -> None:
        """Persist phase artefact as JSON."""
        path = self.output_dir / f"{phase_name}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.debug("phase_saved", phase=phase_name, path=str(path))

    def _save_iteration(self) -> None:
        """Persist the full iteration summary."""
        summary = {
            "iteration": self.iteration,
            "phases_completed": 7,
            "questions_for_review": len(self.result.questions),
            "new_classes": (
                self.result.hierarchy.new_classes_count
                if self.result.hierarchy else 0
            ),
            "properties_defined": len(self.result.properties),
            "facets_defined": (
                len(self.result.facets.facets)
                if self.result.facets else 0
            ),
            "cq_coverage_pct": (
                self.result.validation.cq_coverage_pct
                if self.result.validation else 0
            ),
            "questions": [
                {
                    "phase": q.phase.value,
                    "question": q.question,
                    "context": q.context,
                    "options": q.options,
                    "default": q.default,
                    "answer": q.answer,
                }
                for q in self.result.questions
            ],
        }
        self._save_phase("iteration_summary", summary)

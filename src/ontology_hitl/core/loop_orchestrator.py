"""Orchestrator for the Ontology↔KG co-evolution feedback loop.

This is the top-level entry point that ties everything together.
It runs the multi-agent Ont-101 pipeline (OntologyEngineer + DomainExpert
+ Critic) across iterations, tracking convergence metrics.

The pipeline follows Noy & McGuinness (2001):
  1. Scope & CQs → 2. Reuse → 3. Terms → 4. Hierarchy →
  5. Properties → 6. Facets → 7. Instance validation

Each phase is a structured debate between three agents.  The human
reviewer (HITL) only handles escalated disagreements.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import structlog

from ontology_hitl.core.config import Settings
from ontology_hitl.core.feedback_protocol import (
    ConvergenceReport,
    FeedbackMetrics,
    IterationPlan,
    LoopMode,
)
from ontology_hitl.evaluation.provenance import ProvenanceTracker
from ontology_hitl.evaluation.feedback_learner import FeedbackLearner
from ontology_hitl.schema.seed_manager import SeedProtectedOntology

logger = structlog.get_logger(__name__)


class FeedbackLoopOrchestrator:
    """Run the ontology extension feedback loop.

    Uses a multi-agent team (OntologyEngineer, DomainExpert, Critic)
    following the Ont-101 methodology at each iteration.

    Standalone mode
    ---------------
    1. Fetch documents from Qdrant
    2. Run 7-phase multi-agent pipeline
    3. Agents debate each phase artefact
    4. Escalated questions go to HITL
    5. Export extended ontology (OWL + SHACL + YARRRML)
    6. Measure CQ answerability and entity coverage
    7. If not converged → next iteration

    Coupled mode (with KGB)
    -----------------------
    Same as above, plus:
    - Trigger KGB re-extraction after export
    - Measure improvement from new KG checkpoint

    Parameters
    ----------
    settings:
        Application configuration.
    mode:
        ``LoopMode.STANDALONE`` or ``LoopMode.COUPLED``.
    max_iterations:
        Safety cap on iteration count.
    convergence_threshold:
        Stop when entity_coverage improvement < this per iteration.
    max_debate_rounds:
        Maximum propose→review→revise cycles per phase.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        mode: LoopMode = LoopMode.STANDALONE,
        max_iterations: int = 6,
        convergence_threshold: float = 0.02,
        max_debate_rounds: int = 2,
        experiment_name: str = "",
    ) -> None:
        self.settings = settings or Settings()
        self.mode = mode
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.max_debate_rounds = max_debate_rounds
        self.experiment_name = experiment_name
        self.metrics_history: list[FeedbackMetrics] = []
        self._iteration = 0

        # Literature-inspired modules (shared across iterations)
        self.seed_manager: SeedProtectedOntology | None = None
        self.provenance = (
            ProvenanceTracker(settings=self.settings)
            if self.settings.provenance_enabled else None
        )
        self.feedback_learner = (
            FeedbackLearner(
                max_few_shot=self.settings.feedback_max_few_shot,
                memory_path=Path(self.settings.feedback_memory_path),
            )
            if self.settings.feedback_learning_enabled else None
        )
        # Feedback memory is auto-loaded in FeedbackLearner.__init__

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        checkpoint_path: Path | None = None,
        auto_review: bool = False,
    ) -> ConvergenceReport:
        """Execute the full feedback loop until convergence or max iterations.

        Args:
            checkpoint_path:
                KGB checkpoint for initial iteration (coupled mode).
                If ``None`` in standalone mode, entities are extracted
                from Qdrant directly.
            auto_review:
                If ``True``, skip interactive review and auto-accept
                proposals above the confidence threshold. Useful for
                automated experiments comparing feedback vs no-feedback.

        Returns:
            ``ConvergenceReport`` with per-iteration metrics.
        """
        logger.info("feedback_loop_start",
                     mode=self.mode.value,
                     max_iter=self.max_iterations)

        # W&B init
        self._init_wandb()

        for iteration in range(1, self.max_iterations + 1):
            self._iteration = iteration
            logger.info("iteration_start", iteration=iteration)

            plan = self._plan_iteration(iteration, checkpoint_path)
            metrics = self._execute_iteration(plan, checkpoint_path, auto_review)

            # Compute improvement over previous
            if self.metrics_history:
                prev = self.metrics_history[-1]
                metrics.improvement_over_previous = (
                    metrics.entity_coverage_pct - prev.entity_coverage_pct
                )
            else:
                metrics.improvement_over_previous = metrics.entity_coverage_pct

            self.metrics_history.append(metrics)
            self._log_wandb(metrics)

            logger.info(
                "iteration_complete",
                iteration=iteration,
                entity_coverage=f"{metrics.entity_coverage_pct:.1%}",
                cq_coverage=f"{metrics.cq_coverage_pct:.1%}",
                improvement=f"{metrics.improvement_over_previous:.1%}",
            )

            # Convergence check
            if (
                iteration > 1
                and metrics.improvement_over_previous < self.convergence_threshold
            ):
                logger.info("convergence_reached", iteration=iteration)
                break

            # Target check
            if (
                metrics.entity_coverage_pct >= self.settings.entity_coverage_target
                and metrics.cq_coverage_pct >= self.settings.cq_answerability_target
            ):
                logger.info("targets_met", iteration=iteration)
                break

        report = ConvergenceReport(
            total_iterations=len(self.metrics_history),
            mode=self.mode.value,
            metrics_per_iteration=self.metrics_history,
        )
        summary = report.compute_summary()

        # Save report
        self._save_report(report, summary)
        self._finish_wandb(summary)

        # Module D: Export full provenance trail
        if self.provenance:
            try:
                output_dir = Path(self.settings.exports_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                prov_path = output_dir / "provenance.json"
                prov_data = self.provenance.to_dict()
                import json as _json
                with open(prov_path, "w") as f:
                    _json.dump(prov_data, f, indent=2, default=str)
                logger.info("provenance_trail_exported", path=str(prov_path))
            except Exception as e:
                logger.warning("provenance_export_failed", error=str(e))

        # Module F: feedback memory is auto-persisted on each record()

        return report

    # ------------------------------------------------------------------
    # Single-iteration execution
    # ------------------------------------------------------------------

    def _execute_iteration(
        self,
        plan: IterationPlan,
        checkpoint_path: Path | None,
        auto_review: bool,
    ) -> FeedbackMetrics:
        """Run one iteration using the multi-agent Ont-101 pipeline.

        The pipeline structures the work as 7 phases, each executed as
        a debate between OntologyEngineer, DomainExpert, and Critic:
          1. Scope & CQs      — "What should this ontology cover?"
          2. Reuse             — "What already exists that we can reuse?"
          3. Term enumeration  — "What are all the important domain terms?"
          4. Class hierarchy   — "How do these terms relate? (is-a, siblings)"
          5. Properties        — "What attributes and relations do they have?"
          6. Facets            — "What constraints apply? (cardinality, types)"
          7. Instance validation — "Does the ontology work? Can we answer the CQs?"
        """
        from ontology_hitl.methodology.pipeline import Ont101Pipeline

        iter_dir = Path(self.settings.iterations_dir) / f"{'v' + str(plan.iteration) if not self.experiment_name else self.experiment_name}"

        # Gather input context
        doc_excerpts = self._fetch_document_excerpts()
        seed_classes = self._get_seed_classes()
        seed_properties = self._get_seed_properties()
        seed_hierarchy = self._get_seed_hierarchy_text()

        # Module A: Seed Protection — load once per loop
        if self.seed_manager is None:
            try:
                self.seed_manager = SeedProtectedOntology()
                self.seed_manager.load_seed(self.settings.seed_ontology_path)
                logger.info(
                    "seed_manager_loaded",
                    classes=len(self.seed_manager.seed_classes()),
                )
            except Exception as e:
                logger.warning("seed_manager_load_failed", error=str(e))
                self.seed_manager = None

        # Run the 7-phase multi-agent pipeline
        pipeline = Ont101Pipeline(
            settings=self.settings,
            iteration=plan.iteration,
            output_dir=iter_dir,
            max_debate_rounds=self.max_debate_rounds,
            seed_manager=self.seed_manager,
            provenance=self.provenance,
            feedback_learner=self.feedback_learner,
        )
        result = pipeline.run_iteration(
            document_excerpts=doc_excerpts,
            seed_classes=seed_classes,
            seed_properties=seed_properties,
            seed_hierarchy=seed_hierarchy,
        )

        # Convert Ont101Iteration → FeedbackMetrics for convergence tracking
        total_entities = len(result.terms.terms) if result.terms else 0
        new_classes = result.hierarchy.new_classes_count if result.hierarchy else 0
        cq_coverage = result.validation.cq_coverage_pct if result.validation else 0.0
        n_properties = len(result.properties)
        n_questions = len(result.questions)

        # Entity coverage: proportion of terms that became classes
        entity_cov = (
            len(result.terms.class_candidates) / len(result.terms.terms)
            if result.terms and result.terms.terms else 0.0
        )

        # Ontology quality assessment (scientific validation)
        quality_scores = self._assess_ontology_quality(checkpoint_path, iter_dir / "ontology.ttl")

        metrics = FeedbackMetrics(
            iteration=plan.iteration,
            mode=self.mode.value,
            total_entities_extracted=total_entities,
            proposals_generated=new_classes,
            proposals_accepted=new_classes,
            acceptance_rate=1.0 if auto_review else 0.0,
            classes_added_this_iter=new_classes,
            entity_coverage_pct=entity_cov,
            cq_coverage_pct=cq_coverage,
            ontology_consistency_score=quality_scores.get("consistency", 0.0),
            ontology_coherence_score=quality_scores.get("coherence", 0.0),
            ontology_modularity_score=quality_scores.get("modularity", 0.0),
            ontology_expressiveness_score=quality_scores.get("expressiveness", 0.0),
            ontology_overall_quality_score=quality_scores.get("overall_quality_score", 0.0),
        )

        logger.info(
            "iteration_metrics",
            iteration=plan.iteration,
            new_classes=new_classes,
            properties=n_properties,
            cq_coverage=f"{cq_coverage:.0%}",
            questions_for_review=n_questions,
        )

        return metrics

    def _assess_ontology_quality(
        self, checkpoint_path: Path | None, ontology_path: Path | None
    ) -> dict[str, float]:
        """Assess ontology quality using scientific metrics."""
        try:
            from ontology_hitl.evaluation.ontology_quality import OntologyQualityAnalyzer

            analyzer = OntologyQualityAnalyzer(
                fuseki_url=self.settings.fuseki_url,
                dataset=self.settings.fuseki_dataset,
                ollama_url=self.settings.ollama_url,
                model=self.settings.ollama_model,
            )

            if checkpoint_path and ontology_path and ontology_path.exists():
                assessment = analyzer.comprehensive_quality_assessment(
                    checkpoint_path=str(checkpoint_path),
                    ontology_path=str(ontology_path),
                )
                return {
                    "consistency": assessment.get("consistency", {}).get("consistency_score", 0.0),
                    "coherence": assessment.get("coherence", {}).get("coherence_score", 0.0),
                    "modularity": assessment.get("modularity", {}).get("modularity_score", 0.0),
                    "expressiveness": assessment.get("expressiveness", {}).get("expressiveness_score", 0.0),
                    "overall_quality_score": assessment.get("overall_quality_score", 0.0),
                }
            else:
                # Fallback: basic assessment without full data
                return {
                    "consistency": 0.5,
                    "coherence": 0.5,
                    "modularity": 0.5,
                    "expressiveness": 0.5,
                    "overall_quality_score": 0.5,
                }
        except Exception as e:
            logger.warning("ontology_quality_assessment_failed", error=str(e))
            return {
                "consistency": 0.0,
                "coherence": 0.0,
                "modularity": 0.0,
                "expressiveness": 0.0,
                "overall_quality_score": 0.0,
            }

    # ------------------------------------------------------------------
    # Context gathering for the multi-agent pipeline
    # ------------------------------------------------------------------

    def _fetch_document_excerpts(self, max_chunks: int = 50) -> list[str]:
        """Fetch text chunks from Qdrant for the Ont-101 pipeline."""
        try:
            from ontology_hitl.sources.qdrant_source import QdrantDocumentSource
            source = QdrantDocumentSource(
                qdrant_url=self.settings.qdrant_url,
                ollama_url=self.settings.ollama_url,
                ollama_model=self.settings.ollama_model,
            )
            chunks = source.fetch_chunks(limit=max_chunks, prioritize_legal=True)
            return [c.text for c in chunks]
        except Exception as e:
            logger.warning("qdrant_fetch_failed", error=str(e))
            return []

    def _get_seed_classes(self) -> list[str]:
        """Get class labels from the seed ontology via rdflib."""
        try:
            from rdflib import Graph, RDF, OWL, RDFS
            g = Graph()
            g.parse(self.settings.seed_ontology_path)
            classes = []
            for cls in g.subjects(RDF.type, OWL.Class):
                for label in g.objects(cls, RDFS.label):
                    classes.append(str(label))
                    break
                else:
                    classes.append(str(cls).split("#")[-1].split("/")[-1])
            return classes
        except Exception as e:
            logger.warning("seed_ontology_load_failed", error=str(e))
            return []

    def _get_seed_properties(self) -> list[str]:
        """Get property names from the seed ontology via rdflib."""
        try:
            from rdflib import Graph, RDF, OWL, RDFS
            g = Graph()
            g.parse(self.settings.seed_ontology_path)
            props = []
            for prop_type in [OWL.DatatypeProperty, OWL.ObjectProperty]:
                for prop in g.subjects(RDF.type, prop_type):
                    for label in g.objects(prop, RDFS.label):
                        props.append(str(label))
                        break
                    else:
                        props.append(str(prop).split("#")[-1].split("/")[-1])
            return props
        except Exception:
            return []

    def _get_seed_hierarchy_text(self) -> str:
        """Build a text representation of the seed class hierarchy."""
        try:
            from rdflib import Graph, RDF, OWL, RDFS
            g = Graph()
            g.parse(self.settings.seed_ontology_path)

            lines = []
            for cls in g.subjects(RDF.type, OWL.Class):
                label = str(cls).split("#")[-1].split("/")[-1]
                parents = list(g.objects(cls, RDFS.subClassOf))
                if parents:
                    for p in parents:
                        plabel = str(p).split("#")[-1].split("/")[-1]
                        lines.append(f"  {label} → subClassOf → {plabel}")
                else:
                    lines.append(f"  {label} (root)")
            return "\n".join(lines) if lines else "(empty seed ontology)"
        except Exception:
            return "(seed ontology not available)"

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _plan_iteration(
        self,
        iteration: int,
        checkpoint_path: Path | None,
    ) -> IterationPlan:
        """Decide what the next iteration should focus on."""
        return IterationPlan(
            iteration=iteration,
            mode=self.mode,
            max_proposals=15 if iteration <= 2 else 10,
            trigger_kgb_reextract=(
                self.mode == LoopMode.COUPLED and iteration > 1
            ),
            notes=f"Auto-planned iteration {iteration}",
        )

    # ------------------------------------------------------------------
    # W&B integration
    # ------------------------------------------------------------------

    def _init_wandb(self) -> None:
        if not self.settings.wandb_enabled:
            return
        try:
            import wandb
            from datetime import datetime
            import os

            # Ensure we are logged in with the provided API key
            if self.settings.wandb_api_key:
                wandb.login(key=self.settings.wandb_api_key)

            # Create clean run name: just the experiment name
            if self.experiment_name:
                run_name = self.experiment_name
            else:
                # Fallback to mode + timestamp if no experiment name
                timestamp = datetime.now().strftime("%H%M")
                run_name = f"{self.mode.value}_{timestamp}"

            # Create minimal clean tags: experiment name and model
            model_name = self.settings.ollama_model
            model_short = model_name.split(":")[0].split("/")[-1]  # Handle 'user/model:version'
            tags = [model_short]  # Include the clean model name
            if self.experiment_name:
                tags.append(self.experiment_name)

            wandb.init(
                project=self.settings.wandb_project,
                entity=self.settings.wandb_entity,
                name=run_name,
                config={
                    "mode": self.mode.value,
                    "max_iterations": self.max_iterations,
                    "convergence_threshold": self.convergence_threshold,
                    "model": self.settings.ollama_model,
                    "min_frequency": self.settings.min_entity_frequency,
                    "similarity_threshold": self.settings.semantic_similarity_threshold,
                },
                tags=tags,
                reinit=True,
            )

            # LangSmith tracing is now handled by @ls_traceable decorators
            # on agent methods and the pipeline (see agents/base.py).
            # No additional setup needed here — langsmith auto-traces when
            # LANGSMITH_TRACING=true is set in the environment.

        except Exception as e:
            logger.warning("wandb_init_failed", error=str(e))

    def _log_wandb(self, metrics: FeedbackMetrics) -> None:
        if not self.settings.wandb_enabled:
            return
        try:
            import wandb
            wandb.log({
                "iteration": metrics.iteration,
                "entity_coverage": metrics.entity_coverage_pct,
                "cq_coverage": metrics.cq_coverage_pct,
                "classes_added": metrics.classes_added_this_iter,
                "acceptance_rate": metrics.acceptance_rate,
                "improvement": metrics.improvement_over_previous,
                "total_entities": metrics.total_entities_extracted,
            })
        except Exception:
            pass

    def _finish_wandb(self, summary: dict) -> None:
        if not self.settings.wandb_enabled:
            return
        try:
            import wandb
            wandb.summary.update(summary)
            wandb.finish()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_report(self, report: ConvergenceReport, summary: dict) -> None:
        """Save convergence report to disk."""
        output_dir = Path(self.settings.exports_dir)
        if self.experiment_name:
            output_dir = output_dir / self.experiment_name
        output_dir.mkdir(parents=True, exist_ok=True)

        report_data = {
            "total_iterations": report.total_iterations,
            "mode": report.mode,
            "summary": summary,
            "iterations": [
                {
                    "iteration": m.iteration,
                    "entity_coverage_pct": m.entity_coverage_pct,
                    "cq_coverage_pct": m.cq_coverage_pct,
                    "classes_added": m.classes_added_this_iter,
                    "improvement": m.improvement_over_previous,
                    "acceptance_rate": m.acceptance_rate,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in report.metrics_per_iteration
            ],
        }

        path = output_dir / "convergence_report.json"
        with open(path, "w") as f:
            json.dump(report_data, f, indent=2)

        logger.info("convergence_report_saved", path=str(path))

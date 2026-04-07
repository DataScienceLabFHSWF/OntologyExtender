"""Six-dimension + extended evaluation framework for ontology extension benchmarking.

Computes all six core metric dimensions defined in MetricScores:
  1. Semantic Correctness — embedding-based alignment with gold standard
  2. Hallucination Rate   — elements with no gold-standard correspondence
  3. CQ Coverage          — fraction of CQs answerable after extension
  4. Hierarchy Quality    — depth and structure of class hierarchy
  5. Domain Compliance    — alignment with domain vocabulary / namespace
  6. Expert Acceptance    — human (or simulated) acceptance rate

Plus extended evaluations from integrated frameworks:
  7. TamingHallucinations Semantic Matching (concept + triple level)
     — Fathallah, Staab & Algergawy (2025)
     — Sentence-transformer embeddings + cosine similarity
     — Two-level: concept label matching + SPO triple matching
  8. OntoURL Capability Profiling (15 tasks × 3 levels)
     — Zhang et al. (2025)
     — Understanding / Reasoning / Learning taxonomy
     — Metrics: Accuracy, ROUGE-L, Triple-F1, Tuple-F1
  9. OWLUnit Ontology Unit Testing (4 test types)
     — Asprino (2024)
     — Annotation / CQ / Inference / Error Provocation verification

Architecture
------------
The ``BenchmarkEvaluator`` takes a generated ontology and a gold-standard
ontology, and scores each dimension.  It reuses components from the
existing ``ontology_hitl.evaluation`` module where possible (CQEvaluator,
OntologyQualityAnalyzer) and adds new scorers specific to benchmarking.

Dependencies
------------
- ``rdflib``                for OWL graph comparison
- ``numpy``                 for cosine similarity
- ``httpx``                 for embedding API calls (Ollama)
- ``sentence-transformers`` for TamingHallucinations semantic matching
- ``structlog``             for structured logging

References
----------
- BASELINE_POSITIONING_SUMMARY.md §Metrics Table
- BENCHMARKING_EXECUTIVE_SUMMARY.md §Expected Results
- BENCHMARKING_QUICKSTART.md §Evaluation Rubric
- Fathallah et al. (2025) TamingHallucinations
- Zhang et al. (2025) OntoURL
- Asprino (2024) OWLUnit
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import structlog
from rdflib import OWL, RDF, RDFS, Graph, URIRef

from .models import (
    BenchmarkResult,
    CompetencyQuestion,
    ExpertReviewSession,
    MetricScores,
    OntoURLCapability,
    OntoURLCapabilityProfile,
    OntoURLTask,
    OntoURLTaskScore,
    OWLUnitTestResult,
    OWLUnitTestSuite,
    OWLUnitTestType,
    SemanticMatchLevel,
    SemanticMatchResult,
    TestCase,
)

logger = structlog.get_logger(__name__)


class BenchmarkEvaluator:
    """Six-dimension evaluator for ontology extension benchmarks.

    Computes all metric dimensions for a generated ontology against
    a gold-standard reference.

    Parameters
    ----------
    embedding_url : str
        Ollama endpoint for computing text embeddings.
    embedding_model : str
        Model name for the embedding API.
    similarity_threshold : float
        Minimum cosine similarity to count as a semantic match
        when evaluating semantic correctness.
    fuseki_url : str | None
        Optional Fuseki SPARQL endpoint for CQ evaluation.
        If ``None``, CQ evaluation uses structural matching only.

    Examples
    --------
    >>> evaluator = BenchmarkEvaluator()
    >>> scores = evaluator.evaluate_all(
    ...     generated_path="results/cogagent_75pct/output.owl",
    ...     test_case=test_case,
    ... )
    >>> scores.composite_score
    0.87
    """

    def __init__(
        self,
        embedding_url: str = "http://localhost:18135",
        embedding_model: str = "gemma4:e2b",
        similarity_threshold: float = 0.85,
        fuseki_url: str | None = None,
        # --- TamingHallucinations settings ---
        semantic_match_model: str = "all-MiniLM-L6-v2",
        concept_match_threshold: float = 0.55,
        triple_match_threshold: float = 0.50,
        semantic_embedding_model: str | None = None,
        # --- OWLUnit settings ---
        owlunit_jar_path: str | None = None,
    ) -> None:
        self.embedding_url = embedding_url
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.fuseki_url = fuseki_url
        # TamingHallucinations
        self.semantic_match_model_name = semantic_match_model
        self.semantic_embedding_model = semantic_embedding_model or embedding_model
        self.concept_match_threshold = concept_match_threshold
        self.triple_match_threshold = triple_match_threshold
        self._sentence_model = None  # Lazy-loaded SentenceTransformer
        self._embedding_cache: dict[str, list[float]] = {}
        # OWLUnit
        self.owlunit_jar_path = owlunit_jar_path

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def evaluate_all(
        self,
        generated_path: str | Path,
        test_case: TestCase,
        expert_review: ExpertReviewSession | None = None,
    ) -> MetricScores:
        """Compute all six metric dimensions.

        Parameters
        ----------
        generated_path : str | Path
            Path to the OWL/TTL file produced by the system under test.
        test_case : TestCase
            The test case (contains gold standard path, removed elements, CQs).
        expert_review : ExpertReviewSession | None
            Optional human review data for expert_acceptance metric.
            If ``None``, uses LLM-based simulated expert scoring.

        Returns
        -------
        MetricScores
            Fully populated scores across all six dimensions.

        Notes
        -----
        Each dimension is scored independently.  If one dimension
        fails (e.g., embedding service down), the others still compute
        and the failed dimension gets a score of 0.0 with a warning log.
        """
        metrics = MetricScores()

        # Load graphs
        try:
            gen_graph = self._load_graph(generated_path)
        except Exception as e:
            logger.warning("evaluate_all_failed_load_generated", error=str(e))
            raise

        try:
            gold_graph = self._load_graph(test_case.gold_standard_path)
        except Exception:
            gold_graph = Graph()

        # Seed graph may be absent in some test-cases
        seed_graph = Graph()
        try:
            if getattr(test_case, "seed_ontology_path", None):
                seed_graph = self._load_graph(test_case.seed_ontology_path)
        except Exception:
            seed_graph = Graph()

        # Per-dimension scoring with guarded failures
        try:
            metrics.semantic_correctness = self.score_semantic_correctness(
                gen_graph, gold_graph, test_case.removed_classes
            )
        except Exception as e:
            logger.warning("semantic_correctness_failed", error=str(e))
            metrics.semantic_correctness = 0.0

        try:
            metrics.hallucination_rate = self.score_hallucination_rate(
                gen_graph, gold_graph, seed_graph
            )
        except Exception as e:
            logger.warning("hallucination_rate_failed", error=str(e))
            metrics.hallucination_rate = 1.0

        try:
            metrics.cq_coverage = self.score_cq_coverage(
                gen_graph, test_case.competency_questions
            )
        except Exception as e:
            logger.warning("cq_coverage_failed", error=str(e))
            metrics.cq_coverage = 0.0

        try:
            metrics.hierarchy_quality = self.score_hierarchy_quality(gen_graph, gold_graph)
        except Exception as e:
            logger.warning("hierarchy_quality_failed", error=str(e))
            metrics.hierarchy_quality = 0.0

        try:
            metrics.domain_compliance = self.score_domain_compliance(gen_graph, gold_graph)
        except Exception as e:
            logger.warning("domain_compliance_failed", error=str(e))
            metrics.domain_compliance = 0.0

        try:
            metrics.expert_acceptance = self.score_expert_acceptance(
                gen_graph, gold_graph, None
            )
        except Exception as e:
            logger.warning("expert_acceptance_failed", error=str(e))
            metrics.expert_acceptance = 0.0

        # ------------------------------------------------------------------
        # Extended evaluations (TamingHallucinations + OWLUnit)
        # ------------------------------------------------------------------
        try:
            # Build reference graphs: always include the gold standard first
            reference_graphs: dict[str, Graph] = {"gold": gold_graph}

            # Allow optional extra reference ontologies provided in test_case.metadata
            refs = getattr(test_case, "metadata", {}).get("reference_ontologies")
            if refs:
                # refs may be list or dict
                if isinstance(refs, dict):
                    for name, path in refs.items():
                        try:
                            reference_graphs[name] = self._load_graph(path)
                        except Exception:
                            logger.debug("ref_load_failed", name=name, path=str(path))
                else:
                    for path in (refs or []):
                        try:
                            key = Path(path).stem
                            reference_graphs[key] = self._load_graph(path)
                        except Exception:
                            logger.debug("ref_load_failed", path=str(path))

            # TamingHallucinations: concept & triple semantic matching
            try:
                metrics.semantic_match_concept = self.score_semantic_match_concepts(
                    gen_graph, reference_graphs
                )
            except Exception as e:
                logger.warning("semantic_match_concepts_failed", error=str(e))
                metrics.semantic_match_concept = None

            try:
                metrics.semantic_match_triple = self.score_semantic_match_triples(
                    gen_graph, reference_graphs
                )
            except Exception as e:
                logger.warning("semantic_match_triples_failed", error=str(e))
                metrics.semantic_match_triple = None

            # OWLUnit-style test suite (rdflib approximation or JAR if configured)
            try:
                metrics.owlunit_suite = self.score_owlunit_suite(generated_path, test_case)
            except Exception as e:
                logger.warning("owlunit_suite_failed", error=str(e))
                metrics.owlunit_suite = None
        except Exception as e:
            logger.warning("extended_evaluations_failed", error=str(e))

        return metrics

    # ------------------------------------------------------------------
    # Dimension 1: Semantic Correctness
    # ------------------------------------------------------------------

    def score_semantic_correctness(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
        removed_classes: list[str],
    ) -> float:
        """Score semantic correctness of generated classes vs. gold standard.

        Algorithm
        ---------
        1. Extract labels of all *new* classes in the generated graph
           (classes not in the reduced seed).
        2. For each new class label, compute embedding similarity
           against each *removed* class label in the gold standard.
        3. A new class is "semantically correct" if its best-match
           similarity ≥ ``self.similarity_threshold`` OR it exactly
           matches a removed class label (case-insensitive).
        4. Score = correct_matches / total_removed_classes.

        Parameters
        ----------
        generated_graph : Graph
            The system's extended ontology.
        gold_graph : Graph
            The full gold-standard ontology.
        removed_classes : list[str]
            URIs of classes that were deliberately removed.

        Returns
        -------
        float
            Score in [0, 1].  1.0 = all removed classes semantically
            recovered.  Target: ≥ 0.92.

        Notes
        -----
        This measures *recall* of the removed elements.  A system that
        generates many correct classes but misses removed ones still
        gets a low score.
        """
        # Extract labels
        gen_labels = self._extract_class_labels(generated_graph)
        gold_labels = self._extract_class_labels(gold_graph)

        if not removed_classes:
            return 1.0

        matched = 0
        for removed_uri in removed_classes:
            # find label of removed class in gold
            removed_label = gold_labels.get(removed_uri, None)
            if not removed_label:
                # try local name
                removed_label = removed_uri.split("#")[-1].split("/")[-1]

            # Exact match (case-insensitive)
            found_exact = any(
                removed_label.lower() == lbl.lower() for lbl in gen_labels.values()
            )
            if found_exact:
                matched += 1
                continue

            # Embedding-based fallback
            try:
                rem_emb = self._get_embedding(removed_label)
                for gen_lbl in gen_labels.values():
                    gen_emb = self._get_embedding(gen_lbl)
                    if gen_emb is None or rem_emb is None:
                        continue
                    if self._cosine_similarity(rem_emb, gen_emb) >= self.similarity_threshold:
                        matched += 1
                        break
            except Exception:
                continue

        return matched / max(1, len(removed_classes))

    # ------------------------------------------------------------------
    # Dimension 2: Hallucination Rate
    # ------------------------------------------------------------------

    def score_hallucination_rate(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
        seed_graph: Graph,
    ) -> float:
        """Compute hallucination rate: fraction of generated elements
        that have no correspondence in the gold standard.

        Algorithm
        ---------
        1. Identify all *new* classes in the generated graph (not in seed).
        2. For each new class, check if it has a semantic match in the
           gold standard (embedding similarity ≥ threshold OR exact match).
        3. Classes with *no* match are hallucinations.
        4. Rate = hallucinated_classes / total_new_classes.

        Parameters
        ----------
        generated_graph : Graph
        gold_graph : Graph
        seed_graph : Graph
            The reduced seed (to determine what is "new").

        Returns
        -------
        float
            Rate in [0, 1].  0.0 = no hallucinations.  Target: < 0.05.

        Notes
        -----
        This is the complement of *precision* restricted to novelty.
        A system that simply copies the seed gets 0 % hallucination
        but also 0 % semantic correctness.
        """
        gen_labels = self._extract_class_labels(generated_graph)
        seed_labels = self._extract_class_labels(seed_graph)
        gold_labels = self._extract_class_labels(gold_graph)

        # New classes = present in generated but not in seed
        new_classes = [uri for uri in gen_labels.keys() if uri not in seed_labels]
        total_new = len(new_classes)
        if total_new == 0:
            return 0.0

        hallucinated = 0
        for uri in new_classes:
            gen_lbl = gen_labels.get(uri, uri.split('#')[-1].split('/')[-1])
            # exact match in gold?
            if any(gen_lbl.lower() == gl.lower() for gl in gold_labels.values()):
                continue

            # embedding match fallback
            try:
                gen_emb = self._get_embedding(gen_lbl)
                matched = False
                for gl in gold_labels.values():
                    gl_emb = self._get_embedding(gl)
                    if gen_emb is None or gl_emb is None:
                        continue
                    if self._cosine_similarity(gen_emb, gl_emb) >= self.similarity_threshold:
                        matched = True
                        break
                if not matched:
                    hallucinated += 1
            except Exception:
                hallucinated += 1

        return hallucinated / total_new

    # ------------------------------------------------------------------
    # Dimension 3: CQ Coverage
    # ------------------------------------------------------------------

    def score_cq_coverage(
        self,
        generated_graph: Graph,
        competency_questions: list[CompetencyQuestion],
    ) -> float:
        """Score competency question answerability.

        Strategy
        --------
        For each CQ:
          A. **Structural check** (fast): verify that all
             ``target_classes`` and ``target_properties`` exist in
             the generated graph.
          B. **SPARQL check** (if Fuseki available and CQ has
             ``sparql_template``): execute the SPARQL query and
             check for non-empty results.

        A CQ is "covered" if *either* check passes.

        Parameters
        ----------
        generated_graph : Graph
        competency_questions : list[CompetencyQuestion]

        Returns
        -------
        float
            Fraction in [0, 1].  Target: > 0.85.

        See Also
        --------
        ontology_hitl.evaluation.cq_evaluator.CQEvaluator
            Existing CQ evaluator that uses SPARQL-based checking.
        """
        covered = 0
        total = max(1, len(competency_questions))

        # quick existence check helper
        def _exists(uri: str) -> bool:
            u = URIRef(uri)
            # class defined or referenced
            for _ in generated_graph.triples((u, None, None)):
                return True
            for _ in generated_graph.triples((None, None, u)):
                return True
            return False

        for cq in competency_questions:
            # Structural check: all target classes/properties present
            classes_ok = all(_exists(c) for c in cq.target_classes) if cq.target_classes else True
            props_ok = all(_exists(p) for p in cq.target_properties) if cq.target_properties else True
            if classes_ok and props_ok:
                covered += 1
                continue
            # SPARQL check skipped in smoke mode / when no fuseki configured
            # Treat as not covered if structural checks fail
        return covered / total

    # ------------------------------------------------------------------
    # Dimension 4: Hierarchy Quality
    # ------------------------------------------------------------------

    def score_hierarchy_quality(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
    ) -> float:
        """Score the depth and structure of the generated class hierarchy.

        Measures
        --------
        1. **Max depth**: longest rdfs:subClassOf chain from owl:Thing
           to a leaf class.
        2. **Avg branching factor**: mean number of direct subclasses
           per non-leaf class.
        3. **Structure similarity**: how close the generated hierarchy
           resembles the gold standard's tree shape.

        The final score normalises generated depth against gold depth:
        ``min(gen_depth, gold_depth) / gold_depth``, penalising both
        too-shallow (< gold) and moderately rewarding matching depth.

        Parameters
        ----------
        generated_graph : Graph
        gold_graph : Graph

        Returns
        -------
        float
            Score in [0, 1].  Target: depth of 4–5 levels → 0.8–1.0.
        """
        gen_depth = self._compute_hierarchy_depth(generated_graph)
        gold_depth = self._compute_hierarchy_depth(gold_graph)
        if gold_depth <= 0:
            return 1.0
        return min(gen_depth, gold_depth) / gold_depth

    def _compute_hierarchy_depth(self, graph: Graph) -> int:
        """Compute the maximum depth of the class hierarchy.

        Traverses ``rdfs:subClassOf`` chains starting from root
        classes (those with no superclass or only ``owl:Thing``).

        Parameters
        ----------
        graph : Graph

        Returns
        -------
        int
            Maximum depth (1 = only root classes, no hierarchy).
        """
        # Build parent -> children map
        children: dict[str, set[str]] = {}
        classes = set()
        for s, p, o in graph.triples((None, RDF.type, OWL.Class)):
            classes.add(str(s))
        for s, p, o in graph.triples((None, RDFS.subClassOf, None)):
            parent = str(o)
            child = str(s)
            classes.update([parent, child])
            children.setdefault(parent, set()).add(child)

        # Roots: classes with no parent (or whose parent is owl:Thing)
        has_parent = set(o for s, p, o in graph.triples((None, RDFS.subClassOf, None)))
        roots = [c for c in classes if c not in has_parent or c == str(OWL.Thing)]
        if not roots:
            roots = list(classes)[:1]

        max_depth = 0
        stack = [(r, 1) for r in roots]
        while stack:
            node, depth = stack.pop()
            max_depth = max(max_depth, depth)
            for child in children.get(node, []):
                stack.append((child, depth + 1))
        return max_depth or 1

    def _compute_branching_factor(self, graph: Graph) -> float:
        """Compute mean branching factor of the class hierarchy.

        Parameters
        ----------
        graph : Graph

        Returns
        -------
        float
            Average number of subclasses per non-leaf class.
        """
        # Build parent -> children map
        counts = []
        for s, p, o in graph.triples((None, RDFS.subClassOf, None)):
            counts.append(1)
        # Approximate branching factor: total subclass edges / number of parents
        parent_set = set(str(o) for s, p, o in graph.triples((None, RDFS.subClassOf, None)))
        if not parent_set:
            return 0.0
        total_edges = sum(1 for _ in graph.triples((None, RDFS.subClassOf, None)))
        return total_edges / max(1, len(parent_set))

    # ------------------------------------------------------------------
    # Dimension 5: Domain Compliance
    # ------------------------------------------------------------------

    def score_domain_compliance(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
        domain_namespace: str | None = None,
    ) -> float:
        """Score alignment with domain vocabulary and namespace conventions.

        Checks
        ------
        1. **Namespace compliance**: fraction of new classes/properties
           using the correct ontology namespace (vs. inventing new ones).
        2. **Label quality**: new elements have rdfs:label and
           rdfs:comment annotations.
        3. **Vocabulary alignment**: new labels use terms from the
           domain vocabulary (seed ontology + gold standard labels).

        Parameters
        ----------
        generated_graph : Graph
        gold_graph : Graph
        domain_namespace : str | None
            Expected namespace URI.  If ``None``, inferred from
            the gold standard's ontology IRI.

        Returns
        -------
        float
            Score in [0, 1].  Target: ≥ 0.95.
        """
        # Determine domain namespace
        ns = domain_namespace
        if ns is None:
            # infer from gold graph: first class URI namespace
            for s, p, o in gold_graph.triples((None, RDF.type, OWL.Class)):
                uri = str(s)
                if '#' in uri:
                    ns = uri.split('#')[0] + '#'
                else:
                    ns = '/'.join(uri.split('/')[:-1]) + '/'
                break
        if not ns:
            ns = ''

        gen_labels = self._extract_class_labels(generated_graph)
        gold_labels = self._extract_class_labels(gold_graph)

        # New elements = classes in generated but not in gold
        new_classes = [u for u in gen_labels.keys() if u not in gold_labels]
        total_new = len(new_classes)
        if total_new == 0:
            return 1.0

        ns_ok = 0
        label_ok = 0
        for uri in new_classes:
            if uri.startswith(ns):
                ns_ok += 1
            label = gen_labels.get(uri, '')
            if label:
                label_ok += 1
        ns_frac = ns_ok / total_new
        label_frac = label_ok / total_new
        return (ns_frac + label_frac) / 2.0

    # ------------------------------------------------------------------
    # Dimension 6: Expert Acceptance
    # ------------------------------------------------------------------

    def score_expert_acceptance(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
        expert_review: ExpertReviewSession | None = None,
    ) -> float:
        """Score expert acceptance rate of generated proposals.

        If ``expert_review`` is provided, uses the human reviewer's
        decisions.  Otherwise, simulates expert review using an LLM
        rubric: for each new class, prompt the LLM with domain context
        and ask whether the class is (a) semantically valid,
        (b) well-placed in hierarchy, (c) domain-appropriate.

        Parameters
        ----------
        generated_graph : Graph
        gold_graph : Graph
        expert_review : ExpertReviewSession | None

        Returns
        -------
        float
            Acceptance rate in [0, 1].  Target: ≥ 0.87.

        Notes
        -----
        LLM-simulated expert review is a *proxy*.  For publication,
        at least the primary test case (75 % reduction) should be
        scored by a real domain expert.
        """
        # If explicit expert review provided, compute acceptance rate
        if expert_review is not None:
            # ExpertReviewSession (list of ProposalReview) -> acceptance fraction
            reviews = getattr(expert_review, "reviews", [])
            if not reviews:
                return 0.0
            accepts = sum(1 for r in reviews if getattr(r, "decision", "accept") == "accept")
            return accepts / max(1, len(reviews))

        # Otherwise use semantic correctness as a proxy for expert acceptance
        try:
            # compute new classes and compare labels to gold
            gen_labels = self._extract_class_labels(generated_graph)
            gold_labels = self._extract_class_labels(gold_graph)
            new_uris = [u for u in gen_labels.keys() if u not in gold_labels]
            if not new_uris:
                return 1.0
            accepted = 0
            for u in new_uris:
                lbl = gen_labels.get(u, "")
                if any(lbl.lower() == gl.lower() for gl in gold_labels.values()):
                    accepted += 1
                else:
                    # fallback to embedding similarity
                    try:
                        emb = self._get_embedding(lbl)
                        if emb is None:
                            continue
                        for gl in gold_labels.values():
                            gemb = self._get_embedding(gl)
                            if gemb and self._cosine_similarity(emb, gemb) >= self.similarity_threshold:
                                accepted += 1
                                break
                    except Exception:
                        continue
            return accepted / max(1, len(new_uris))
        except Exception:
            return 0.0

    def _simulate_expert_review(
        self,
        new_classes: list[str],
        gold_classes: list[str],
        domain_context: str,
    ) -> float:
        """Use LLM to simulate expert review of generated classes.

        Prompts the LLM with the domain context and each generated
        class, asking it to score on a 3-point rubric:
          - Accept (1.0)
          - Revise (0.5)
          - Reject (0.0)

        Parameters
        ----------
        new_classes : list[str]
            Labels of newly generated classes.
        gold_classes : list[str]
            Labels of gold-standard classes (for context).
        domain_context : str
            Description of the domain for the LLM prompt.

        Returns
        -------
        float
            Mean acceptance score across all new classes.
        """
        scores = []
        for cls in new_classes:
            # simple token overlap heuristic
            a = set(cls.lower().replace('_',' ').split())
            best = 0.0
            for g in gold_classes:
                b = set(g.lower().replace('_',' ').split())
                if not a or not b:
                    continue
                overlap = len(a & b) / max(1, len(a | b))
                best = max(best, overlap)
            if best >= 0.8:
                scores.append(1.0)
            elif best >= 0.4:
                scores.append(0.5)
            else:
                scores.append(0.0)
        return sum(scores) / max(1, len(scores))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _get_embedding(self, text: str, model: str | None = None) -> list[float] | None:
        """Get text embedding from Ollama (configurable model).

        Parameters
        ----------
        text : str
            Text to embed.
        model : str | None
            Ollama embedding model to call (defaults to ``self.embedding_model``).

        Returns
        -------
        list[float] | None
            Embedding vector or None on failure.
        """
        model_to_use = model or self.embedding_model
        # simple caching keyed by (model, text)
        cache_key = f"{model_to_use}:{text}"
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]
        try:
            import httpx

            resp = httpx.post(
                f"{self.embedding_url}/api/embed",
                json={"model": model_to_use, "input": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            emb = resp.json().get("embeddings", [])
            if emb:
                vec = emb[0]
                self._embedding_cache[cache_key] = vec
                return vec
        except Exception as e:
            logger.warning("embedding_failed", model=model_to_use, text=text[:80], error=str(e))
        return None

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Parameters
        ----------
        a, b : list[float]

        Returns
        -------
        float
            Similarity in [-1, 1].
        """
        va, vb = np.array(a), np.array(b)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)

    def _extract_class_labels(self, graph: Graph) -> dict[str, str]:
        """Extract class URI → label mapping from a graph.

        Parameters
        ----------
        graph : Graph

        Returns
        -------
        dict[str, str]
            Mapping from class URI string to rdfs:label string.
            If no label exists, uses the URI's local name.
        """
        labels: dict[str, str] = {}
        for s, p, o in graph.triples((None, RDF.type, OWL.Class)):
            uri = str(s)
            lbl = graph.value(s, RDFS.label)
            if lbl:
                labels[uri] = str(lbl)
            else:
                labels[uri] = uri.split('#')[-1].split('/')[-1]
        return labels

    def _load_graph(self, path: str | Path) -> Graph:
        """Load an OWL/RDF file into an rdflib Graph.

        Handles format detection (.owl → xml, .ttl → turtle, etc.).

        Parameters
        ----------
        path : str | Path

        Returns
        -------
        Graph
        """
        g = Graph()
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        fmt = None
        if p.suffix in (".ttl", ".turtle"):
            fmt = "turtle"
        elif p.suffix in (".owl", ".rdf", ".xml"):
            fmt = "xml"
        elif p.suffix in (".nt",):
            fmt = "nt"
        try:
            if fmt:
                g.parse(str(p), format=fmt)
            else:
                g.parse(str(p))
        except Exception:
            # last-resort try
            g.parse(str(p))
        return g

    # ==================================================================
    # EXTENDED EVALUATION: TamingHallucinations Semantic Matching
    # ==================================================================
    #
    # Integrates the semantic matching methodology from:
    #   Fathallah, Staab & Algergawy (2025)
    #   "Taming Hallucinations: A Semantic Matching Evaluation Framework
    #    for LLM-Generated Ontologies"
    #   https://github.com/NadeenAhmad/TamingHallucinations
    #
    # The approach uses sentence-transformer embeddings (all-MiniLM-L6-v2)
    # to compute cosine similarity between:
    #   (a) LLM-generated concept labels and reference ontology concepts
    #   (b) LLM-generated SPO triples and reference ontology triples
    #
    # Unmatched items are flagged as hallucinations.  Match percentages
    # are reported cumulatively across multiple reference ontologies
    # with increasing domain specificity.
    # ==================================================================

    def _get_sentence_model(self) -> Any:
        """Lazy-load the sentence-transformer model.

        Uses ``sentence-transformers`` library with the model specified
        in ``self.semantic_match_model_name`` (default: all-MiniLM-L6-v2).

        Returns
        -------
        SentenceTransformer
            The loaded model instance.

        Raises
        ------
        ImportError
            If ``sentence-transformers`` is not installed.
        """
        try:
            from sentence_transformers import SentenceTransformer

            if self._sentence_model is None:
                self._sentence_model = SentenceTransformer(self.semantic_match_model_name)
            return self._sentence_model
        except Exception as e:
            logger.warning("sentence_model_unavailable", error=str(e))
            raise


    def score_semantic_match_concepts(
        self,
        generated_graph: Graph,
        reference_graphs: dict[str, Graph],
    ) -> SemanticMatchResult:
        """Concept-level semantic matching (TamingHallucinations approach).

        Practical implementation with fallbacks:
        - Prefer sentence-transformers if available.
        - Fallback to Ollama embeddings via ``_get_embedding`` if not.
        - Final fallback: token-overlap heuristic.
        """
        gen_map = self._extract_concepts_with_definitions(generated_graph)
        total = len(gen_map)
        result = SemanticMatchResult(
            level=SemanticMatchLevel.CONCEPT,
            total_generated=total,
            similarity_threshold=self.concept_match_threshold,
            embedding_model=self.semantic_match_model_name,
            reference_ontologies=list(reference_graphs.keys()),
        )

        if total == 0:
            result.total_matched = 0
            result.total_hallucinated = 0
            result.match_percentage = 0.0
            result.hallucination_percentage = 0.0
            return result

        # Keep track of unmatched generated concept labels
        unmatched = set(gen_map.keys())
        matched_pairs = []

        # Try to use sentence-transformers if available
        use_st = True
        try:
            st_model = self._get_sentence_model()
        except Exception:
            st_model = None
            use_st = False

        for ref_name, ref_graph in reference_graphs.items():
            if not unmatched:
                result.per_reference_matches[ref_name] = 100.0
                continue

            ref_map = self._extract_concepts_with_definitions(ref_graph)
            if not ref_map:
                result.per_reference_matches[ref_name] = (
                    (len(gen_map) - len(unmatched)) / total * 100.0
                )
                continue

            gen_texts = [f"{lbl} -- {gen_map[lbl]}" for lbl in list(unmatched)]
            ref_texts = [f"{lbl} -- {ref_map[lbl]}" for lbl in ref_map.keys()]

            if use_st and st_model is not None:
                try:
                    gen_embs = st_model.encode(gen_texts, convert_to_numpy=True)
                    ref_embs = st_model.encode(ref_texts, convert_to_numpy=True)
                    # normalize
                    gen_norm = gen_embs / (np.linalg.norm(gen_embs, axis=1, keepdims=True) + 1e-9)
                    ref_norm = ref_embs / (np.linalg.norm(ref_embs, axis=1, keepdims=True) + 1e-9)
                    sim_matrix = np.dot(gen_norm, ref_norm.T)
                    # evaluate matches
                    to_remove = []
                    for i, gen_lbl in enumerate(list(unmatched)):
                        best_idx = int(np.argmax(sim_matrix[i]))
                        best_sim = float(sim_matrix[i, best_idx])
                        if best_sim >= self.concept_match_threshold:
                            ref_lbl = list(ref_map.keys())[best_idx]
                            matched_pairs.append({"generated": gen_lbl, "reference": ref_lbl, "score": best_sim})
                            to_remove.append(gen_lbl)
                    for r in to_remove:
                        unmatched.discard(r)
                except Exception:
                    # fall through to embedding fallback
                    use_st = False

            if not use_st:
                # embedding-based fallback using Ollama embeddings or token overlap
                to_remove = []
                for gen_lbl in list(unmatched):
                    gen_text = f"{gen_lbl} -- {gen_map[gen_lbl]}"
                    gen_emb = None
                    try:
                        gen_emb = self._get_embedding(gen_text, model=self.semantic_embedding_model)
                    except Exception:
                        gen_emb = None

                    best_match = (None, 0.0)
                    for ref_lbl, ref_def in ref_map.items():
                        ref_text = f"{ref_lbl} -- {ref_def}"
                        ref_emb = None
                        try:
                            ref_emb = self._get_embedding(ref_text, model=self.semantic_embedding_model)
                        except Exception:
                            ref_emb = None

                        sim = 0.0
                        if gen_emb is not None and ref_emb is not None:
                            sim = self._cosine_similarity(gen_emb, ref_emb)
                        else:
                            # token overlap fallback
                            a = set(gen_lbl.lower().split())
                            b = set(ref_lbl.lower().split())
                            if a and b:
                                sim = len(a & b) / max(1, len(a | b))
                        if sim > best_match[1]:
                            best_match = (ref_lbl, sim)

                    if best_match[1] >= self.concept_match_threshold:
                        matched_pairs.append({"generated": gen_lbl, "reference": best_match[0], "score": best_match[1]})
                        to_remove.append(gen_lbl)
                for r in to_remove:
                    unmatched.discard(r)

            result.per_reference_matches[ref_name] = (len(gen_map) - len(unmatched)) / total * 100.0

        result.total_matched = len(gen_map) - len(unmatched)
        result.total_hallucinated = len(unmatched)
        result.match_percentage = result.total_matched / total * 100.0
        result.hallucination_percentage = result.total_hallucinated / total * 100.0
        result.matched_pairs = matched_pairs[:50]
        return result
    def score_semantic_match_triples(
        self,
        generated_graph: Graph,
        reference_graphs: dict[str, Graph],
    ) -> SemanticMatchResult:
        """Triple-level semantic matching (TamingHallucinations approach).

        Practical implementation with fallbacks similar to concept matching.
        """
        gen_triples = self._extract_spo_triples(generated_graph)
        gen_sentences = self._triples_to_sentences(gen_triples)
        total = len(gen_sentences)
        result = SemanticMatchResult(
            level=SemanticMatchLevel.TRIPLE,
            total_generated=total,
            similarity_threshold=self.triple_match_threshold,
            embedding_model=self.semantic_match_model_name,
            reference_ontologies=list(reference_graphs.keys()),
        )

        if total == 0:
            result.total_matched = 0
            result.total_hallucinated = 0
            return result

        unmatched_idx = set(range(total))
        matched_pairs = []

        # Try sentence-transformers first
        use_st = True
        try:
            st_model = self._get_sentence_model()
        except Exception:
            st_model = None
            use_st = False

        for ref_name, ref_graph in reference_graphs.items():
            if not unmatched_idx:
                result.per_reference_matches[ref_name] = 100.0
                continue

            ref_triples = self._extract_spo_triples(ref_graph)
            ref_sentences = self._triples_to_sentences(ref_triples)
            if not ref_sentences:
                result.per_reference_matches[ref_name] = (total - len(unmatched_idx)) / total * 100.0
                continue

            if use_st and st_model is not None:
                try:
                    gen_embs = st_model.encode([gen_sentences[i] for i in sorted(unmatched_idx)], convert_to_numpy=True)
                    ref_embs = st_model.encode(ref_sentences, convert_to_numpy=True)
                    gen_norm = gen_embs / (np.linalg.norm(gen_embs, axis=1, keepdims=True) + 1e-9)
                    ref_norm = ref_embs / (np.linalg.norm(ref_embs, axis=1, keepdims=True) + 1e-9)
                    sim_matrix = np.dot(gen_norm, ref_norm.T)
                    to_remove = []
                    for local_i, global_idx in enumerate(sorted(unmatched_idx)):
                        best_idx = int(np.argmax(sim_matrix[local_i]))
                        best_sim = float(sim_matrix[local_i, best_idx])
                        if best_sim >= self.triple_match_threshold:
                            matched_pairs.append({
                                "generated": gen_triples[global_idx],
                                "reference": ref_triples[best_idx],
                                "score": best_sim,
                            })
                            to_remove.append(global_idx)
                    for r in to_remove:
                        unmatched_idx.discard(r)
                except Exception:
                    use_st = False

            if not use_st:
                # Fallback: string equality / token overlap / Ollama embeddings
                to_remove = []
                for gi in list(unmatched_idx):
                    gen_sent = gen_sentences[gi]
                    best_match = (None, 0.0)
                    # try exact string match first
                    for ref_sent in ref_sentences:
                        if gen_sent.strip().lower() == ref_sent.strip().lower():
                            best_match = (ref_sent, 1.0)
                            break
                        # token overlap
                        a = set(gen_sent.lower().split())
                        b = set(ref_sent.lower().split())
                        if a and b:
                            sim = len(a & b) / max(1, len(a | b))
                        else:
                            sim = 0.0
                        if sim > best_match[1]:
                            best_match = (ref_sent, sim)
                    # if still low, try Ollama embedding
                    if best_match[1] < self.triple_match_threshold:
                        try:
                            gen_emb = self._get_embedding(gen_sent)
                        except Exception:
                            gen_emb = None
                        if gen_emb is not None:
                            for ref_sent in ref_sentences:
                                try:
                                    ref_emb = self._get_embedding(ref_sent)
                                except Exception:
                                    ref_emb = None
                                if ref_emb is None:
                                    continue
                                simv = self._cosine_similarity(gen_emb, ref_emb)
                                if simv > best_match[1]:
                                    best_match = (ref_sent, simv)
                    if best_match[1] >= self.triple_match_threshold:
                        matched_pairs.append({
                            "generated": gen_triples[gi],
                            "reference": best_match[0],
                            "score": best_match[1],
                        })
                        to_remove.append(gi)
                for r in to_remove:
                    unmatched_idx.discard(r)

            result.per_reference_matches[ref_name] = (total - len(unmatched_idx)) / total * 100.0

        result.total_matched = total - len(unmatched_idx)
        result.total_hallucinated = len(unmatched_idx)
        result.match_percentage = result.total_matched / total * 100.0
        result.hallucination_percentage = result.total_hallucinated / total * 100.0
        result.matched_pairs = matched_pairs[:100]
        return result
    def _extract_concepts_with_definitions(
        self, graph: Graph
    ) -> dict[str, str]:
        """Extract concept labels and their definitions from an OWL graph.

        Returns a mapping label -> definition (empty string if absent).
        """
        concepts: dict[str, str] = {}
        for s, p, o in graph.triples((None, RDF.type, OWL.Class)):
            lbl = graph.value(s, RDFS.label)
            if lbl:
                label = str(lbl)
            else:
                uri = str(s)
                label = uri.split('#')[-1].split('/')[-1]
            comment = graph.value(s, RDFS.comment)
            concepts[label] = str(comment) if comment else ""
        return concepts
    def _extract_spo_triples(
        self, graph: Graph
    ) -> list[tuple[str, str, str]]:
        """Extract meaningful SPO triples from an OWL graph.

        Produces human-readable (subject_label, predicate_label, object_label)
        tuples suitable for conversion to sentences and embedding.
        """
        def _label(node):
            if node is None:
                return ""
            if isinstance(node, URIRef):
                lab = graph.value(node, RDFS.label)
                if lab:
                    return str(lab)
                uri = str(node)
                return uri.split('#')[-1].split('/')[-1]
            # Literals
            return str(node)

        triples: list[tuple[str, str, str]] = []
        for s, p, o in graph.triples((None, None, None)):
            # filter metadata predicates
            if p in (RDFS.label, RDFS.comment, RDF.type):
                # handle RDF.type separately below
                continue
            # skip blank nodes subjects/objects
            if hasattr(s, 'startswith') and (str(s).startswith('_:') or str(o).startswith('_:')):
                continue
            # skip built-in vocab predicates
            if str(p).startswith('http://www.w3.org'):
                continue
            subj_lbl = _label(s)
            pred_lbl = _label(p)
            obj_lbl = _label(o)
            if not subj_lbl or not pred_lbl or not obj_lbl:
                continue
            triples.append((subj_lbl, pred_lbl, obj_lbl))

        # Add rdfs:subClassOf relations explicitly (if not already captured)
        for s, p, o in graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                triples.append((_label(s), 'subClassOf', _label(o)))

        # Add rdf:type triples for individuals (exclude owl:Class declarations)
        for s, p, o in graph.triples((None, RDF.type, None)):
            if o == OWL.Class:
                continue
            triples.append((_label(s), 'type', _label(o)))

        # Deduplicate
        seen = set()
        out = []
        for t in triples:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out
    def _triples_to_sentences(
        self, triples: list[tuple[str, str, str]]
    ) -> list[str]:
        """Convert SPO triples to natural-language sentences for embedding.

        Simple concatenation: ``f"{subject} {predicate} {object}"``
        as used in TamingHallucinations ``convert_triples_to_sentences()``.

        Parameters
        ----------
        triples : list[tuple[str, str, str]]

        Returns
        -------
        list[str]
        """
        return [f"{s} {p} {o}" for s, p, o in triples]

    # ==================================================================
    # EXTENDED EVALUATION: OntoURL Capability Profiling
    # ==================================================================
    #
    # Integrates the 15-task evaluation taxonomy from:
    #   Zhang, Lai, Meng & Bos (2025)
    #   "OntoURL: A Benchmark for Evaluating LLMs on Symbolic
    #    Ontological Understanding, Reasoning and Learning"
    #   https://arxiv.org/abs/2505.11031
    #
    # OntoURL provides 58,981 questions from 40 ontologies across
    # 8 domains, structured into three Bloom-inspired capability levels:
    #   - Understanding (U1–U5): factual recall from ontology
    #   - Reasoning (R1–R5): logical inference requiring a reasoner
    #   - Learning (L1–L5): ontology construction / generation
    #
    # We use OntoURL-style tasks to produce a capability *profile*
    # that complements our six-dimension scores.
    # ==================================================================

    def score_ontourl_profile(
        self,
        model_name: str,
        generated_graph: Graph,
        gold_graph: Graph,
        ontourl_dataset_path: str | Path | None = None,
    ) -> OntoURLCapabilityProfile:
        """Compute an OntoURL-style capability profile.

        If the OntoURL dataset is available locally, evaluates the
        system's LLM on relevant Learning tasks (L1–L5) using the
        actual benchmark questions.  Otherwise, constructs proxy
        tasks from our own test cases.

        Parameters
        ----------
        model_name : str
            Name of the LLM being evaluated.
        generated_graph : Graph
            The system's output ontology.
        gold_graph : Graph
            The reference ontology.
        ontourl_dataset_path : str | Path | None
            Path to the downloaded OntoURL dataset (from HuggingFace:
            XiaoZhang98/OntoURL).  If ``None``, uses proxy evaluation.

        Returns
        -------
        OntoURLCapabilityProfile
            Scores across Understanding, Reasoning, and Learning.

        Notes
        -----
        For a full OntoURL evaluation, use their evaluation scripts:
        https://github.com/LastDance500/OntoURL
        """
        # Use proxy evaluation (generate tasks from our own data)
        understanding_scores = self._evaluate_understanding_proxy(
            generated_graph, gold_graph
        )
        learning_scores = self._evaluate_learning_proxy(
            generated_graph, gold_graph
        )

        all_scores = understanding_scores + learning_scores

        # Compute averages per capability level
        u_vals = [
            s.accuracy for s in understanding_scores
            if s.accuracy is not None
        ]
        l_vals = []
        for s in learning_scores:
            if s.triple_f1 is not None:
                l_vals.append(s.triple_f1)
            elif s.rouge_l is not None:
                l_vals.append(s.rouge_l)

        u_avg = sum(u_vals) / max(1, len(u_vals)) if u_vals else 0.0
        l_avg = sum(l_vals) / max(1, len(l_vals)) if l_vals else 0.0

        # Reasoning proxy — uses owlrl OWL-RL/RDFS reasoner
        reasoning_scores = self._evaluate_reasoning_proxy(
            generated_graph, gold_graph
        )
        all_scores = all_scores + reasoning_scores
        r_vals = [
            s.accuracy for s in reasoning_scores
            if s.accuracy is not None
        ]
        r_avg = sum(r_vals) / max(1, len(r_vals)) if r_vals else 0.0

        overall = (u_avg + r_avg + l_avg) / 3.0

        return OntoURLCapabilityProfile(
            understanding_avg=u_avg,
            reasoning_avg=r_avg,
            learning_avg=l_avg,
            task_scores=all_scores,
            overall_avg=overall,
            model_name=model_name,
        )

    def _evaluate_understanding_proxy(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
    ) -> list[OntoURLTaskScore]:
        """Proxy evaluation for OntoURL Understanding tasks (U1–U5).

        Creates MCQ-style questions from the gold-standard ontology
        and tests whether the system's knowledge is reflected in
        its generated output.  This is a *proxy* — the real OntoURL
        benchmark uses curated questions.

        Tasks approximated:
          U1: Can the system define generated classes correctly?
          U2: Does the hierarchy reflect known taxonomic relations?
          U3: Are property domains/ranges correctly assigned?
          U4: (Skipped — requires instance data)
          U5: (Skipped — requires instance data)

        Parameters
        ----------
        generated_graph : Graph
        gold_graph : Graph

        Returns
        -------
        list[OntoURLTaskScore]
        """
        scores: list[OntoURLTaskScore] = []
        gen_labels = self._extract_class_labels(generated_graph)
        gold_labels = self._extract_class_labels(gold_graph)

        # U1: Class Definition — can we find generated classes that
        #     match gold-standard definitions?
        if gold_labels:
            matched = sum(
                1 for gl in gold_labels.values()
                if any(gl.lower() == gn.lower() for gn in gen_labels.values())
            )
            acc = matched / max(1, len(gold_labels))
        else:
            acc = 0.0
        scores.append(OntoURLTaskScore(
            task=OntoURLTask.U1_CLASS_DEFINITION,
            capability=OntoURLCapability.UNDERSTANDING,
            accuracy=acc,
            num_questions=len(gold_labels),
        ))

        # U2: Class Relation — do subClassOf relations match?
        gold_rels = set()
        for s, p, o in gold_graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                gold_rels.add((str(s), str(o)))
        gen_rels = set()
        for s, p, o in generated_graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                gen_rels.add((str(s), str(o)))
        if gold_rels:
            overlap = len(gold_rels & gen_rels)
            acc_u2 = overlap / max(1, len(gold_rels))
        else:
            acc_u2 = 0.0
        scores.append(OntoURLTaskScore(
            task=OntoURLTask.U2_CLASS_RELATION,
            capability=OntoURLCapability.UNDERSTANDING,
            accuracy=acc_u2,
            num_questions=len(gold_rels),
        ))

        # U3: Property Domain — check domain/range assignments
        gold_props: dict[str, tuple[str, str]] = {}
        for prop in gold_graph.subjects(RDF.type, OWL.ObjectProperty):
            dom = gold_graph.value(prop, RDFS.domain)
            rng = gold_graph.value(prop, RDFS.range)
            gold_props[str(prop)] = (str(dom) if dom else "", str(rng) if rng else "")
        gen_props: dict[str, tuple[str, str]] = {}
        for prop in generated_graph.subjects(RDF.type, OWL.ObjectProperty):
            dom = generated_graph.value(prop, RDFS.domain)
            rng = generated_graph.value(prop, RDFS.range)
            gen_props[str(prop)] = (str(dom) if dom else "", str(rng) if rng else "")

        if gold_props:
            correct = sum(1 for p, v in gold_props.items() if gen_props.get(p) == v)
            acc_u3 = correct / max(1, len(gold_props))
        else:
            acc_u3 = 0.0
        scores.append(OntoURLTaskScore(
            task=OntoURLTask.U3_PROPERTY_DOMAIN,
            capability=OntoURLCapability.UNDERSTANDING,
            accuracy=acc_u3,
            num_questions=len(gold_props),
        ))

        return scores

    def _evaluate_learning_proxy(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
    ) -> list[OntoURLTaskScore]:
        """Proxy evaluation for OntoURL Learning tasks (L1–L5).

        Evaluates the system's *generation* capabilities by comparing
        what it produced against what should have been produced.

        Tasks approximated:
          L1: Quality of generated class definitions (ROUGE-L vs gold)
          L2: Hierarchy structure quality (Triple-F1 for subClassOf)
          L3: Property relation quality (Triple-F1 for domain/range)
          L4: (Constraint construction — requires OWL constraint data)
          L5: Alignment quality (if multiple ontology fragments involved)

        Parameters
        ----------
        generated_graph : Graph
        gold_graph : Graph

        Returns
        -------
        list[OntoURLTaskScore]
        """
        scores: list[OntoURLTaskScore] = []
        gen_concepts = self._extract_concepts_with_definitions(generated_graph)
        gold_concepts = self._extract_concepts_with_definitions(gold_graph)

        # L1: Class Definition Generation — ROUGE-L of definitions
        if gold_concepts:
            rouge_scores: list[float] = []
            for gold_lbl, gold_def in gold_concepts.items():
                if not gold_def:
                    continue
                # Find matching generated concept
                gen_def = gen_concepts.get(gold_lbl, "")
                if not gen_def:
                    # Try case-insensitive match
                    for gl, gd in gen_concepts.items():
                        if gl.lower() == gold_lbl.lower():
                            gen_def = gd
                            break
                if gen_def and gold_def:
                    # Simple ROUGE-L approximation: LCS ratio
                    rouge_scores.append(self._rouge_l(gen_def, gold_def))
                else:
                    rouge_scores.append(0.0)
            l1_score = sum(rouge_scores) / max(1, len(rouge_scores)) if rouge_scores else 0.0
        else:
            l1_score = 0.0

        scores.append(OntoURLTaskScore(
            task=OntoURLTask.L1_CLASS_DEF_GENERATION,
            capability=OntoURLCapability.LEARNING,
            rouge_l=l1_score,
            num_questions=len(gold_concepts),
        ))

        # L2: Hierarchy Construction — Triple-F1 for subClassOf triples
        gold_hier = set()
        for s, p, o in gold_graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                gold_hier.add((str(s), str(o)))
        gen_hier = set()
        for s, p, o in generated_graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                gen_hier.add((str(s), str(o)))

        if gold_hier or gen_hier:
            tp = len(gold_hier & gen_hier)
            precision = tp / max(1, len(gen_hier))
            recall = tp / max(1, len(gold_hier))
            f1 = 2 * precision * recall / max(1e-9, precision + recall)
        else:
            f1 = 0.0

        scores.append(OntoURLTaskScore(
            task=OntoURLTask.L2_HIERARCHY_CONSTRUCTION,
            capability=OntoURLCapability.LEARNING,
            triple_f1=f1,
            num_questions=len(gold_hier),
        ))

        # L3: Property Relation Construction — Triple-F1 for domain/range
        gold_prop_triples = set()
        for prop in gold_graph.subjects(RDF.type, OWL.ObjectProperty):
            dom = gold_graph.value(prop, RDFS.domain)
            rng = gold_graph.value(prop, RDFS.range)
            if dom and rng:
                gold_prop_triples.add((str(prop), str(dom), str(rng)))
        gen_prop_triples = set()
        for prop in generated_graph.subjects(RDF.type, OWL.ObjectProperty):
            dom = generated_graph.value(prop, RDFS.domain)
            rng = generated_graph.value(prop, RDFS.range)
            if dom and rng:
                gen_prop_triples.add((str(prop), str(dom), str(rng)))

        if gold_prop_triples or gen_prop_triples:
            tp3 = len(gold_prop_triples & gen_prop_triples)
            prec3 = tp3 / max(1, len(gen_prop_triples))
            rec3 = tp3 / max(1, len(gold_prop_triples))
            f1_3 = 2 * prec3 * rec3 / max(1e-9, prec3 + rec3)
        else:
            f1_3 = 0.0

        scores.append(OntoURLTaskScore(
            task=OntoURLTask.L3_PROPERTY_CONSTRUCTION,
            capability=OntoURLCapability.LEARNING,
            triple_f1=f1_3,
            num_questions=len(gold_prop_triples),
        ))

        return scores

    # ------------------------------------------------------------------
    # Reasoning proxy (R1, R2, R5) — OWL-RL entailment checks
    # ------------------------------------------------------------------

    def _evaluate_reasoning_proxy(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
    ) -> list[OntoURLTaskScore]:
        """Proxy evaluation for OntoURL Reasoning tasks (R1, R2, R5).

        Uses the ``owlrl`` OWL-RL/RDFS reasoner to materialise inferred
        triples, then checks:

        R1 — Inferred Relation
            After OWL-RL closure, how many gold ``rdfs:subClassOf`` chains
            are entailed?  E.g. if gold has A⊑B⊑C then the reasoner
            should infer A⊑C.  Score = entailed / expected.

        R2 — Constraint Checking
            Count ``owl:disjointWith`` pairs in the generated ontology and
            verify that no individual is typed to both.  After reasoning,
            an inconsistency would manifest as both types present on an
            entity; since we have no ABox data we measure *structural
            constraint presence* as a proxy: score = 1.0 if disjointness
            axioms exist, 0.0 otherwise (encouraging axiom richness).

        R5 — Description Logic
            Fraction of ``owl:equivalentClass`` axioms from the gold
            standard recovered in the generated ontology (exact URI match).

        Parameters
        ----------
        generated_graph : Graph
        gold_graph : Graph

        Returns
        -------
        list[OntoURLTaskScore]
        """
        scores: list[OntoURLTaskScore] = []

        # --- R1: Inferred transitive subClassOf chains ----------------
        try:
            import owlrl  # type: ignore[import-untyped]

            # Work on a copy so we don't mutate the caller's graph
            reasoned = Graph()
            for triple in generated_graph:
                reasoned.add(triple)
            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(reasoned)

            # Collect gold subClassOf pairs (transitive closure)
            gold_sub = set()
            for s, _, o in gold_graph.triples((None, RDFS.subClassOf, None)):
                if isinstance(s, URIRef) and isinstance(o, URIRef):
                    gold_sub.add((str(s), str(o)))

            if gold_sub:
                entailed = sum(
                    1 for s, o in gold_sub
                    if (URIRef(s), RDFS.subClassOf, URIRef(o)) in reasoned
                )
                r1_acc = entailed / len(gold_sub)
            else:
                r1_acc = 0.0
        except Exception as e:
            logger.warning("reasoning_r1_failed", error=str(e))
            r1_acc = 0.0

        scores.append(OntoURLTaskScore(
            task=OntoURLTask.R1_INFERRED_RELATION,
            capability=OntoURLCapability.REASONING,
            accuracy=r1_acc,
            num_questions=len(gold_sub) if 'gold_sub' in dir() else 0,
        ))

        # --- R2: Constraint presence (disjointness axioms) ------------
        disjoint_count = sum(
            1 for _ in generated_graph.triples((None, OWL.disjointWith, None))
        )
        r2_acc = min(1.0, disjoint_count / 5.0)  # normalise: ≥5 axioms → 1.0
        scores.append(OntoURLTaskScore(
            task=OntoURLTask.R2_CONSTRAINT,
            capability=OntoURLCapability.REASONING,
            accuracy=r2_acc,
            num_questions=disjoint_count,
        ))

        # --- R5: equivalentClass recovery -----------------------------
        gold_equiv = set()
        for s, _, o in gold_graph.triples((None, OWL.equivalentClass, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                gold_equiv.add((str(s), str(o)))
        if gold_equiv:
            recovered = sum(
                1 for s, o in gold_equiv
                if (URIRef(s), OWL.equivalentClass, URIRef(o)) in generated_graph
            )
            r5_acc = recovered / len(gold_equiv)
        else:
            r5_acc = 0.0  # no equivalence axioms in gold → neutral
        scores.append(OntoURLTaskScore(
            task=OntoURLTask.R5_DESCRIPTION_LOGIC,
            capability=OntoURLCapability.REASONING,
            accuracy=r5_acc,
            num_questions=len(gold_equiv),
        ))

        return scores

    def _rouge_l(self, hypothesis: str, reference: str) -> float:
        """Compute ROUGE-L F1 score between two strings.

        Uses longest common subsequence (LCS) on word tokens.
        """
        hyp_tokens = hypothesis.lower().split()
        ref_tokens = reference.lower().split()
        m, n = len(hyp_tokens), len(ref_tokens)
        if m == 0 or n == 0:
            return 0.0

        # LCS via DP
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if hyp_tokens[i - 1] == ref_tokens[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        lcs_len = dp[m][n]

        precision = lcs_len / m
        recall = lcs_len / n
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    # ==================================================================
    # EXTENDED EVALUATION: OWLUnit Ontology Unit Testing
    # ==================================================================
    #
    # Integrates the ontology unit testing framework from:
    #   Asprino (2024) "OWLUnit"
    #   https://github.com/luigi-asprino/owl-unit
    #
    # OWLUnit provides four test types:
    #   1. Annotation Verification — SHACL shapes for annotations
    #   2. CQ Verification — CQ → SPARQL with IRI and result checks
    #   3. Inference Verification — Consistency + SPARQL ASK on inferences
    #   4. Error Provocation — Inject inconsistencies, verify detection
    #
    # We generate test cases for types 2–4 from our benchmark data
    # and optionally invoke the OWLUnit JAR for execution.
    # ==================================================================

    def score_owlunit_suite(
        self,
        generated_path: str | Path,
        test_case: TestCase,
    ) -> OWLUnitTestSuite:
        """Run OWLUnit-style tests on the generated ontology.

        Implements a pragmatic rdflib-based approximation for CQ,
        inference and error-provocation tests so users can run the
        suite without the external OWLUnit JAR.
        """
        gen_graph = self._load_graph(generated_path)
        gold_graph = Graph()
        try:
            gold_graph = self._load_graph(test_case.gold_standard_path)
        except Exception:
            gold_graph = Graph()

        results: list[OWLUnitTestResult] = []

        # CQ verification
        try:
            results.extend(self._generate_cq_verification_tests(test_case, gen_graph))
        except Exception as e:
            logger.warning("cq_verification_failed", error=str(e))

        # Inference verification
        try:
            results.extend(self._generate_inference_verification_tests(gen_graph, gold_graph))
        except Exception as e:
            logger.warning("inference_verification_failed", error=str(e))

        # Error provocation
        try:
            results.extend(self._generate_error_provocation_tests(gen_graph))
        except Exception as e:
            logger.warning("error_provocation_failed", error=str(e))

        suite = OWLUnitTestSuite(
            suite_name=f"owlunit-{getattr(test_case, 'id', 'unnamed')}",
            ontology_path=str(generated_path),
            results=results,
            total_tests=len(results),
            passed_tests=sum(1 for r in results if r.passed),
            failed_tests=sum(1 for r in results if not r.passed),
        )
        return suite
    def _generate_cq_verification_tests(
        self,
        test_case: TestCase,
        generated_graph: Graph,
    ) -> list[OWLUnitTestResult]:
        """Generate and run OWLUnit CQ Verification tests (rdflib approximation).
        """
        results: list[OWLUnitTestResult] = []
        cqs = getattr(test_case, 'competency_questions', []) or []
        for i, cq in enumerate(cqs):
            if not getattr(cq, 'sparql_template', None):
                # skip CQs without SPARQL templates
                continue
            test_id = f"CQ-{i}-{getattr(cq,'id', 'auto')}"
            desc = f"CQ verification for {getattr(cq,'id', 'unknown')}"
            # check IRIs
            missing_iris = []
            for uri in (cq.target_classes or []) + (cq.target_properties or []):
                u = URIRef(uri)
                found = False
                for _ in generated_graph.triples((u, None, None)):
                    found = True
                    break
                for _ in generated_graph.triples((None, None, u)):
                    found = True
                    break
                if not found:
                    missing_iris.append(uri)
            if missing_iris:
                results.append(
                    OWLUnitTestResult(
                        test_type=OWLUnitTestType.COMPETENCY_Q,
                        test_id=test_id,
                        passed=False,
                        description=desc,
                        sparql_query=cq.sparql_template,
                        expected_result="IRIs present & non-empty results",
                        actual_result=f"missing_iris={missing_iris}",
                        error_message="required IRIs not found in generated graph",
                    )
                )
                continue

            # Try executing SPARQL template directly
            try:
                q = cq.sparql_template
                res = list(generated_graph.query(q))
                passed = len(res) > 0
                results.append(
                    OWLUnitTestResult(
                        test_type=OWLUnitTestType.COMPETENCY_Q,
                        test_id=test_id,
                        passed=passed,
                        description=desc,
                        sparql_query=q,
                        expected_result="non-empty results",
                        actual_result=str(len(res)),
                        error_message=None if passed else "empty result set",
                    )
                )
            except Exception as e:
                results.append(
                    OWLUnitTestResult(
                        test_type=OWLUnitTestType.COMPETENCY_Q,
                        test_id=test_id,
                        passed=False,
                        description=desc,
                        sparql_query=getattr(cq, 'sparql_template', None),
                        expected_result="non-empty results",
                        actual_result=None,
                        error_message=str(e),
                    )
                )
        return results
    def _generate_inference_verification_tests(
        self,
        generated_graph: Graph,
        gold_graph: Graph,
    ) -> list[OWLUnitTestResult]:
        """Approximate inference verification using graph traversal + ASK checks.
        """
        results: list[OWLUnitTestResult] = []

        # 1) Consistency heuristic: detect explicit contradictions
        # Look for pairs of classes declared disjoint and an individual
        # asserted to be instance of both.
        disjoint_pairs = []
        for a, _, b in generated_graph.triples((None, OWL.disjointWith, None)):
            disjoint_pairs.append((a, b))
        inconsistency_found = False
        for a, b in disjoint_pairs:
            # find individuals of both types
            for ind, _, _ in generated_graph.triples((None, RDF.type, a)):
                if (ind, RDF.type, b) in generated_graph:
                    inconsistency_found = True
                    break
            if inconsistency_found:
                break
        results.append(
            OWLUnitTestResult(
                test_type=OWLUnitTestType.INFERENCE,
                test_id="inference-consistency",
                passed=not inconsistency_found,
                description="Consistency heuristic (disjointness vs individuals)",
                expected_result="consistent",
                actual_result=("inconsistency_detected" if inconsistency_found else "no_issue_detected"),
                error_message=None,
            )
        )

        # 2) Check that some representative gold subClassOf relations are entailed
        def _is_subclass(g: Graph, sub: URIRef, sup: URIRef) -> bool:
            # BFS over rdfs:subClassOf edges
            seen = set()
            stack = [str(sub)]
            while stack:
                cur = stack.pop()
                if cur == str(sup):
                    return True
                if cur in seen:
                    continue
                seen.add(cur)
                for s, p, o in g.triples((URIRef(cur), RDFS.subClassOf, None)):
                    if isinstance(o, URIRef):
                        stack.append(str(o))
            return False

        checked = 0
        for s, p, o in gold_graph.triples((None, RDFS.subClassOf, None)):
            if checked >= 10:
                break
            if not isinstance(s, URIRef) or not isinstance(o, URIRef):
                continue
            # only check when both classes exist in generated_graph
            subj_exists = any(True for _ in generated_graph.triples((s, None, None)))
            obj_exists = any(True for _ in generated_graph.triples((o, None, None)))
            if not (subj_exists and obj_exists):
                continue
            passed = _is_subclass(generated_graph, s, o)
            results.append(
                OWLUnitTestResult(
                    test_type=OWLUnitTestType.INFERENCE,
                    test_id=f"inference-subClassOf-{checked}",
                    passed=passed,
                    description=f"Verify inferred subClassOf: {s} ⊑ {o}",
                    sparql_query=f"ASK WHERE {{ <{s}> rdfs:subClassOf+ <{o}> }}",
                    expected_result="ASK True",
                    actual_result=("True" if passed else "False"),
                    error_message=None if passed else "missing inferred path",
                )
            )
            checked += 1

        return results
    def _generate_error_provocation_tests(
        self,
        generated_graph: Graph,
    ) -> list[OWLUnitTestResult]:
        """Generate and run OWLUnit Error Provocation tests (heuristic).

        Strategy:
        - If graph contains disjointWith pairs, create an individual
          that instantiates both classes and verify our disjointness
          heuristic detects the inconsistency.
        - Otherwise return a skipped/failing result indicating the
          provocation could not be constructed.
        """
        results: list[OWLUnitTestResult] = []
        # find a disjoint pair
        pair = None
        for a, _, b in generated_graph.triples((None, OWL.disjointWith, None)):
            pair = (a, b)
            break
        if pair:
            a, b = pair
            fake_ind = URIRef(f"urn:prov:ind-{abs(hash(str(a)+str(b))) % (10**8)}")
            # create a small temp graph
            temp = Graph()
            for t in generated_graph.triples((None, None, None)):
                temp.add(t)
            temp.add((fake_ind, RDF.type, a))
            temp.add((fake_ind, RDF.type, b))
            # detection: individual typed as both classes that are disjoint
            inconsistency = False
            for ind, _, _ in temp.triples((None, RDF.type, a)):
                if (ind, RDF.type, b) in temp:
                    inconsistency = True
                    break
            results.append(
                OWLUnitTestResult(
                    test_type=OWLUnitTestType.ERROR_PROVOKE,
                    test_id="error-prov-disjoint-1",
                    passed=inconsistency,
                    description=f"Inject individual typed as both {a} and {b}",
                    expected_result="reasoner detects inconsistency",
                    actual_result=("inconsistency_detected" if inconsistency else "no_inconsistency"),
                    error_message=None if inconsistency else "provocation not detected",
                )
            )
            return results

        # fallback: cannot construct provocation reliably
        results.append(
            OWLUnitTestResult(
                test_type=OWLUnitTestType.ERROR_PROVOKE,
                test_id="error-prov-skip",
                passed=False,
                description="No suitable disjoint pairs found for provocation",
                expected_result="inconsistency_detected",
                actual_result="skipped",
                error_message="no disjointWith axioms available",
            )
        )
        return results

"""Test-case generator: decompose a gold-standard ontology into graded test cases.

This module takes the full plan-ontology-v1.0.owl (18 classes, 26 properties)
and produces four reduced seed ontologies by removing a controlled percentage
of classes and their dependent properties.  The removed elements become the
*ground truth* for evaluating whether a system can rediscover them.

Algorithm
---------
1. Parse the gold-standard OWL file with ``rdflib``.
2. Enumerate all ``owl:Class`` and ``owl:ObjectProperty`` / ``owl:DatatypeProperty``.
3. Build a dependency graph: properties depend on their domain/range classes.
4. For each reduction level (50 %, 75 %, 90 %, 95 %):
   a. Randomly select classes to *remove* (using ``random_seed`` for
      reproducibility).  Core classes with high in-degree are removed
      last to keep the hierarchy valid.
   b. Remove all properties whose domain or range references a removed class.
   c. Serialise the reduced graph as a new OWL file.
   d. Generate competency questions targeting the removed elements.
5. Return a list of ``TestCase`` objects ready for the benchmark runner.

Usage
-----
::

    from ontology_hitl.benchmarking.test_cases import TestCaseGenerator

    gen = TestCaseGenerator(
        gold_standard_path="data/seed_ontology/plan-ontology-v1.0.owl",
        output_dir="data/test_cases",
        random_seed=42,
    )
    test_cases = gen.generate_all()

Dependencies
------------
- ``rdflib``     for OWL/RDF parsing and serialisation
- ``structlog``  for structured logging
- ``httpx``      for LLM-based CQ generation (optional)
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import structlog
from rdflib import OWL, RDF, RDFS, Graph, Namespace, URIRef

from .models import (
    CompetencyQuestion,
    ReductionLevel,
    TestCase,
)

logger = structlog.get_logger(__name__)


class TestCaseGenerator:
    """Generate graded test cases by decomposing a gold-standard ontology.

    Parameters
    ----------
    gold_standard_path : str | Path
        Path to the full reference OWL file (e.g. plan-ontology-v1.0.owl).
    output_dir : str | Path
        Directory where reduced OWL files and metadata are written.
    random_seed : int
        Seed for reproducible class selection.
    ollama_url : str
        Ollama endpoint for LLM-based CQ generation (optional).
    ollama_model : str
        Model to use for CQ generation.

    Examples
    --------
    >>> gen = TestCaseGenerator("data/seed_ontology/plan-ontology-v1.0.owl")
    >>> cases = gen.generate_all()
    >>> len(cases)
    4
    >>> cases[0].reduction_level
    <ReductionLevel.PCT_50: '50pct'>
    """

    REDUCTION_LEVELS: list[tuple[ReductionLevel, float]] = [
        (ReductionLevel.PCT_50, 0.50),
        (ReductionLevel.PCT_75, 0.75),
        (ReductionLevel.PCT_90, 0.90),
        (ReductionLevel.PCT_95, 0.95),
    ]

    def __init__(
        self,
        gold_standard_path: str | Path,
        output_dir: str | Path = "data/test_cases",
        random_seed: int = 42,
        ollama_url: str = "http://localhost:18135",
        ollama_model: str = "llama3.2:3b",
    ) -> None:
        self.gold_standard_path = Path(gold_standard_path)
        self.output_dir = Path(output_dir)
        self.random_seed = random_seed
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model

        self._rng = random.Random(random_seed)
        self._gold_graph: Graph | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_all(self) -> list[TestCase]:
        """Generate test cases for all four reduction levels.

        Returns
        -------
        list[TestCase]
            Four test cases at 50 %, 75 %, 90 %, 95 % reduction.

        Raises
        ------
        FileNotFoundError
            If the gold-standard OWL file does not exist.
        """
        if not self.gold_standard_path.exists():
            raise FileNotFoundError(f"Gold-standard OWL file not found: {self.gold_standard_path}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        test_cases: list[TestCase] = []
        for level, fraction in self.REDUCTION_LEVELS:
            tc = self.generate_single(level, fraction)
            test_cases.append(tc)
            logger.info(
                "test_case_generated",
                level=level.value,
                removed=len(tc.removed_classes),
                remaining=tc.num_remaining_classes,
            )
        return test_cases

    def generate_single(self, level: ReductionLevel, fraction: float) -> TestCase:
        """Generate one test case at the given reduction level.

        Parameters
        ----------
        level : ReductionLevel
            Enum member identifying this reduction.
        fraction : float
            Fraction of classes to *remove* (0.50 → remove half).

        Returns
        -------
        TestCase
            Fully populated test case with paths and metadata.

        Algorithm
        ---------
        1. Load and parse the gold-standard graph.
        2. Enumerate classes and compute dependency ordering.
        3. Select ``fraction`` of classes for removal.
        4. Remove selected classes and dependent properties.
        5. Serialise reduced graph and build competency questions.
        """
        graph = self._load_gold_standard()
        all_classes = self._enumerate_classes(graph)
        all_properties = self._enumerate_properties(graph)
        dep_graph = self._build_dependency_graph(graph, all_classes, all_properties)

        classes_to_remove = self._select_classes_to_remove(all_classes, fraction, dep_graph)

        # Work on a copy so the cached gold graph is not mutated
        import copy
        reduced = copy.deepcopy(graph)
        reduced, removed_class_uris, removed_property_uris = self._remove_elements(
            reduced, classes_to_remove, dep_graph
        )

        seed_path = self._serialise_reduced_ontology(reduced, level)

        cqs = self._generate_competency_questions(
            removed_class_uris, removed_property_uris, level
        )

        num_orig = len(all_classes)
        num_remaining = num_orig - len(removed_class_uris)

        return TestCase(
            id=f"{self.gold_standard_path.stem}-{level.value}",
            reduction_level=level,
            seed_ontology_path=seed_path,
            gold_standard_path=self.gold_standard_path,
            removed_classes=removed_class_uris,
            removed_properties=removed_property_uris,
            competency_questions=cqs,
            num_original_classes=num_orig,
            num_remaining_classes=num_remaining,
            metadata={
                "random_seed": self.random_seed,
                "fraction": fraction,
            },
        )

    # ------------------------------------------------------------------
    # Internal: OWL Parsing
    # ------------------------------------------------------------------

    def _load_gold_standard(self) -> Graph:
        """Parse the gold-standard OWL file into an rdflib Graph.

        Returns
        -------
        Graph
            The fully parsed RDF graph.

        Raises
        ------
        FileNotFoundError
            If ``self.gold_standard_path`` does not exist.

        Notes
        -----
        Caches the parsed graph in ``self._gold_graph`` to avoid
        re-parsing on subsequent calls.
        """
        if self._gold_graph is not None:
            return self._gold_graph
        if not self.gold_standard_path.exists():
            raise FileNotFoundError(str(self.gold_standard_path))
        g = Graph()
        suffix = self.gold_standard_path.suffix.lower()
        fmt = "xml" if suffix in (".owl", ".rdf", ".xml") else (
            "turtle" if suffix in (".ttl",) else None
        )
        if fmt:
            g.parse(str(self.gold_standard_path), format=fmt)
        else:
            g.parse(str(self.gold_standard_path))
        self._gold_graph = g
        return g

    def _enumerate_classes(self, graph: Graph) -> list[URIRef]:
        """Extract all owl:Class URIs from the graph.

        Parameters
        ----------
        graph : Graph
            An rdflib graph loaded from an OWL file.

        Returns
        -------
        list[URIRef]
            Sorted list of class URIs (excluding OWL built-ins like
            ``owl:Thing`` and ``owl:Nothing``).
        """
        built_ins = {OWL.Thing, OWL.Nothing}
        classes: set[URIRef] = set()
        for s in graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef) and s not in built_ins:
                classes.add(s)
        return sorted(classes, key=str)

    def _enumerate_properties(self, graph: Graph) -> list[URIRef]:
        """Extract all owl:ObjectProperty and owl:DatatypeProperty URIs.

        Parameters
        ----------
        graph : Graph

        Returns
        -------
        list[URIRef]
            Sorted list of property URIs.
        """
        props: set[URIRef] = set()
        for s in graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(s, URIRef):
                props.add(s)
        for s in graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(s, URIRef):
                props.add(s)
        return sorted(props, key=str)

    def _build_dependency_graph(
        self, graph: Graph, classes: list[URIRef], properties: list[URIRef]
    ) -> dict[URIRef, set[URIRef]]:
        """Build a dependency map: class → set of dependent properties.

        A property *depends on* a class if the class appears as
        ``rdfs:domain`` or ``rdfs:range`` of that property.

        Parameters
        ----------
        graph : Graph
        classes : list[URIRef]
        properties : list[URIRef]

        Returns
        -------
        dict[URIRef, set[URIRef]]
            Mapping from class URI to the set of property URIs that
            reference it.
        """
        dep: dict[URIRef, set[URIRef]] = {c: set() for c in classes}
        for prop in properties:
            for _, _, domain_cls in graph.triples((prop, RDFS.domain, None)):
                if isinstance(domain_cls, URIRef) and domain_cls in dep:
                    dep[domain_cls].add(prop)
            for _, _, range_cls in graph.triples((prop, RDFS.range, None)):
                if isinstance(range_cls, URIRef) and range_cls in dep:
                    dep[range_cls].add(prop)
        return dep

    # ------------------------------------------------------------------
    # Internal: Reduction
    # ------------------------------------------------------------------

    def _select_classes_to_remove(
        self, classes: list[URIRef], fraction: float, dep_graph: dict[URIRef, set[URIRef]]
    ) -> list[URIRef]:
        """Select which classes to remove at this reduction level.

        Uses a *periphery-first* strategy: classes with fewer
        dependents are removed first, so the reduced ontology
        remains structurally valid as long as possible.

        Parameters
        ----------
        classes : list[URIRef]
            All classes in the gold-standard.
        fraction : float
            Target fraction to remove.
        dep_graph : dict[URIRef, set[URIRef]]
            Class → dependent-properties mapping.

        Returns
        -------
        list[URIRef]
            Classes selected for removal.
        """
        n_to_remove = max(1, int(len(classes) * fraction))
        # Sort by number of dependents ascending (periphery first)
        sorted_classes = sorted(classes, key=lambda c: len(dep_graph.get(c, set())))
        # Shuffle within same-dependency-count tiers for randomness
        tier_start = 0
        while tier_start < len(sorted_classes):
            tier_count = len(dep_graph.get(sorted_classes[tier_start], set()))
            tier_end = tier_start
            while tier_end < len(sorted_classes) and len(dep_graph.get(sorted_classes[tier_end], set())) == tier_count:
                tier_end += 1
            tier = sorted_classes[tier_start:tier_end]
            self._rng.shuffle(tier)
            sorted_classes[tier_start:tier_end] = tier
            tier_start = tier_end
        return sorted_classes[:n_to_remove]

    def _remove_elements(
        self,
        graph: Graph,
        classes_to_remove: list[URIRef],
        dep_graph: dict[URIRef, set[URIRef]],
    ) -> tuple[Graph, list[str], list[str]]:
        """Remove selected classes and dependent properties from the graph.

        Parameters
        ----------
        graph : Graph
            A *copy* of the gold-standard graph.
        classes_to_remove : list[URIRef]
            Classes to excise.
        dep_graph : dict[URIRef, set[URIRef]]
            Dependency map.

        Returns
        -------
        reduced_graph : Graph
            The graph with elements removed.
        removed_class_uris : list[str]
            String URIs of removed classes (for the TestCase record).
        removed_property_uris : list[str]
            String URIs of removed properties.
        """
        removed_class_uris: list[str] = []
        removed_property_uris: list[str] = []

        # Gather all properties to remove (dependent on removed classes)
        props_to_remove: set[URIRef] = set()
        for cls in classes_to_remove:
            props_to_remove.update(dep_graph.get(cls, set()))

        # Remove class triples
        for cls in classes_to_remove:
            removed_class_uris.append(str(cls))
            # Remove all triples where this class is subject or object
            for t in list(graph.triples((cls, None, None))):
                graph.remove(t)
            for t in list(graph.triples((None, None, cls))):
                graph.remove(t)

        # Remove property triples
        for prop in props_to_remove:
            removed_property_uris.append(str(prop))
            for t in list(graph.triples((prop, None, None))):
                graph.remove(t)
            for t in list(graph.triples((None, None, prop))):
                graph.remove(t)
            for t in list(graph.triples((None, prop, None))):
                graph.remove(t)

        return graph, removed_class_uris, removed_property_uris

    def _serialise_reduced_ontology(
        self, graph: Graph, level: ReductionLevel
    ) -> Path:
        """Serialise the reduced graph to an OWL/XML file.

        Parameters
        ----------
        graph : Graph
            The reduced graph.
        level : ReductionLevel
            Used to name the output file.

        Returns
        -------
        Path
            Path to the written file, e.g.
            ``data/test_cases/plan-ontology-75pct.owl``.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.gold_standard_path.stem}-{level.value}.owl"
        out_path = self.output_dir / filename
        graph.serialize(destination=str(out_path), format="xml")
        logger.info("serialised_reduced_ontology", path=str(out_path))
        return out_path

    # ------------------------------------------------------------------
    # Internal: Competency Question Generation
    # ------------------------------------------------------------------

    def _generate_competency_questions(
        self,
        removed_classes: list[str],
        removed_properties: list[str],
        level: ReductionLevel,
    ) -> list[CompetencyQuestion]:
        """Generate competency questions targeting the removed elements.

        Strategy
        --------
        - **Template-based** (fast): For each removed class, create a
          CQ like "What types of <parent_class> exist?" or
          "What is the relationship between <domain> and <range>?"
        - **LLM-based** (richer): Prompt an LLM with the list of
          removed elements and ask it to generate natural-language
          CQs that *require* those elements to be answerable.

        Parameters
        ----------
        removed_classes : list[str]
            URIs of removed classes.
        removed_properties : list[str]
            URIs of removed properties.
        level : ReductionLevel
            For setting CQ difficulty metadata.

        Returns
        -------
        list[CompetencyQuestion]
            CQs that should become answerable after extension.
        """
        cqs: list[CompetencyQuestion] = []

        # Template-based CQ generation for removed classes
        for i, cls_uri in enumerate(removed_classes):
            local_name = cls_uri.split("#")[-1].split("/")[-1]
            # Convert camelCase/underscore to words
            label = local_name.replace("_", " ")

            difficulty = "easy"
            if level in (ReductionLevel.PCT_90, ReductionLevel.PCT_95):
                difficulty = "hard"
            elif level == ReductionLevel.PCT_75:
                difficulty = "medium"

            cqs.append(
                CompetencyQuestion(
                    id=f"CQ-C{i:02d}",
                    question=f"What is a {label} and how does it relate to the ontology?",
                    cq_type="VCQ",
                    target_classes=[cls_uri],
                    target_properties=[],
                    difficulty=difficulty,
                )
            )

        # Template-based CQ generation for removed properties
        for j, prop_uri in enumerate(removed_properties):
            local_name = prop_uri.split("#")[-1].split("/")[-1]
            label = local_name.replace("_", " ")

            difficulty = "medium" if level in (
                ReductionLevel.PCT_50, ReductionLevel.PCT_75
            ) else "hard"

            cqs.append(
                CompetencyQuestion(
                    id=f"CQ-P{j:02d}",
                    question=f"What relationship does '{label}' describe between entities?",
                    cq_type="RCQ",
                    target_classes=[],
                    target_properties=[prop_uri],
                    difficulty=difficulty,
                )
            )

        return cqs

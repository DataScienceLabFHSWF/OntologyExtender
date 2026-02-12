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
        raise NotImplementedError(
            "TODO: iterate over REDUCTION_LEVELS, call generate_single() for each"
        )

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
        raise NotImplementedError(
            "TODO: implement ontology reduction logic"
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
        raise NotImplementedError(
            "TODO: rdflib.Graph().parse(self.gold_standard_path, format='xml')"
        )

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
        raise NotImplementedError(
            "TODO: graph.subjects(RDF.type, OWL.Class), filter built-ins"
        )

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
        raise NotImplementedError(
            "TODO: combine ObjectProperty + DatatypeProperty subjects"
        )

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
        raise NotImplementedError(
            "TODO: iterate properties, check domain/range, build map"
        )

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
        raise NotImplementedError(
            "TODO: sort by dependency count ascending, take fraction"
        )

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
        raise NotImplementedError(
            "TODO: remove all triples where class/property is subject or object"
        )

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
        raise NotImplementedError(
            "TODO: graph.serialize(destination=..., format='xml')"
        )

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
        raise NotImplementedError(
            "TODO: template + optional LLM generation of CQs"
        )

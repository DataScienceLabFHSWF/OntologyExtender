"""OWL reasoning and logical consistency checking.

This package provides a lightweight, in-process OWL reasoning layer used by
two consumers:

* The **Reasoner agent** (``ontology_hitl.agents.reasoner``) runs it over
  candidate ontology extensions during multi-agent debate to surface logical
  flaws (unsatisfiable classes, disjointness violations, subclass cycles).
* The **OEO benchmark** (``ontology_hitl.benchmarking.oeo_benchmark``) reuses
  the same checker to evaluate reasoner-style competency questions and to
  detect inconsistencies in generated ontologies.

The core uses ``rdflib`` + ``owlrl`` (OWL-RL/RDFS materialisation) plus a set
of structural TBox checks that catch unsatisfiability patterns OWL-RL alone
does not flag without ABox data.
"""

from __future__ import annotations

from ontology_hitl.reasoning.consistency import (
    ConsistencyChecker,
    ConsistencyReport,
    LogicalIssue,
    LogicalIssueKind,
)

__all__ = [
    "ConsistencyChecker",
    "ConsistencyReport",
    "LogicalIssue",
    "LogicalIssueKind",
]

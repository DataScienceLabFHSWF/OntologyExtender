"""Multi-agent ontology development system.

Three specialised agents collaborate through structured debate to build
ontologies following the Noy & McGuinness (2001) methodology:

**OntologyEngineer** — drives the 7-phase Ont-101 process, proposes
    class hierarchies, properties, and constraints.

**DomainExpert** — grounded in domain documents (Qdrant), validates
    proposals against real-world evidence, catches domain errors.

**Critic** — reviews both agents' work, checks consistency, identifies
    gaps, and plays devil's advocate.

The human reviewer (HITL) only intervenes when agents disagree or
when high-stakes decisions arise.
"""

from ontology_hitl.agents.base import (
    AgentRole,
    AgentMessage,
    Debate,
    DebateOutcome,
)
from ontology_hitl.agents.ontology_engineer import OntologyEngineerAgent
from ontology_hitl.agents.domain_expert import DomainExpertAgent
from ontology_hitl.agents.critic import CriticAgent
from ontology_hitl.agents.team import AgentTeam

__all__ = [
    "AgentRole",
    "AgentMessage",
    "Debate",
    "DebateOutcome",
    "OntologyEngineerAgent",
    "DomainExpertAgent",
    "CriticAgent",
    "AgentTeam",
]

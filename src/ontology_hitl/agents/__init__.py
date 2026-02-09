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
    AgentPerformanceMetrics,
    Debate,
    DebateOutcome,
    DebateStrategy,
    DebateVerdict,
)
from ontology_hitl.agents.ontology_engineer import OntologyEngineerAgent
from ontology_hitl.agents.domain_expert import DomainExpertAgent
from ontology_hitl.agents.critic import CriticAgent
from ontology_hitl.agents.team import AgentTeam
from ontology_hitl.agents.debate_strategies import DebateStrategist
from ontology_hitl.agents.moderator import (
    Moderator,
    DriftThresholds,
    GroundingReport,
    DriftReport,
    GROUNDING_CONSTRAINTS,
    DEFAULT_STRATEGY_MAP,
)

__all__ = [
    "AgentRole",
    "AgentMessage",
    "AgentPerformanceMetrics",
    "Debate",
    "DebateOutcome",
    "DebateStrategy",
    "DebateStrategist",
    "DebateVerdict",
    "Moderator",
    "DriftThresholds",
    "GroundingReport",
    "DriftReport",
    "GROUNDING_CONSTRAINTS",
    "DEFAULT_STRATEGY_MAP",
    "OntologyEngineerAgent",
    "DomainExpertAgent",
    "CriticAgent",
    "AgentTeam",
]

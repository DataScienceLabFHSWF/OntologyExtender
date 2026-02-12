"""Base abstractions for the multi-agent ontology system.

Every agent in the system shares the same LLM backend (Ollama) but has
a distinct *role* encoded via its system prompt.  Agents communicate
through ``AgentMessage`` objects within a ``Debate`` — a structured
conversation that produces a ``DebateOutcome``.

The ``Debate`` is the fundamental collaboration primitive:
    1. The proposer (usually OntologyEngineer) initiates with a proposal.
    2. Reviewers (DomainExpert, Critic) respond with assessments.
    3. The proposer may revise based on feedback.
    4. A ``DebateOutcome`` is produced: consensus, revised, or escalated.

Escalated outcomes become ``AgentQuestion`` items for HITL review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

import httpx
import structlog

from ontology_hitl.core.config import Settings
from ontology_hitl.methodology.ontology101 import AgentQuestion, Phase

logger = structlog.get_logger(__name__)


# ── Enums ───────────────────────────────────────────────────────────

class AgentRole(str, Enum):
    """Roles available in the multi-agent system."""

    ONTOLOGY_ENGINEER = "ontology_engineer"
    DOMAIN_EXPERT = "domain_expert"
    CRITIC = "critic"


class DebateStrategy(str, Enum):
    """Different debate strategies inspired by philosophical methods."""

    DIALECTICAL = "dialectical"          # Thesis → Antithesis → Synthesis (Hegel)
    SOCRATIC = "socratic"                # Question-driven inquiry (Plato)
    DELPHI = "delphi"                    # Iterative expert consensus (Dalkey & Helmer)
    ABDUCTIVE = "abductive"              # Inference to best explanation (Peirce)
    CONSENSUS_BUILDING = "consensus"     # Discourse ethics (Habermas)


class DebateVerdict(str, Enum):
    """Possible debate outcomes."""

    CONSENSUS = "consensus"         # all agents agree
    REVISED = "revised"             # proposal was improved through debate
    ESCALATED = "escalated"         # disagreement → needs HITL
    PARTIAL = "partial"             # some issues resolved, others escalated


@dataclass
class AgentPerformanceMetrics:
    """Tracks performance metrics for agents across debates."""

    agent_role: AgentRole
    total_debates: int = 0
    consensus_contributions: int = 0
    revisions_requested: int = 0
    escalations_caused: int = 0
    avg_response_time: float = 0.0
    issues_raised_per_debate: float = 0.0
    approval_rate: float = 0.0
    debate_participation: dict[str, int] = field(default_factory=dict)  # phase -> count

@dataclass
class AgentMessage:
    """A single message from an agent in a debate.

    Messages are typed so the orchestrator knows whether the agent
    is proposing, reviewing, or revising.
    """

    role: AgentRole
    phase: Phase
    message_type: Literal["proposal", "review", "revision", "assessment"]
    content: dict[str, Any]             # structured JSON payload
    reasoning: str = ""                 # chain of thought / rationale
    issues_raised: list[str] = field(default_factory=list)
    approves: bool | None = None        # True=approve, False=reject, None=neutral
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DebateOutcome:
    """The result of a multi-agent debate on a single phase.

    Contains the final proposal (possibly revised), a list of issues
    that were auto-resolved through debate, and any unresolved issues
    that require HITL escalation.
    """

    phase: Phase
    verdict: DebateVerdict
    final_proposal: dict[str, Any]      # the agreed-upon JSON artefact
    messages: list[AgentMessage] = field(default_factory=list)
    resolved_issues: list[str] = field(default_factory=list)
    escalated_questions: list[AgentQuestion] = field(default_factory=list)
    rounds: int = 1


@dataclass
class Debate:
    """A conversation between agents about a single phase.

    Orchestrates the propose → review → revise flow and determines
    when consensus is reached or escalation is needed.
    """

    phase: Phase
    messages: list[AgentMessage] = field(default_factory=list)
    strategy: DebateStrategy = DebateStrategy.CONSENSUS_BUILDING
    max_rounds: int = 2

    def add_message(self, msg: AgentMessage) -> None:
        self.messages.append(msg)

    @property
    def latest_proposal(self) -> dict[str, Any] | None:
        """The most recent proposal or revision."""
        for msg in reversed(self.messages):
            if msg.message_type in ("proposal", "revision"):
                return msg.content
        return None

    @property
    def reviews(self) -> list[AgentMessage]:
        """All review messages."""
        return [m for m in self.messages if m.message_type == "review"]

    @property
    def has_consensus(self) -> bool:
        """True if all reviewers approve the latest proposal."""
        reviews = self.reviews
        if not reviews:
            return False
        # Only check reviews that came after the latest proposal
        latest_prop_idx = max(
            (i for i, m in enumerate(self.messages)
             if m.message_type in ("proposal", "revision")),
            default=-1,
        )
        recent_reviews = [
            m for i, m in enumerate(self.messages)
            if i > latest_prop_idx and m.message_type == "review"
        ]
        return bool(recent_reviews) and all(r.approves for r in recent_reviews)

    @property
    def unresolved_issues(self) -> list[str]:
        """Issues raised by reviewers that weren't addressed in revisions."""
        all_issues: list[str] = []
        for review in self.reviews:
            all_issues.extend(review.issues_raised)
        # Remove issues addressed in revisions
        for msg in self.messages:
            if msg.message_type == "revision" and msg.reasoning:
                all_issues = [
                    i for i in all_issues
                    if i.lower() not in msg.reasoning.lower()
                ]
        return all_issues


# ── Base Agent class ────────────────────────────────────────────────

class BaseAgent:
    """Base class for all agents in the system.

    Each agent has:
    - A ``role`` that determines its perspective
    - A ``system_prompt`` that defines its expertise and priorities
    - Access to the same LLM via the Ollama API

    Subclasses implement ``propose()`` and ``review()`` methods
    that return structured ``AgentMessage`` objects.
    """

    role: AgentRole
    system_prompt: str

    def __init__(
        self,
        settings: Settings | None = None,
        system_prompt: str = "",
    ) -> None:
        self.settings = settings or Settings()
        self.system_prompt = system_prompt
        self._response_cache: dict[str, dict[str, Any]] = {}  # Simple in-memory cache

    def call_llm(
        self,
        user_prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any] | None:
        """Call Ollama chat API and parse JSON from the response.

        Handles qwen3-next thinking mode — extracts content after
        the ``</think>`` tag if present.

        Args:
            user_prompt: The user message.
            system_prompt: Override the default system prompt.
            temperature: LLM temperature (default from settings).
            use_cache: Whether to cache and reuse responses for identical prompts.

        Returns:
            Parsed JSON dict, or None if the call fails.
        """
        sys_prompt = system_prompt or self.system_prompt
        temp = temperature if temperature is not None else self.settings.llm_temperature

        # Create cache key from prompt and parameters
        if use_cache:
            cache_key = f"{hash(sys_prompt)}:{hash(user_prompt)}:{temp}"
            if cache_key in self._response_cache:
                logger.debug("llm_cache_hit", agent=self.role.value, cache_key=cache_key[:16])
                return self._response_cache[cache_key]

        try:
            logger.debug("llm_call_start", agent=self.role.value, timeout=self.settings.llm_timeout_seconds)
            resp = httpx.post(
                f"{self.settings.ollama_url}/api/chat",
                json={
                    "model": self.settings.ollama_model,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": temp,
                        "num_predict": 4096,
                    },
                },
                timeout=self.settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]

            # Strip qwen3-next thinking tags
            if "</think>" in content:
                content = content.split("</think>", 1)[1].strip()

            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                content = content.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in content:
                md_parts = content.split("```")
                if len(md_parts) >= 3:
                    content = md_parts[1]

            # More robust JSON extraction using balanced brackets
            def find_json_objects(text):
                results = []
                # Remove control characters that definitely break JSON
                text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
                
                start_indices = [i for i, char in enumerate(text) if char in '{[']
                for start in start_indices:
                    stack = []
                    for i in range(start, len(text)):
                        char = text[i]
                        if char in '{[':
                            stack.append(text[start] if not stack else char)
                        elif char in '}]':
                            if not stack: break
                            opening = stack.pop()
                            if (opening == '{' and char == '}') or (opening == '[' and char == ']'):
                                if not stack:
                                    candidate = text[start:i+1]
                                    try:
                                        results.append(json.loads(candidate))
                                    except json.JSONDecodeError:
                                        # Handle common trailing comma issue
                                        try:
                                            results.append(json.loads(re.sub(r',(\s*[}\]])', r'\1', candidate)))
                                        except json.JSONDecodeError:
                                            pass
                                    break
                            else:
                                break
                return results

            json_objects = find_json_objects(content)
            if json_objects:
                # Most ontology agents return a single dict or a list. 
                # If we have multiple, the first one is usually the main response.
                result = json_objects[0]
            else:
                # Last resort fallback
                result = json.loads(content)

            # Cache the result
            if use_cache:
                self._response_cache[cache_key] = result
                logger.debug("llm_cache_stored", agent=self.role.value, cache_key=cache_key[:16])

            return result

        except httpx.HTTPError as e:
            logger.warning("llm_call_failed", agent=self.role.value, error=str(e))
            return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("llm_parse_failed",
                          agent=self.role.value,
                          error=str(e),
                          raw_content=content[:500] if 'content' in locals() else "No content received")
            return None

    def call_llm_multi_turn(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> dict[str, Any] | None:
        """Call Ollama with a multi-turn conversation.

        Used for review rounds where agents see previous messages.

        Args:
            messages: List of {role, content} dicts including system.
            temperature: LLM temperature.

        Returns:
            Parsed JSON dict, or None.
        """
        temp = temperature if temperature is not None else self.settings.llm_temperature

        try:
            resp = httpx.post(
                f"{self.settings.ollama_url}/api/chat",
                json={
                    "model": self.settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temp,
                        "num_predict": 4096,
                    },
                },
                timeout=self.settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]

            if "</think>" in content:
                content = content.split("</think>", 1)[1].strip()

            if "```json" in content:
                content = content.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in content:
                content = content.split("```", 1)[1].split("```", 1)[0]

            # Sanitize JSON content - remove control characters that break parsing
            import re
            content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)

            return json.loads(content)

        except httpx.HTTPError as e:
            logger.warning("llm_multi_turn_failed", agent=self.role.value, error=str(e))
            return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("llm_multi_turn_parse_failed", agent=self.role.value, error=str(e))
            return None
    def clear_response_cache(self) -> None:
        """Clear the LLM response cache."""
        cache_size = len(self._response_cache)
        self._response_cache.clear()
        logger.info("llm_cache_cleared", agent=self.role.value, cleared_entries=cache_size)
"""Strategy adapters for OntoURL benchmark evaluation.

Each strategy wraps a different approach to answering OntoURL questions,
from a simple vanilla prompt-to-answer baseline to multi-agent debate.

Strategies
----------
VanillaStrategy             Direct prompt → answer (OntoURL baseline)
ChainOfThoughtStrategy      CoT reasoning before answering
OntologyEngineerStrategy    Role-play as ontology engineer (L1–L5)
MultiTurnStrategy           Multi-turn refinement (L2–L4)
DebateStrategy              Simulated proposer/critic debate (L2–L4)
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog

from .prompts import OntoURLPromptBuilder

logger = structlog.get_logger(__name__)


class OllamaAdapter:
    """Thin wrapper around the Ollama HTTP API for OntoURL inference.

    Replaces OntoURL's vLLM engine with sequential Ollama calls.

    Parameters
    ----------
    model : str
        Ollama model tag.
    ollama_url : str
        Ollama server URL.
    temperature : float
        Sampling temperature (0.0 for deterministic).
    max_tokens : int
        Max tokens per response.
    timeout : float
        Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "llama3.2:3b",
        ollama_url: str = "http://localhost:18135",
        temperature: float = 0.0,
        max_tokens: int = 512,
        timeout: float = 600.0,
    ) -> None:
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        """Single-turn generation via Ollama /api/generate.

        Parameters
        ----------
        prompt : str
            Full prompt text.

        Returns
        -------
        str
            Model's raw response text.
        """
        resp = httpx.post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")

        # Strip qwen3 thinking tags
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()

        return text

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        """Multi-turn generation via Ollama /api/chat.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages [{role, content}, ...].

        Returns
        -------
        str
            Model's raw response text.
        """
        resp = httpx.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        text = resp.json()["message"]["content"]

        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()

        return text


# ── Base strategy ────────────────────────────────────────────────────

class OntoURLStrategy(ABC):
    """Base class for OntoURL benchmark strategies."""

    name: str = "base"

    def __init__(self, llm: OllamaAdapter) -> None:
        self.llm = llm
        self.prompt_builder = OntoURLPromptBuilder()

    @abstractmethod
    def answer(
        self,
        example: dict[str, Any],
        task_type: str,
        split_id: str,
    ) -> str:
        """Generate an answer for a single OntoURL example.

        Parameters
        ----------
        example : dict
            Dataset example with 'question', 'answer', etc.
        task_type : str
            Task type.
        split_id : str
            Split ID.

        Returns
        -------
        str
            Raw model response.
        """
        ...

    def applicable_to(self, task_type: str, split_id: str) -> bool:
        """Check if this strategy is applicable to the given task.

        Override in subclasses to restrict strategies to certain tasks.
        """
        return True


# ── Vanilla (direct prompt → answer) ────────────────────────────────

class VanillaStrategy(OntoURLStrategy):
    """Direct prompt → answer. Reproduces OntoURL's baseline.

    Parameters
    ----------
    llm : OllamaAdapter
        Ollama adapter.
    shot_setting : str
        'zero_shot', 'two_shot', or 'four_shot'.
    few_shot_examples : list[dict] | None
        Pre-loaded few-shot examples.
    """

    name = "vanilla"

    def __init__(
        self,
        llm: OllamaAdapter,
        shot_setting: str = "zero_shot",
        few_shot_examples: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(llm)
        self.shot_setting = shot_setting
        self.few_shot_examples = few_shot_examples
        self.name = f"vanilla_{shot_setting}"

    def answer(
        self,
        example: dict[str, Any],
        task_type: str,
        split_id: str,
    ) -> str:
        prompt = self.prompt_builder.build_prompt(
            split_id=split_id,
            example=example,
            task_type=task_type,
            strategy="vanilla",
            few_shot_examples=self.few_shot_examples,
        )
        return self.llm.generate(prompt)


# ── Chain-of-Thought ─────────────────────────────────────────────────

class ChainOfThoughtStrategy(OntoURLStrategy):
    """CoT: Think step by step before answering."""

    name = "cot"

    def answer(
        self,
        example: dict[str, Any],
        task_type: str,
        split_id: str,
    ) -> str:
        prompt = self.prompt_builder.build_prompt(
            split_id=split_id,
            example=example,
            task_type=task_type,
            strategy="cot",
        )
        return self.llm.generate(prompt)


# ── Ontology Engineer Role ───────────────────────────────────────────

class OntologyEngineerStrategy(OntoURLStrategy):
    """Role-play as ontology engineer. Works on all tasks."""

    name = "engineer"

    def answer(
        self,
        example: dict[str, Any],
        task_type: str,
        split_id: str,
    ) -> str:
        prompt = self.prompt_builder.build_prompt(
            split_id=split_id,
            example=example,
            task_type=task_type,
            strategy="engineer",
        )
        return self.llm.generate(prompt)


# ── Multi-Turn Strategy ─────────────────────────────────────────────

class MultiTurnStrategy(OntoURLStrategy):
    """Multi-turn refinement: analyze → draft → critique → final.

    For Learning tasks L1–L5 (generation/construction/alignment).
    """

    name = "multi_turn"

    def applicable_to(self, task_type: str, split_id: str) -> bool:
        return split_id.startswith("3_")

    def answer(
        self,
        example: dict[str, Any],
        task_type: str,
        split_id: str,
    ) -> str:
        # Turn 1: Analyze
        initial_messages = self.prompt_builder.build_multi_turn_messages(
            split_id=split_id,
            example=example,
            task_type=task_type,
        )
        analysis = self.llm.generate_chat(initial_messages)

        # Turn 2: Generate based on analysis
        if task_type == "open_text":
            gen_instruction = (
                "Based on your analysis, now generate a precise natural "
                "language definition for the class."
            )
        elif task_type == "open_tuple":
            gen_instruction = (
                "Based on your analysis, now generate the alignment tuples "
                "in the form (entity1, entity2). "
                "Output all tuples between <ans> and </ans>."
            )
        else:
            gen_instruction = (
                "Based on your analysis, now generate the triples "
                "in the form (subject, predicate, object). "
                "Output all triples between <ans> and </ans>."
            )

        generation_messages = initial_messages + [
            {"role": "assistant", "content": analysis},
            {"role": "user", "content": gen_instruction},
        ]
        draft = self.llm.generate_chat(generation_messages)

        # Turn 3: Self-critique and refine
        if task_type == "open_text":
            refine_instruction = (
                "Review your definition. Check for:\n"
                "1. Accuracy and completeness\n"
                "2. Proper use of ontology terminology\n"
                "3. Conciseness\n\n"
                "Output the final refined definition."
            )
        elif task_type == "open_tuple":
            refine_instruction = (
                "Review your alignment tuples. Check for:\n"
                "1. Missing alignments\n"
                "2. Incorrect mappings\n"
                "3. Redundant tuples\n\n"
                "Output the corrected final tuples between <ans> and </ans>."
            )
        else:
            refine_instruction = (
                "Review your triples. Check for:\n"
                "1. Missing relationships\n"
                "2. Incorrect taxonomic hierarchies\n"
                "3. Redundant or contradictory triples\n\n"
                "Output the corrected final triples between "
                "<ans> and </ans>."
            )

        refinement_messages = generation_messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": refine_instruction},
        ]
        return self.llm.generate_chat(refinement_messages)


# ── Debate Strategy ─────────────────────────────────────────────────

class DebateStrategy(OntoURLStrategy):
    """Simulated multi-agent debate for Learning tasks.

    Proposer generates → Critic identifies issues →
    Proposer revises. For all Learning tasks (L1–L5).
    """

    name = "debate"

    def applicable_to(self, task_type: str, split_id: str) -> bool:
        return split_id.startswith("3_")

    def answer(
        self,
        example: dict[str, Any],
        task_type: str,
        split_id: str,
    ) -> str:
        debate_config = self.prompt_builder.build_debate_messages(
            split_id=split_id,
            example=example,
            task_type=task_type,
        )

        # Determine task-specific output instruction
        if task_type == "open_text":
            gen_instr = "Generate a precise definition."
            output_fmt = ""
        elif task_type == "open_tuple":
            gen_instr = "Generate alignment tuples in the form (entity1, entity2)."
            output_fmt = " Put all tuples between <ans> and </ans>."
        else:
            gen_instr = "Generate all triples in (subject, predicate, object) form."
            output_fmt = " Put all triples between <ans> and </ans>."

        # Agent 1 (Proposer): Generate initial answer
        proposal = self.llm.generate_chat([
            {"role": "system", "content": debate_config["proposer_system"]},
            {
                "role": "user",
                "content": (
                    f"{debate_config['instruction']}\n\n"
                    f"Question: {debate_config['question']}\n"
                    f"{gen_instr}{output_fmt}"
                ),
            },
        ])

        # Agent 2 (Critic): Review and identify issues
        critique = self.llm.generate_chat([
            {"role": "system", "content": debate_config["critic_system"]},
            {
                "role": "user",
                "content": (
                    f"The following answer was proposed for this ontology task:\n\n"
                    f"Question: {debate_config['question']}\n\n"
                    f"Proposed answer:\n{proposal}\n\n"
                    f"Identify any errors, missing elements, or improvements."
                ),
            },
        ])

        # Agent 1 (Proposer): Revise based on critique
        revised = self.llm.generate_chat([
            {"role": "system", "content": debate_config["proposer_system"]},
            {
                "role": "user",
                "content": (
                    f"You proposed this answer:\n{proposal}\n\n"
                    f"A critic identified these issues:\n{critique}\n\n"
                    f"Original question: {debate_config['question']}\n\n"
                    f"Revise your answer to address the critique. "
                    f"{gen_instr}{output_fmt}"
                ),
            },
        ])

        return revised


# ── Self-Verify Strategy (Agentic: works on ALL tasks) ──────────────

class SelfVerifyStrategy(OntoURLStrategy):
    """Agentic self-verification: answer → verify → revise if needed.

    Mirrors our review agent pattern. Works on ALL task types:
      - MCQ/Bool: answer → check reasoning → confirm or switch
      - Text gen: generate → review quality → refine
      - Triple/Tuple: generate → verify completeness → fix
    """

    name = "self_verify"

    def answer(
        self,
        example: dict[str, Any],
        task_type: str,
        split_id: str,
    ) -> str:
        # Step 1: Get initial answer (using vanilla prompt)
        prompt = self.prompt_builder.build_prompt(
            split_id=split_id,
            example=example,
            task_type=task_type,
            strategy="vanilla",
        )
        initial = self.llm.generate(prompt)

        # Step 2: Verify — ask model to check its own answer
        if task_type in ("mc", "bool"):
            verify_prompt = (
                f"You answered the following ontology question:\n\n"
                f"Question: {example.get('question', '')}\n"
            )
            options = example.get("options", "")
            if options:
                verify_prompt += f"{options}\n"
            verify_prompt += (
                f"\nYour answer: {initial}\n\n"
                f"Double-check your reasoning. Is your answer correct? "
                f"If not, provide the corrected answer. "
            )
            if task_type == "mc":
                verify_prompt += (
                    "Put the final letter between <ans> and </ans>."
                )
            else:
                verify_prompt += "Answer with 'true' or 'false'."
        elif task_type == "open_text":
            verify_prompt = (
                f"You generated the following definition for an ontology class:\n\n"
                f"Context: {example.get('question', '')[:500]}\n\n"
                f"Your definition: {initial}\n\n"
                f"Review for accuracy, completeness, and conciseness. "
                f"Output the final refined definition."
            )
        elif task_type == "open_triple":
            verify_prompt = (
                f"You generated these triples for an ontology task:\n\n"
                f"Question: {example.get('question', '')[:500]}\n\n"
                f"Your triples:\n{initial}\n\n"
                f"Verify: Are any relationships missing? Are the predicates "
                f"correct (subClassOf, etc.)? Are there redundancies?\n"
                f"Output the corrected triples in (subject, predicate, object) "
                f"form between <ans> and </ans>."
            )
        else:  # open_tuple
            verify_prompt = (
                f"You generated these alignment tuples:\n\n"
                f"Question: {example.get('question', '')[:500]}\n\n"
                f"Your tuples:\n{initial}\n\n"
                f"Verify: Are any alignments missing or incorrect?\n"
                f"Output the corrected tuples in (entity1, entity2) form "
                f"between <ans> and </ans>."
            )

        # Step 3: Get verified/revised answer
        return self.llm.generate(verify_prompt)

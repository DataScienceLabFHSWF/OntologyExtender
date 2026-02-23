from __future__ import annotations

import re
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

# Import the real base strategy (fall back only if module path differs)
try:
    from ontology_hitl.benchmarking.ontourl.strategies import OntoURLStrategy
except Exception:
    # Backwards-compatible fallback for environments where the package layout
    # may differ (keeps this module importable during tests).
    class OntoURLStrategy:
        """Base strategy for OntoURL benchmark (fallback)."""
        def __init__(self, model_name: str):
            self.model_name = model_name

        def answer(self, task_prompt: str) -> str:
            # Fallback used only when the real strategy class cannot be imported.
            # Return an empty string rather than raising so that import-time
            # checks and lightweight tests can proceed without errors.
            return ""

class HCOMEStrategy(OntoURLStrategy):
    """
    Simulates the HCOME collaborative ontology engineering methodology
    using a single-call multi-role roleplay (equivalent to `hcome_single`).

    Notes
    -----
    - This implementation runs a single LLM call that role-plays the three
      HCOME roles and extracts the consensus `FINAL ANSWER:` block.
    - For a 3-round LC3-style pipeline (`hcome_3round`) we would implement
      a separate strategy that issues three sequential calls.
    """

    def __init__(self, llm: object) -> None:
        """Ensure `self.llm` and `self.prompt_builder` exist regardless of
        import-time circularities between `strategies.py` and this module.

        This makes the class robust both when it inherits the real
        `OntoURLStrategy` and when a lightweight fallback base class is used.
        """
        # Attempt parent initialization (may accept different signature).
        try:
            super().__init__(llm)
        except Exception:
            # ignore and continue — we'll set required attrs explicitly
            pass

        # Always ensure `self.llm` is set so answer() can call it reliably.
        self.llm = llm

        # Ensure a prompt builder is available (matches OntoURLStrategy)
        if not hasattr(self, "prompt_builder") or self.prompt_builder is None:
            try:
                from ontology_hitl.benchmarking.ontourl.prompts import OntoURLPromptBuilder

                self.prompt_builder = OntoURLPromptBuilder()
            except Exception:
                self.prompt_builder = None

    HCOME_SYSTEM_PROMPT = """Create three instances of yourself playing three different roles in the ontology engineering process
based on the HCOME collaborative ontology engineering methodology.
The three roles are the knowledge engineer, the domain expert and the knowledge worker.
These three roles work together to create an ontology. The Knowledge Engineer is responsible
for the requirements specification, conceptualisation and generation of the ontology. The Domain
Expert is an experienced person and provides the requirements for the
ontology, terminology, definitions of terms, domain specific explanations of terms and his
experience in general. The Knowledge Worker is the user of the ontology
and actively participates in the ontology engineering process. The above roles should express
their deep knowledge during the conversation. Their aim is to play all three roles, simulating
the HCOME methodology. The above mentioned roles will interact with each other, asking and
answering questions until a valid and comprehensive ontology is created, which covers all
the defined requirements.

The goal is to answer the following ontology question/task:
{topic}

Please simulate the discussion between these three roles to reach a conclusion.
Finally, output the final answer clearly labeled as 'FINAL ANSWER:'."""
    def answer(
        self,
        example: dict[str, object],
        task_type: str,
        split_id: str,
    ) -> str:
        """Build HCOME prompt from the example and return the parsed consensus.

        Matches the `OntoURLStrategy.answer()` signature so the runner can call
        HCOME interchangeably with other strategies.
        """
        # Prefer using the shared prompt builder so behavior aligns with other strategies
        prompt = getattr(self, "prompt_builder", None)
        if prompt is not None:
            full_prompt = self.prompt_builder.build_prompt(
                split_id=split_id,
                example=example,
                task_type=task_type,
                strategy="hcome",
            )
        else:
            full_prompt = self.HCOME_SYSTEM_PROMPT.format(topic=example.get("question", ""))

        # Use the shared wrapper when available so per-strategy timeouts
        # are respected; fall back to direct adapter or placeholder.
        if hasattr(self, "_generate"):
            resp = self._generate(full_prompt)
        elif hasattr(self, "llm") and getattr(self, "llm") is not None:
            resp = self.llm.generate(full_prompt)
        else:
            resp = self.call_llm(full_prompt)

        return self._parse_consensus(resp)

    def applicable_to(self, task_type: str, split_id: str) -> bool:
        """Allow all task types for smoke tests; can be restricted later."""
        return True

    def call_llm(self, prompt: str) -> str:
        """Fallback LLM call for environments without `self.llm`.

        Prefer `self.llm.generate()` when the strategy is constructed by the
        framework (the runner supplies an OllamaAdapter).
        """
        if hasattr(self, "llm") and getattr(self, "llm") is not None:
            try:
                return self.llm.generate(prompt)
            except Exception:
                return ""

        # Backward-compatible placeholder for unit tests / offline import
        return "Simulation placeholder"

    def _parse_consensus(self, dialogue: str) -> str:
        """
        Extracts the final consensus answer from the multi-role dialogue.
        Looks for 'FINAL ANSWER:' marker.
        """
        match = re.search(r"FINAL ANSWER:\s*(.*)", dialogue, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Fallback: return the last part of the dialogue if no marker found
        lines = dialogue.strip().split('\n')
        return lines[-1] if lines else ""


class HCOME3RoundStrategy(HCOMEStrategy):
    """Reproduce the LC3/LLM4ACOE 3-round HCOME pipeline (hcome_3round).

    Rounds:
      1) Generate initial answer from context
      2) Refine checking against OWL/axioms (structural check)
      3) ReAct-style final improvement + consensus
    """

    name = "hcome_3round"
    strategy_timeout = 180.0

    def answer(self, example: dict[str, object], task_type: str, split_id: str) -> str:
        question = example.get("question", "")

        # Round 1: initial generation (roleplay simplified)
        r1_prompt = (
            f"[Round 1 — Generate]\n{self.HCOME_SYSTEM_PROMPT}\n\nTask: {question}\n\n"
            "Produce an initial candidate answer."
        )
        r1 = self._generate(r1_prompt) if hasattr(self, "_generate") else self.llm.generate(r1_prompt)

        # Round 2: structural/OWL refinement (simulate validator)
        r2_prompt = (
            f"[Round 2 — Refine]\nGiven the initial candidate:\n{r1}\n\n"
            "Check against ontology axioms and correct errors or missing triples."
        )
        r2 = self._generate(r2_prompt) if hasattr(self, "_generate") else self.llm.generate(r2_prompt)

        # Round 3: final ReAct-style consolidation and role consensus
        r3_prompt = (
            f"[Round 3 — Consolidate]\nInitial: {r1}\nRefinements: {r2}\n\n"
            "As the Knowledge Engineer, Domain Expert and Knowledge Worker, produce a FINAL ANSWER:."
        )
        r3 = self._generate(r3_prompt) if hasattr(self, "_generate") else self.llm.generate(r3_prompt)

        return self._parse_consensus(r3)

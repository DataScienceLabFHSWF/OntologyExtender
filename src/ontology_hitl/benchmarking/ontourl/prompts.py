"""Prompt templates for OntoURL benchmark tasks.

Replicates OntoURL's exact prompt formats for fair comparison,
plus enhanced variants for our agentic strategies.

Reference: https://github.com/LastDance500/OntoURL/tree/main/inference/prompt
"""

from __future__ import annotations

from typing import Any


# ── Vanilla prompt instructions per task type ────────────────────────

# These match OntoURL's official zero-shot prompts exactly.
_VANILLA_INSTRUCTIONS: dict[str, str] = {
    # Understanding: MCQ (1_1 .. 1_5)
    "1_1": (
        "Given a multiple-choice question with options, select the one correct "
        "definition and put the letter between <ans> and </ans>."
    ),
    "1_2": (
        "Given a multiple-choice question with options, select the one correct "
        "relationship and put the letter between <ans> and </ans>."
    ),
    "1_3": (
        "Given a multiple-choice question with options, select the one correct "
        "property domain/range and put the letter between <ans> and </ans>."
    ),
    "1_4": (
        "Given a multiple-choice question with options, select the one correct "
        "class for the instance and put the letter between <ans> and </ans>."
    ),
    "1_5": (
        "Given a multiple-choice question with options, select the one correct "
        "definition and put the letter between <ans> and </ans>."
    ),
    # Reasoning: MCQ (2_1 .. 2_4)
    "2_1": (
        "Given a multiple-choice question about ontological relationships, "
        "select the correct answer and put the letter between <ans> and </ans>."
    ),
    "2_2": (
        "Given a multiple-choice question about ontological constraints, "
        "select the correct answer and put the letter between <ans> and </ans>."
    ),
    "2_3": (
        "Given a multiple-choice question about instance classification, "
        "select the correct answer and put the letter between <ans> and </ans>."
    ),
    "2_4": (
        "Given a multiple-choice question about SWRL-based reasoning, "
        "select the correct answer and put the letter between <ans> and </ans>."
    ),
    # Reasoning: True/False (2_5)
    "2_5": (
        "Given a true/false question about description logic, "
        "answer with 'true' or 'false'."
    ),
    # Learning: Text generation (3_1)
    "3_1": (
        "Generate a precise natural language definition for the given ontology "
        "class based on the ontology context provided."
    ),
    # Learning: Triple generation (3_2)
    "3_2": (
        "Construct the ontology's structure and output the triple in the form "
        "(subject, predicate, object). Put all triples in <ans> and </ans> "
        "and separate triples by space."
    ),
    # Learning: Property construction (3_3)
    "3_3": (
        "Construct the ontology's property structure and output the triple in "
        "the form (subject, predicate, object). Put all triples in <ans> and "
        "</ans> and separate triples by space."
    ),
    # Learning: Constraint construction (3_4)
    "3_4": (
        "Construct the ontology's structure (constraint) and output the triple "
        "in the form (subject, predicate, object). Put all triples in <ans> "
        "and </ans> and separate triples by space."
    ),
    # Learning: Ontology alignment (3_5)
    "3_5": (
        "Your task is to perform ontology alignment. Please only output the "
        "tuple in the form (entity1, entity2). Put all triples in <ans> and "
        "</ans> and separate triples by space."
    ),
}

# CoT (Chain-of-Thought) variants — prepend reasoning instruction
_COT_PREFIX: dict[str, str] = {
    "mc": "Think step by step before selecting the answer.\n\n",
    "bool": "Think step by step before answering true or false.\n\n",
    "open_text": "Think step by step, then generate the definition.\n\n",
    "open_triple": (
        "Think step by step about the ontology structure, "
        "then generate the triples.\n\n"
    ),
    "open_tuple": (
        "Think step by step about the relationship between the two ontologies, "
        "then generate the alignment tuples.\n\n"
    ),
}

# Enhanced ontology-engineer system prompt (for L1–L5)
_ENGINEER_SYSTEM = (
    "You are an expert ontology engineer with deep knowledge of OWL, RDFS, "
    "and formal ontology design patterns. You follow the Noy & McGuinness "
    "Ontology 101 methodology. When constructing ontological structures, "
    "you consider:\n"
    "1. Taxonomic correctness (proper is-a relationships)\n"
    "2. Property domain/range constraints\n"
    "3. Disjointness and completeness axioms\n"
    "4. Naming conventions and ontology design patterns\n\n"
    "Apply these principles carefully to the task below.\n\n"
)


class OntoURLPromptBuilder:
    """Build prompts for OntoURL benchmark tasks.

    Supports multiple prompt variants:
      - ``vanilla_zero``: OntoURL's exact zero-shot prompt
      - ``vanilla_few``: OntoURL's few-shot (with examples)
      - ``cot``: Chain-of-thought reasoning prefix
      - ``engineer``: Ontology engineering role prompt (L1–L5 only)
    """

    def build_prompt(
        self,
        split_id: str,
        example: dict[str, Any],
        task_type: str,
        strategy: str = "vanilla_zero",
        few_shot_examples: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build a prompt for a single OntoURL example.

        Parameters
        ----------
        split_id : str
            Split ID (e.g. '3_2').
        example : dict
            One dataset example with 'question', 'answer', optionally 'options'.
        task_type : str
            One of 'mc', 'bool', 'open_text', 'open_triple', 'open_tuple'.
        strategy : str
            Prompt strategy variant.
        few_shot_examples : list[dict] | None
            Examples for few-shot prompting.

        Returns
        -------
        str
            The formatted prompt ready to send to the LLM.
        """
        instruction = _VANILLA_INSTRUCTIONS.get(split_id, "")

        # Build question block
        question_block = self._format_question(example, split_id, task_type)

        # Assemble few-shot examples if provided
        examples_text = ""
        if few_shot_examples:
            examples_text = "Here are some examples.\n\n"
            for ex in few_shot_examples:
                ex_q = self._format_question(ex, split_id, task_type)
                ex_a = ex.get("answer", "").strip()
                examples_text += f"Question: {ex_q}\nAnswer: {ex_a}\n\n"

        # Strategy-specific modifications
        prefix = ""
        if strategy == "cot":
            prefix = _COT_PREFIX.get(task_type, "")
        elif strategy == "engineer":
            prefix = _ENGINEER_SYSTEM

        # Final assembly
        parts = []
        if prefix:
            parts.append(prefix)
        if instruction:
            parts.append(instruction)
        if examples_text:
            parts.append(examples_text)
        parts.append(f"Question: {question_block}\nAnswer:")

        return "\n\n".join(parts)

    def build_multi_turn_messages(
        self,
        split_id: str,
        example: dict[str, Any],
        task_type: str,
    ) -> list[dict[str, str]]:
        """Build multi-turn messages for the multi-turn strategy (L1–L5).

        Turn 1: Analyze the ontology structure.
        Turn 2+: Generate and refine answer.

        Parameters
        ----------
        split_id : str
            Split ID (e.g. '3_2').
        example : dict
            Dataset example.
        task_type : str
            Task type.

        Returns
        -------
        list[dict]
            List of {role, content} dicts for multi-turn conversation.
        """
        question_block = self._format_question(example, split_id, task_type)

        if task_type == "open_text":
            analyze_prompt = (
                f"Analyze this ontology context and identify the key "
                f"characteristics of the class to be defined:\n\n"
                f"{question_block}\n\n"
                f"List the key characteristics and relationships."
            )
        elif task_type == "open_tuple":
            analyze_prompt = (
                f"Analyze these two ontologies and identify potential "
                f"alignments between their entities:\n\n"
                f"{question_block}\n\n"
                f"List the structural similarities and possible mappings."
            )
        else:
            analyze_prompt = (
                f"Analyze this ontology structure and identify the key "
                f"taxonomic relationships, properties, or constraints:\n\n"
                f"{question_block}\n\n"
                f"List the key structural observations."
            )

        return [
            {
                "role": "system",
                "content": (
                    "You are an expert ontology engineer. Follow the "
                    "Noy & McGuinness Ontology 101 methodology. "
                    "Analyze the ontology structure step by step before "
                    "generating any output."
                ),
            },
            {
                "role": "user",
                "content": analyze_prompt,
            },
        ]

    def build_debate_messages(
        self,
        split_id: str,
        example: dict[str, Any],
        task_type: str,
    ) -> dict[str, list[dict[str, str]]]:
        """Build debate messages for the debate strategy (L1–L5).

        Returns separate system prompts for proposer and critic roles.

        Returns
        -------
        dict
            Keys 'proposer_system', 'critic_system', 'question', 'instruction'.
        """
        question_block = self._format_question(example, split_id, task_type)
        instruction = _VANILLA_INSTRUCTIONS.get(split_id, "")

        return {
            "proposer_system": (
                "You are an ontology engineer proposing ontological structures. "
                "Generate answers that are taxonomically correct and follow "
                "ontology design patterns. Be precise and comprehensive."
            ),
            "critic_system": (
                "You are an ontology critic reviewing proposed answers. "
                "Identify errors in definitions, taxonomic relationships, missing "
                "properties, incorrect constraints, and naming issues. "
                "Be specific about what needs to change."
            ),
            "instruction": instruction,
            "question": question_block,
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _format_question(
        self,
        example: dict[str, Any],
        split_id: str,
        task_type: str,
    ) -> str:
        """Format the question block from an example.

        For MCQ tasks, appends option text. For generation tasks,
        just returns the question.
        """
        question = example.get("question", "").strip()

        if task_type in ("mc", "bool"):
            options = example.get("options", "")
            if isinstance(options, str) and options.strip():
                # Clean up double newlines
                options = options.strip().replace("\n\n", "\n")
                question = f"{question}\n{options}"

        return question

"""OntoURL benchmark integration.

Zhang et al. (2025) "OntoURL: A Benchmark for Evaluating LLMs on
Symbolic Ontological Understanding, Reasoning and Learning"
https://arxiv.org/abs/2505.11031

Modules
-------
loader      Dataset loading from HuggingFace
prompts     Prompt templates per task (zero/few-shot)
evaluator   Metric computation (Accuracy, ROUGE-L, Triple-F1, Tuple-F1)
strategies  Strategy adapters (vanilla, agentic, multi-turn)
reporter    Results aggregation, comparison tables, charts
"""

from .loader import OntoURLLoader, SPLIT_TASK_MAP
from .evaluator import OntoURLEvaluator
from .prompts import OntoURLPromptBuilder
from .strategies import (
    OntoURLStrategy,
    VanillaStrategy,
    ChainOfThoughtStrategy,
    OntologyEngineerStrategy,
    MultiTurnStrategy,
    DebateStrategy,
    SelfVerifyStrategy,
)
from .reporter import OntoURLReporter

__all__ = [
    "OntoURLLoader",
    "OntoURLEvaluator",
    "OntoURLPromptBuilder",
    "OntoURLReporter",
    "OntoURLStrategy",
    "VanillaStrategy",
    "ChainOfThoughtStrategy",
    "OntologyEngineerStrategy",
    "MultiTurnStrategy",
    "DebateStrategy",
    "SelfVerifyStrategy",
    "SPLIT_TASK_MAP",
]

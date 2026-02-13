"""OntoURL dataset loader.

Downloads and caches the OntoURL benchmark dataset from HuggingFace,
providing access to all 15 task splits across three capability levels.

Dataset: https://huggingface.co/datasets/XiaoZhang98/OntoURL
Paper:   https://arxiv.org/abs/2505.11031
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from ontology_hitl.benchmarking.models import OntoURLTask, OntoURLCapability

logger = structlog.get_logger(__name__)


# ── Split → (task_type, OntoURLTask, OntoURLCapability) mapping ─────

SPLIT_TASK_MAP: dict[str, tuple[str, OntoURLTask, OntoURLCapability]] = {
    "1_1": ("mc", OntoURLTask.U1_CLASS_DEFINITION, OntoURLCapability.UNDERSTANDING),
    "1_2": ("mc", OntoURLTask.U2_CLASS_RELATION, OntoURLCapability.UNDERSTANDING),
    "1_3": ("mc", OntoURLTask.U3_PROPERTY_DOMAIN, OntoURLCapability.UNDERSTANDING),
    "1_4": ("mc", OntoURLTask.U4_INSTANCE_CLASS, OntoURLCapability.UNDERSTANDING),
    "1_5": ("mc", OntoURLTask.U5_INSTANCE_DEFINITION, OntoURLCapability.UNDERSTANDING),
    "2_1": ("mc", OntoURLTask.R1_INFERRED_RELATION, OntoURLCapability.REASONING),
    "2_2": ("mc", OntoURLTask.R2_CONSTRAINT, OntoURLCapability.REASONING),
    "2_3": ("mc", OntoURLTask.R3_INSTANCE_CLASS_INFERRED, OntoURLCapability.REASONING),
    "2_4": ("mc", OntoURLTask.R4_SWRL_BASED, OntoURLCapability.REASONING),
    "2_5": ("bool", OntoURLTask.R5_DESCRIPTION_LOGIC, OntoURLCapability.REASONING),
    "3_1": ("open_text", OntoURLTask.L1_CLASS_DEF_GENERATION, OntoURLCapability.LEARNING),
    "3_2": ("open_triple", OntoURLTask.L2_HIERARCHY_CONSTRUCTION, OntoURLCapability.LEARNING),
    "3_3": ("open_triple", OntoURLTask.L3_PROPERTY_CONSTRUCTION, OntoURLCapability.LEARNING),
    "3_4": ("open_triple", OntoURLTask.L4_CONSTRAINT_CONSTRUCTION, OntoURLCapability.LEARNING),
    "3_5": ("open_tuple", OntoURLTask.L5_ONTOLOGY_ALIGNMENT, OntoURLCapability.LEARNING),
}

# Friendly task-ID mapping (e.g. "U1" → "1_1")
TASK_ID_TO_SPLIT: dict[str, str] = {
    "U1": "1_1", "U2": "1_2", "U3": "1_3", "U4": "1_4", "U5": "1_5",
    "R1": "2_1", "R2": "2_2", "R3": "2_3", "R4": "2_4", "R5": "2_5",
    "L1": "3_1", "L2": "3_2", "L3": "3_3", "L4": "3_4", "L5": "3_5",
}


class OntoURLLoader:
    """Load and cache the OntoURL benchmark dataset from HuggingFace.

    Parameters
    ----------
    cache_dir : Path
        Local directory for caching the downloaded dataset.
    """

    def __init__(self, cache_dir: Path | str = "data/benchmark_datasets/ontourl") -> None:
        self.cache_dir = Path(cache_dir)
        self._dataset: Any = None

    def load(self) -> Any:
        """Load the full OntoURL dataset (all 15 splits) from HuggingFace.

        Returns
        -------
        datasets.DatasetDict
            The loaded dataset with one split per task.
        """
        from datasets import load_dataset

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("loading_ontourl_dataset", source="XiaoZhang98/OntoURL")

        self._dataset = load_dataset(
            "XiaoZhang98/OntoURL",
            cache_dir=str(self.cache_dir),
        )
        logger.info(
            "ontourl_dataset_loaded",
            splits=list(self._dataset.keys()),
            total_examples=sum(len(s) for s in self._dataset.values()),
        )
        return self._dataset

    def get_split(self, split_id: str) -> Any:
        """Get a specific split by ID (e.g. '3_2' for L2 hierarchy construction).

        Parameters
        ----------
        split_id : str
            One of: 1_1..1_5, 2_1..2_5, 3_1..3_5.

        Returns
        -------
        datasets.Dataset
            The requested split.
        """
        if self._dataset is None:
            self.load()

        # HuggingFace may name splits with prefixes like "bench_3_2"
        for key in self._dataset.keys():
            if split_id in key:
                return self._dataset[key]

        raise KeyError(
            f"Split '{split_id}' not found. "
            f"Available: {list(self._dataset.keys())}"
        )

    def get_task_examples(
        self,
        task_id: str,
        max_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get examples for a task by friendly ID (e.g. 'L2', 'U1').

        Parameters
        ----------
        task_id : str
            Friendly task ID like 'U1', 'R3', 'L2'.
        max_n : int | None
            Max examples to return. ``None`` = all.

        Returns
        -------
        list[dict]
            List of example dicts with 'question', 'answer', etc.
        """
        split_id = TASK_ID_TO_SPLIT.get(task_id.upper())
        if split_id is None:
            raise KeyError(f"Unknown task ID '{task_id}'. Use one of: {list(TASK_ID_TO_SPLIT.keys())}")

        split = self.get_split(split_id)
        examples = [dict(ex) for ex in split]

        if max_n is not None:
            examples = examples[:max_n]
        return examples

    def get_task_type(self, split_id: str) -> str:
        """Return the task type for a split.

        Returns one of: 'mc', 'bool', 'open_text', 'open_triple', 'open_tuple'.
        """
        if split_id not in SPLIT_TASK_MAP:
            raise KeyError(f"Unknown split '{split_id}'")
        return SPLIT_TASK_MAP[split_id][0]

    def list_splits(self) -> list[str]:
        """List all available split IDs."""
        return list(SPLIT_TASK_MAP.keys())

    def summary(self) -> dict[str, Any]:
        """Get a summary of the loaded dataset.

        Returns
        -------
        dict
            Summary including split names, sizes, and task types.
        """
        if self._dataset is None:
            self.load()

        info: dict[str, Any] = {"splits": {}}
        for split_id, (task_type, task_enum, cap) in SPLIT_TASK_MAP.items():
            try:
                split = self.get_split(split_id)
                size = len(split)
            except KeyError:
                size = 0
            info["splits"][split_id] = {
                "task": task_enum.value,
                "capability": cap.value,
                "type": task_type,
                "size": size,
            }
        info["total"] = sum(s["size"] for s in info["splits"].values())
        return info

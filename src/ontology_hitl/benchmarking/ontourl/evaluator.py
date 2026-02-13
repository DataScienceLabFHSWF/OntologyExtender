"""OntoURL evaluation metrics.

Implements the exact metrics used by OntoURL (Zhang et al., 2025):
  - Accuracy (MCQ and True/False tasks)
  - ROUGE-L F-measure (L1 text generation)
  - Triple-F1 order-sensitive (L2, L3, L4)
  - Tuple-F1 order-insensitive (L5 alignment)

Reference implementation:
  https://github.com/LastDance500/OntoURL/blob/main/inference/infer_script.py
"""

from __future__ import annotations

import ast
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class OntoURLEvaluator:
    """Compute OntoURL benchmark metrics.

    Replicates OntoURL's evaluation logic to ensure fair, reproducible
    comparison against their published results.
    """

    # ── High-level evaluation entry point ────────────────────────────

    def evaluate_split(
        self,
        predictions: list[str],
        references: list[str],
        task_type: str,
    ) -> dict[str, float]:
        """Compute task-appropriate metrics for a split.

        Parameters
        ----------
        predictions : list[str]
            Raw model outputs (one per example).
        references : list[str]
            Ground-truth answers.
        task_type : str
            One of 'mc', 'bool', 'open_text', 'open_triple', 'open_tuple'.

        Returns
        -------
        dict[str, float]
            Metric name → value.
        """
        if task_type in ("mc", "bool"):
            return self._evaluate_classification(predictions, references, task_type)
        elif task_type == "open_text":
            return self._evaluate_text(predictions, references)
        elif task_type == "open_triple":
            return self._evaluate_open_triple(predictions, references)
        elif task_type == "open_tuple":
            return self._evaluate_open_tuple(predictions, references)
        else:
            raise ValueError(f"Unknown task_type: {task_type}")

    # ── MCQ / Bool ───────────────────────────────────────────────────

    def _evaluate_classification(
        self,
        predictions: list[str],
        references: list[str],
        task_type: str,
    ) -> dict[str, float]:
        """Accuracy for MCQ and True/False tasks."""
        correct = 0
        total = len(predictions)

        for pred_raw, ref in zip(predictions, references):
            pred = self.extract_prediction(pred_raw, task_type)
            ref_clean = ref.strip().upper() if task_type == "mc" else ref.strip().lower()
            if pred == ref_clean:
                correct += 1

        acc = correct / total if total > 0 else 0.0
        return {"accuracy": acc, "correct": correct, "total": total}

    # ── ROUGE-L for text generation (L1) ─────────────────────────────

    def _evaluate_text(
        self,
        predictions: list[str],
        references: list[str],
    ) -> dict[str, float]:
        """ROUGE-L, ROUGE-1, ROUGE-2, and BLEU for open-text tasks."""
        from rouge_score import rouge_scorer

        scorer = rouge_scorer.RougeScorer(
            ["rouge1", "rouge2", "rougeL"], use_stemmer=True
        )

        rouge1_scores: list[float] = []
        rouge2_scores: list[float] = []
        rougel_scores: list[float] = []
        bleu_scores: list[float] = []

        for pred_raw, ref in zip(predictions, references):
            pred = pred_raw.strip()
            ref_clean = ref.strip()

            # ROUGE
            scores = scorer.score(ref_clean, pred)
            rouge1_scores.append(scores["rouge1"].fmeasure)
            rouge2_scores.append(scores["rouge2"].fmeasure)
            rougel_scores.append(scores["rougeL"].fmeasure)

            # BLEU (optional, but included for completeness)
            try:
                from nltk.tokenize import word_tokenize
                from nltk.translate.bleu_score import sentence_bleu

                pred_tokens = word_tokenize(pred.lower())
                ref_tokens = word_tokenize(ref_clean.lower())
                bleu = sentence_bleu(
                    [ref_tokens], pred_tokens,
                    weights=(0.25, 0.25, 0.25, 0.25),
                )
                bleu_scores.append(bleu)
            except Exception:
                bleu_scores.append(0.0)

        n = len(predictions) or 1
        return {
            "rouge_l": sum(rougel_scores) / n,
            "rouge_1": sum(rouge1_scores) / n,
            "rouge_2": sum(rouge2_scores) / n,
            "bleu": sum(bleu_scores) / n,
        }

    # ── Triple-F1 order-sensitive (L2, L3, L4) ──────────────────────

    def _evaluate_open_triple(
        self,
        predictions: list[str],
        references: list[str],
    ) -> dict[str, float]:
        """Order-sensitive Triple-F1 matching OntoURL's implementation.

        Matches only count at the same position index.
        """
        tp = fp = fn = 0

        for pred_raw, ref_raw in zip(predictions, references):
            pred_tuples = self.extract_prediction(pred_raw, "open_triple")
            ref_tuples = self.extract_prediction(ref_raw, "open_triple")

            matches = sum(
                1
                for i, tup in enumerate(pred_tuples)
                if i < len(ref_tuples) and tup == ref_tuples[i]
            )
            tp += matches
            fp += max(0, len(pred_tuples) - matches)
            fn += max(0, len(ref_tuples) - matches)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        return {"precision": prec, "recall": rec, "triple_f1": f1}

    # ── Tuple-F1 order-insensitive (L5) ─────────────────────────────

    def _evaluate_open_tuple(
        self,
        predictions: list[str],
        references: list[str],
    ) -> dict[str, float]:
        """Order-insensitive Tuple-F1 for ontology alignment (L5).

        Uses set-based matching — order doesn't matter.
        """
        tp = fp = fn = 0

        for pred_raw, ref_raw in zip(predictions, references):
            pred_tuples = self.extract_prediction(pred_raw, "open_tuple")
            ref_tuples = self.extract_prediction(ref_raw, "open_tuple")

            pred_set = set(tuple(t) for t in pred_tuples)
            ref_set = set(tuple(t) for t in ref_tuples)

            matches = len(pred_set & ref_set)
            tp += matches
            fp += len(pred_set) - matches
            fn += len(ref_set) - matches

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        return {"precision": prec, "recall": rec, "tuple_f1": f1}

    # ── Prediction extraction ───────────────────────────────────────

    def extract_prediction(
        self, raw: str, task_type: str
    ) -> Any:
        """Parse model output to structured prediction.

        Parameters
        ----------
        raw : str
            Raw model output text.
        task_type : str
            One of 'mc', 'bool', 'open_text', 'open_triple', 'open_tuple'.

        Returns
        -------
        str | list[tuple]
            Parsed prediction appropriate for the task type.
        """
        raw = raw.strip()

        # Remove <think>...</think> blocks (qwen3 thinking mode)
        if "</think>" in raw:
            raw = raw.split("</think>", 1)[1].strip()

        if task_type == "mc":
            # Extract letter from <ans>X</ans> or standalone letter
            m = re.search(r"<ans>\s*([A-D])\s*</ans>", raw, re.IGNORECASE)
            if m:
                return m.group(1).upper()
            m = re.search(r"\b([A-D])\b", raw, re.IGNORECASE)
            return m.group(1).upper() if m else raw[:1].upper()

        elif task_type == "bool":
            m = re.search(r"\b(true|false)\b", raw, re.IGNORECASE)
            return m.group(1).lower() if m else raw.lower().strip()

        elif task_type == "open_text":
            return raw

        elif task_type in ("open_triple", "open_tuple"):
            # Try extracting from <ans>...</ans> tags first
            ans_match = re.search(r"<ans>(.*?)</ans>", raw, re.DOTALL)
            text = ans_match.group(1).strip() if ans_match else raw

            parsed = self._parse_tuples_ast(text)
            if not parsed:
                parsed = self._parse_tuples_regex(text)

            if task_type == "open_triple":
                return [t for t in parsed if len(t) == 3]
            return parsed

        return raw

    # ── Tuple parsing helpers (matching OntoURL's implementation) ────

    def _parse_tuples_ast(self, raw: str) -> list[tuple]:
        """Try parsing tuples using Python's AST (robust for well-formed output)."""
        tuples: list[tuple] = []
        try:
            # Try wrapping in list for AST parsing
            parsed = ast.literal_eval(f"[{raw}]")
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, tuple):
                        tuples.append(tuple(str(x).strip() for x in item))
        except (ValueError, SyntaxError):
            pass
        return tuples

    def _parse_tuples_regex(self, raw: str) -> list[tuple]:
        """Fallback regex-based tuple parsing."""
        tuples: list[tuple] = []

        # Match (a, b, c) or (a, b) patterns
        pattern = r"\(([^()]+)\)"
        for match in re.finditer(pattern, raw):
            parts = [p.strip().strip("'\"") for p in match.group(1).split(",")]
            if len(parts) >= 2:
                tuples.append(tuple(parts))

        return tuples

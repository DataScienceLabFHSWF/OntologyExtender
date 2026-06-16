"""Loader for Open Energy Ontology (OEO) competency-question test files.

OEO ships its competency questions as OWL Manchester syntax (``.omn``) files
under ``tests/competency_questions/`` (github.com/OpenEnergyPlatform/ontology).
Each file encodes a *reasoner entailment test*: it declares a small class
expression and an ``EquivalentClasses( … , owl:Nothing )`` axiom asserting that
the expression must be unsatisfiable, together with a natural-language question
in a leading ``#`` comment, e.g.::

    # Do all hot things carry energy?
    Class: owl:Nothing
    EquivalentClasses: ((obo:RO_0000053 some OEO_00000207) and not
        (obo:RO_0000091 some OEO_00000151)), owl:Nothing

This module parses those files into a structured
:class:`OEOCompetencyQuestion` so they can drive the OEO benchmark. The CQ
category is taken from the containing sub-directory (``implementing``,
``physical``, ``model/soundness``, ``social/completeness``, ``deprecated``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# A question comment is a `#` line whose text reads like a question.
_QUESTION_RE = re.compile(r"^\s*#\s*(?P<text>.+?)\s*$")
_NOTHING_RE = re.compile(r"owl:Nothing", re.IGNORECASE)
_EQUIV_RE = re.compile(r"EquivalentClasses\s*:", re.IGNORECASE)
_SUBCLASS_AXIOM_RE = re.compile(r"\bSubClassOf\b", re.IGNORECASE)


@dataclass
class OEOCompetencyQuestion:
    """A single OEO competency-question entailment test."""

    id: str
    question: str
    category: str
    file_path: str
    manchester: str
    expected_unsatisfiable: bool = True
    referenced_terms: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (for JSON reports)."""
        return {
            "id": self.id,
            "question": self.question,
            "category": self.category,
            "file_path": self.file_path,
            "expected_unsatisfiable": self.expected_unsatisfiable,
            "referenced_terms": list(self.referenced_terms),
            "notes": self.notes,
        }


def parse_omn(path: str | Path) -> OEOCompetencyQuestion:
    """Parse a single ``.omn`` competency-question file.

    Parameters
    ----------
    path:
        Path to the ``.omn`` file.

    Returns
    -------
    OEOCompetencyQuestion
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    question, notes = _extract_question_and_notes(text)
    referenced = _extract_terms(text)
    expected_unsat = bool(_EQUIV_RE.search(text) and _NOTHING_RE.search(text))

    return OEOCompetencyQuestion(
        id=path.stem,
        question=question or path.stem.replace("_", " "),
        category=_category_from_path(path),
        file_path=str(path),
        manchester=text,
        expected_unsatisfiable=expected_unsat,
        referenced_terms=referenced,
        notes=notes,
    )


def load_cq_directory(
    cq_dir: str | Path,
    categories: list[str] | None = None,
) -> list[OEOCompetencyQuestion]:
    """Recursively load all ``.omn`` CQ files under ``cq_dir``.

    Parameters
    ----------
    cq_dir:
        Root competency-questions directory.
    categories:
        Optional whitelist of category names (sub-directories) to include.
        When ``None`` all categories are loaded.

    Returns
    -------
    list[OEOCompetencyQuestion]
        Sorted by ``id``.
    """
    cq_dir = Path(cq_dir)
    if not cq_dir.exists():
        raise FileNotFoundError(f"OEO CQ directory not found: {cq_dir}")

    cqs: list[OEOCompetencyQuestion] = []
    for omn in sorted(cq_dir.rglob("*.omn")):
        try:
            cq = parse_omn(omn)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("oeo_cq_parse_failed", file=str(omn), error=str(e))
            continue
        if categories and cq.category not in categories:
            continue
        cqs.append(cq)

    logger.info("oeo_cqs_loaded", count=len(cqs), dir=str(cq_dir))
    return cqs


# ── Internal helpers ────────────────────────────────────────────────


def _extract_question_and_notes(text: str) -> tuple[str, str]:
    """Pull the natural-language question and any explanatory note.

    The question is the first ``#`` comment that ends with ``?`` (or, failing
    that, the first comment after the ``Ontology:`` line). Remaining comment
    lines are collected as notes.
    """
    comments: list[str] = []
    for line in text.splitlines():
        m = _QUESTION_RE.match(line)
        if m:
            payload = m.group("text").strip()
            # Skip pure prefix/IRI noise.
            if payload and not payload.startswith(("<", "http")):
                comments.append(payload)

    question = ""
    for c in comments:
        if c.endswith("?"):
            question = c
            break
    if not question and comments:
        question = comments[0]

    notes = " ".join(c for c in comments if c != question)
    return question, notes


def _extract_terms(text: str) -> list[str]:
    """Extract referenced ontology term identifiers (e.g. OEO_00000207)."""
    terms = set(re.findall(r"\b(?:OEO|RO|BFO|IAO)_\d{6,}\b", text))
    return sorted(terms)


def _category_from_path(path: Path) -> str:
    """Derive the CQ category from the path relative to ``competency_questions``."""
    parts = path.parts
    if "competency_questions" in parts:
        idx = parts.index("competency_questions")
        sub = parts[idx + 1 : -1]
        if sub:
            return "/".join(sub)
    # Fallback: immediate parent directory name.
    return path.parent.name

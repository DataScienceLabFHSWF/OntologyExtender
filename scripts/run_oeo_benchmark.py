#!/usr/bin/env python3
"""Run the Open Energy Ontology (OEO) reproduction benchmark.

Three sub-commands:

    delta     Diff two OEO versions to obtain the gold "additions" delta.
    score     Score a generated ontology against a gold OEO snapshot.
    cqs       Load (and, if a reasoner is available, evaluate) OEO's native
              .omn competency-question entailment tests.

Examples
--------
    # What changed between two OEO releases?
    python scripts/run_oeo_benchmark.py delta \
        --old data/seed_ontology/oeo/oeo-vN.owl \
        --new data/seed_ontology/oeo/oeo-vN1.owl \
        --output results/oeo/delta.json

    # How well did the team reproduce the gold release (delta only)?
    python scripts/run_oeo_benchmark.py score \
        --generated data/exports/oeo_run/extended.owl \
        --gold data/seed_ontology/oeo/oeo-vN1.owl \
        --seed data/seed_ontology/oeo/oeo-vN.owl \
        --output results/oeo/score.json

    # Load OEO competency questions from a cloned ontology repo.
    python scripts/run_oeo_benchmark.py cqs \
        --cq-dir /path/to/ontology/tests/competency_questions \
        --ontology data/seed_ontology/oeo/oeo-vN1.owl \
        --output results/oeo/cq_eval.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import structlog

from ontology_hitl.benchmarking.oeo_benchmark import OEOBenchmark

logger = structlog.get_logger(__name__)


def _write(output: str | None, payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    else:
        print(text)


def cmd_delta(args: argparse.Namespace) -> int:
    bench = OEOBenchmark()
    delta = bench.version_delta(args.old, args.new)
    _write(args.output, delta.to_dict())
    s = delta.to_dict()["summary"]
    print(
        f"Delta: +{s['added_classes']} classes, "
        f"+{s['added_properties']} properties, "
        f"+{s['added_subclass_axioms']} subclass axioms"
    )
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    bench = OEOBenchmark()
    score = bench.score_reproduction(
        args.generated, args.gold, seed_path=args.seed
    )
    payload = score.to_dict()
    _write(args.output, payload)
    print(
        f"Reproduction F1 — classes: {score.class_f1:.3f}, "
        f"properties: {score.property_f1:.3f}, "
        f"subclass: {score.subclass_f1:.3f} | "
        f"consistent: {score.consistent} ({score.num_logical_issues} issues)"
    )
    return 0


def cmd_cqs(args: argparse.Namespace) -> int:
    bench = OEOBenchmark()
    categories = args.categories.split(",") if args.categories else None
    cqs = bench.load_competency_questions(args.cq_dir, categories=categories)
    print(f"Loaded {len(cqs)} OEO competency questions")

    payload: dict = {"loaded": len(cqs), "questions": [c.to_dict() for c in cqs]}
    if args.ontology:
        result = bench.evaluate_competency_questions(args.ontology, cqs)
        payload["evaluation"] = result.to_dict()
        print(
            f"CQ evaluation — reasoner: {result.reasoner}, "
            f"evaluated: {result.evaluated}, passed: {result.passed}, "
            f"skipped: {result.skipped}"
        )
        if result.skip_reason:
            print(f"  note: {result.skip_reason}")
    _write(args.output, payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_delta = sub.add_parser("delta", help="Diff two OEO versions")
    p_delta.add_argument("--old", required=True, help="Older OEO snapshot")
    p_delta.add_argument("--new", required=True, help="Newer OEO snapshot")
    p_delta.add_argument("--output", help="Output JSON path")
    p_delta.set_defaults(func=cmd_delta)

    p_score = sub.add_parser("score", help="Score generated vs gold")
    p_score.add_argument("--generated", required=True, help="Team-produced ontology")
    p_score.add_argument("--gold", required=True, help="Gold OEO snapshot")
    p_score.add_argument("--seed", help="Seed snapshot (score delta only)")
    p_score.add_argument("--output", help="Output JSON path")
    p_score.set_defaults(func=cmd_score)

    p_cqs = sub.add_parser("cqs", help="Load/evaluate OEO competency questions")
    p_cqs.add_argument("--cq-dir", required=True, help="OEO competency_questions directory")
    p_cqs.add_argument("--ontology", help="Snapshot to evaluate CQs against")
    p_cqs.add_argument("--categories", help="Comma-separated category whitelist")
    p_cqs.add_argument("--output", help="Output JSON path")
    p_cqs.set_defaults(func=cmd_cqs)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

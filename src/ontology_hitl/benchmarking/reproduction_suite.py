"""Reproduction benchmark suite — ordered from simple to research-grade.

Each :class:`ReproductionTarget` pairs a *seed* ontology (what the agent is
given) with a *gold* ontology (what it should produce) so the harness can
evaluate precision / recall / F1 of the agent's additions using the shared
:class:`~ontology_hitl.benchmarking.oeo_benchmark.OEOBenchmark` scorer.

Targets are ordered by :class:`Complexity` level so ablation experiments can
progress naturally from a smoke test to full research-grade evaluation:

  1. **Wine** (SMOKE) — W3C OWL-Guide tutorial ontology (~77 classes, simple DL).
     A core-backbone split acts as the seed; the full ontology is gold.
  2. **OWL-Time** (FORMAL) — Two real W3C versions (2006 → 2017 revision).
     Adds TemporalPosition, TimeZone, hasTRS, generalDay/Month/Year constructs.
  3. **PROV-O** (PROVENANCE) — W3C provenance ontology (~60 terms), split into
     core-PROV starting ontology → full W3C release.
  4. **OEO** (RESEARCH) — Open Energy Ontology v1.9 → v2.0 version delta.
     Large-scale domain ontology; the full research-grade benchmark.

Usage
-----
>>> suite = ReproductionSuite()
>>> suite.prepare_all()                   # download + create splits once
>>> for target in suite.targets:
...     delta = suite.benchmark.version_delta(target.seed_path, target.gold_path)
...     print(target.name, delta.to_dict()["summary"])
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

import structlog
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import SKOS

from ontology_hitl.benchmarking.oeo_benchmark import (
    OEOBenchmark,
    OntologyDelta,
    ReproductionScore,
)

logger = structlog.get_logger(__name__)

# Default cache location (relative to project root; overridable via HITL_REPRO_CACHE)
DEFAULT_CACHE = Path("data/benchmark_datasets/reproduction")

# ── Complexity ordering ────────────────────────────────────────────────────────


class Complexity(IntEnum):
    """Ordered difficulty tiers for the reproduction benchmark suite."""

    SMOKE = 1       # Wine: tiny, well-known, simple DL — smoke test
    FORMAL = 2      # OWL-Time: formal temporal logic, real two-version delta
    PROVENANCE = 3  # PROV-O: W3C provenance, single-version split
    RESEARCH = 4    # OEO: large energy-domain ontology, full version delta


# ── Target definition ─────────────────────────────────────────────────────────


@dataclass
class ReproductionTarget:
    """Metadata and local paths for a single reproduction benchmark target.

    For targets with two real published versions (*version-delta* mode),
    set both ``seed_url`` and ``gold_url``.  For targets built from a
    programmatic split set ``seed_url = ""`` — the suite will create the seed
    file from the gold file automatically on ``prepare()``.
    """

    name: str
    description: str
    complexity: Complexity
    gold_url: str
    gold_filename: str
    seed_url: str = ""          # "" → generate seed by splitting gold
    seed_filename: str = ""
    rdf_format: str = "xml"     # rdflib parse/serialize format hint
    split_fraction: float = 0.5  # fraction of leaf classes to keep as seed
    notes: str = ""

    @property
    def cache_dir(self) -> Path:
        return DEFAULT_CACHE / self.name

    @property
    def seed_path(self) -> Path:
        return self.cache_dir / self.seed_filename

    @property
    def gold_path(self) -> Path:
        return self.cache_dir / self.gold_filename

    @property
    def is_version_delta(self) -> bool:
        """True when both seed and gold come from real published URLs."""
        return bool(self.seed_url)


# ── Target registry ────────────────────────────────────────────────────────────

REGISTRY: list[ReproductionTarget] = [
    ReproductionTarget(
        name="wine",
        description=(
            "W3C OWL-Guide Wine Ontology (~77 classes, simple DL). "
            "Seed = backbone taxonomy (grape/winery/region supertypes only); "
            "gold = full tutorial ontology with quality/variety/colour classes."
        ),
        complexity=Complexity.SMOKE,
        gold_url="https://www.w3.org/TR/owl-guide/wine.rdf",
        gold_filename="wine_gold.rdf",
        seed_filename="wine_seed.ttl",
        rdf_format="xml",
        split_fraction=0.45,
        notes=(
            "Classic OWL DL example. Ablations here serve as smoke tests — "
            "if the agent cannot reproduce well-known wine classifications, "
            "something is fundamentally wrong with the pipeline."
        ),
    ),
    ReproductionTarget(
        name="owl_time",
        description=(
            "OWL-Time W3C 2006 → 2017 real version delta. "
            "2017 adds TemporalPosition, TimeZone, hasTRS, "
            "generalDay/Month/Year, and revised duration vocabulary."
        ),
        complexity=Complexity.FORMAL,
        seed_url="https://www.w3.org/2006/time",
        gold_url="https://www.w3.org/ns/owl-time",
        seed_filename="time_2006.ttl",
        gold_filename="time_2017.ttl",
        rdf_format="turtle",
        notes=(
            "Real two-version delta. Good Reasoner stress test because the "
            "2017 revision introduces tight temporal logic axioms."
        ),
    ),
    ReproductionTarget(
        name="prov_o",
        description=(
            "W3C PROV-O provenance ontology (~60 terms). "
            "Seed = PROV starting classes (Entity/Activity/Agent + usage/gen); "
            "gold = full W3C release including qualified derivation terms."
        ),
        complexity=Complexity.PROVENANCE,
        gold_url="https://www.w3.org/ns/prov-o",
        gold_filename="prov_gold.ttl",
        seed_filename="prov_seed.ttl",
        rdf_format="turtle",
        split_fraction=0.40,
        notes=(
            "Provenance domain. Tests whether the agent can extend a "
            "process-model ontology with higher-order derivation classes."
        ),
    ),
    ReproductionTarget(
        name="oeo",
        description=(
            "Open Energy Ontology v1.9 → v2.0 version delta. "
            "Full research-grade benchmark with 1 000+ classes."
        ),
        complexity=Complexity.RESEARCH,
        seed_url=(
            "https://github.com/OpenEnergyPlatform/ontology/releases/"
            "download/v1.9.0/oeo-full.omn"
        ),
        gold_url=(
            "https://github.com/OpenEnergyPlatform/ontology/releases/"
            "download/v2.0.0/oeo-full.omn"
        ),
        seed_filename="oeo_v1.9.omn",
        gold_filename="oeo_v2.0.omn",
        rdf_format="n3",
        notes=(
            "This is the primary benchmark used throughout the paper. "
            "Large download (~50 MB each); allow 10–20 min first run."
        ),
    ),
]

# Convenience: ordered by complexity ascending (easy → hard)
REGISTRY_ORDERED = sorted(REGISTRY, key=lambda t: t.complexity)


# ── Download helpers ───────────────────────────────────────────────────────────


def _download(url: str, dest: Path, *, timeout: int = 60) -> None:
    """Download *url* to *dest*, skipping if already present."""
    if dest.exists():
        logger.debug("repro_download_skip", dest=str(dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("repro_download_start", url=url, dest=str(dest))
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "text/turtle, application/rdf+xml, */*",
            "User-Agent": "OntologyExtender-ReproductionSuite/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    logger.info("repro_download_done", dest=str(dest), bytes=dest.stat().st_size)


# ── Seed-splitting logic ───────────────────────────────────────────────────────


def _build_seed_by_split(
    gold_path: Path,
    seed_path: Path,
    fraction: float,
    rdf_format: str,
) -> None:
    """Create a seed ontology by keeping only the backbone of *gold*.

    Strategy:
    - Keep all classes that *have* subclasses (i.e. are not pure leaves).
    - From the leaf classes (no subclasses), keep a deterministic ``fraction``
      sorted by URI so the split is reproducible.
    - Preserve all axioms that only reference kept classes.
    """
    if seed_path.exists():
        logger.debug("repro_seed_skip", seed=str(seed_path))
        return

    seed_path.parent.mkdir(parents=True, exist_ok=True)
    g = Graph()
    g.parse(str(gold_path))

    # Collect all named classes
    all_classes: set[URIRef] = set()
    for ctype in (OWL.Class, RDFS.Class):
        for s in g.subjects(RDF.type, ctype):
            if isinstance(s, URIRef):
                all_classes.add(s)

    # Split into inner (has subclasses) and leaf
    has_subclass: set[URIRef] = set()
    for sub, _, sup in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(sup, URIRef) and sup in all_classes:
            has_subclass.add(sup)

    inner = all_classes & has_subclass
    leaves = sorted(all_classes - has_subclass)  # sort for reproducibility

    n_keep = max(1, int(len(leaves) * fraction))
    kept = inner | set(leaves[:n_keep])

    # Build seed graph: copy all triples whose subject or range is in kept
    seed_g = Graph()
    # Copy namespace bindings
    for prefix, ns in g.namespaces():
        seed_g.bind(prefix, ns)

    for s, p, o in g:
        if isinstance(s, URIRef) and s in kept:
            # Include triple only if object references known URIs
            if isinstance(o, URIRef) and o not in kept and p == RDFS.subClassOf:
                continue  # drop subClassOf to unknown class
            seed_g.add((s, p, o))
        elif isinstance(s, URIRef) and p == RDF.type and o == OWL.Ontology:
            seed_g.add((s, p, o))  # keep ontology header

    seed_g.serialize(destination=str(seed_path), format="turtle")
    logger.info(
        "repro_seed_created",
        seed=str(seed_path),
        total_classes=len(all_classes),
        kept_classes=len(kept),
        dropped=len(all_classes) - len(kept),
    )


# ── Suite orchestrator ─────────────────────────────────────────────────────────


class ReproductionSuite:
    """Download, prepare and score all reproduction benchmark targets.

    Parameters
    ----------
    targets:
        Which targets to include. Defaults to :data:`REGISTRY_ORDERED`
        (all targets, easy → hard).
    benchmark:
        Optional pre-built :class:`OEOBenchmark`. A default is used when
        omitted.
    cache_dir:
        Root directory for downloaded ontology files.
    """

    def __init__(
        self,
        targets: list[ReproductionTarget] | None = None,
        benchmark: OEOBenchmark | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.targets = targets or REGISTRY_ORDERED
        self.benchmark = benchmark or OEOBenchmark()
        if cache_dir is not None:
            # Rebind DEFAULT_CACHE-relative paths to caller-specified dir
            for t in self.targets:
                t.__class__ = type(
                    t.__class__.__name__, (t.__class__,), {"cache_dir": property(lambda _: cache_dir / _.name)}
                )

    # ── Preparation ──────────────────────────────────────────────────

    def prepare(self, target: ReproductionTarget, *, timeout: int = 120) -> None:
        """Download (if needed) and create seed for a single target."""
        target.cache_dir.mkdir(parents=True, exist_ok=True)

        # Download gold
        _download(target.gold_url, target.gold_path, timeout=timeout)

        if target.is_version_delta:
            # Download seed from its own URL
            _download(target.seed_url, target.seed_path, timeout=timeout)
        else:
            # Build seed by splitting gold
            _build_seed_by_split(
                target.gold_path,
                target.seed_path,
                fraction=target.split_fraction,
                rdf_format=target.rdf_format,
            )

    def prepare_all(self, *, timeout: int = 120) -> None:
        """Prepare every target in order (easy → hard)."""
        for target in self.targets:
            try:
                self.prepare(target, timeout=timeout)
            except Exception as exc:
                logger.warning(
                    "repro_prepare_failed",
                    target=target.name,
                    error=str(exc),
                )

    # ── Scoring ───────────────────────────────────────────────────────

    def score_target(
        self,
        target: ReproductionTarget,
        generated_path: Path | str,
    ) -> ReproductionScore:
        """Score a generated ontology against *target*'s gold, subtracting seed."""
        return self.benchmark.score_reproduction(
            generated_path=generated_path,
            gold_path=target.gold_path,
            seed_path=target.seed_path,
        )

    def delta(self, target: ReproductionTarget) -> OntologyDelta:
        """Return the version delta (gold vs seed) for *target*."""
        return self.benchmark.version_delta(
            old_path=target.seed_path,
            new_path=target.gold_path,
        )

    # ── Summary helpers ───────────────────────────────────────────────

    def delta_summary(self) -> list[dict[str, Any]]:
        """Return delta summaries for all prepared targets (skips missing files)."""
        rows: list[dict[str, Any]] = []
        for t in self.targets:
            if not (t.seed_path.exists() and t.gold_path.exists()):
                rows.append({"name": t.name, "status": "not_prepared"})
                continue
            try:
                d = self.delta(t)
                rows.append(
                    {
                        "name": t.name,
                        "complexity": t.complexity.name,
                        "status": "ok",
                        **d.to_dict()["summary"],
                    }
                )
            except Exception as exc:
                rows.append({"name": t.name, "status": "error", "error": str(exc)})
        return rows

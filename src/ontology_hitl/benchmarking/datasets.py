"""External benchmark dataset registry and loader.

Provides a catalogue of evaluation datasets from recent ontology
engineering research, along with utilities to download, cache, and
load them for benchmarking.

Registered Datasets
-------------------
1. **OntoURL** (Zhang et al., 2025)
   - 58,981 questions from 40 ontologies across 8 domains
   - 15 tasks (Understanding / Reasoning / Learning)
   - Metrics: Accuracy, ROUGE-L, Triple-F1, Tuple-F1
   - Source: huggingface.co/datasets/XiaoZhang98/OntoURL
   - License: CC BY 4.0
   - Construction code: github.com/LastDance500/Bench_Construct
   - Evaluation code: github.com/LastDance500/OntoURL

2. **TamingHallucinations** (Fathallah, Staab & Algergawy, 2025)
   - Concept-level and triple-level semantic matching data
   - Reference ontologies from BioPortal (ENVO, OBOE-SBC, ChEBI)
   - 6 LLM-generated ontologies evaluated
   - Source: github.com/NadeenAhmad/TamingHallucinations
   - License: MIT

3. **Plu et al. Ontology Benchmark** (ISWC 2024)
   - Qualitative evaluation: user-generated ontologies + source docs
   - Quantitative evaluation: document sets for ontology generation
   - Tested: Claude 3.5 Sonnet, GPT-4o, GPT-4o-mini
   - Source: github.com/jplu/ontology-benchmark
   - License: Not specified

4. **OAEI-LLM** (Qiang et al., 2024)
   - Benchmark for detecting LLM hallucinations in ontology matching
   - Extension of OAEI (Ontology Alignment Evaluation Initiative)
   - Used by Agent-OM for hallucination-aware matching
   - Source: Referenced in Agent-OM paper

Dependencies
------------
- ``httpx``     for downloading datasets
- ``pathlib``   for path management
- ``json``      for dataset metadata
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from .models import BenchmarkDataset

logger = structlog.get_logger(__name__)


# =========================================================================
# Dataset Registry
# =========================================================================

DATASET_REGISTRY: dict[str, BenchmarkDataset] = {
    "ontourl": BenchmarkDataset(
        name="OntoURL",
        source="https://huggingface.co/datasets/XiaoZhang98/OntoURL",
        description=(
            "58,981 questions from 40 ontologies across 8 domains, "
            "structured into 15 tasks under three capability levels "
            "(Understanding, Reasoning, Learning).  Evaluated 20 LLMs "
            "in zero-shot, two-shot, and four-shot settings.  Includes "
            "MCQ, true/false, and generation tasks with domain-specific "
            "ontologies covering healthcare, geography, ecology, finance, "
            "transport, food, cultural heritage, and general purpose."
        ),
        license="CC BY 4.0",
        num_samples=58981,
        domains=[
            "healthcare", "geography", "ecology", "finance",
            "transport", "food", "cultural_heritage", "general",
        ],
        paper_reference=(
            "Zhang, X., Lai, H., Meng, Q., & Bos, J. (2025). "
            "OntoURL: A Benchmark for Evaluating Large Language Models "
            "on Symbolic Ontological Understanding, Reasoning and Learning. "
            "arXiv:2505.11031."
        ),
        tasks=[
            "U1_class_definition", "U2_class_relation", "U3_property_domain",
            "U4_instance_class", "U5_instance_definition",
            "R1_inferred_relation", "R2_constraint", "R3_instance_class_inferred",
            "R4_swrl_based", "R5_description_logic",
            "L1_class_def_generation", "L2_hierarchy_construction",
            "L3_property_construction", "L4_constraint_construction",
            "L5_ontology_alignment",
        ],
    ),
    "taming_hallucinations": BenchmarkDataset(
        name="TamingHallucinations",
        source="https://github.com/NadeenAhmad/TamingHallucinations",
        description=(
            "Semantic matching evaluation framework for LLM-generated "
            "ontologies.  Compares six LLM-generated ontologies against "
            "three BioPortal reference ontologies (ENVO, OBOE-SBC, ChEBI) "
            "using sentence-transformer embeddings (all-MiniLM-L6-v2).  "
            "Two-level evaluation: concept matching (label + definition, "
            "threshold ≥ 0.55) and triple matching (SPO sentences, "
            "threshold ≥ 0.50).  Unmatched items flagged as hallucinations."
        ),
        license="MIT",
        num_samples=None,
        domains=["life_sciences", "geoscience", "ecology"],
        paper_reference=(
            "Fathallah, N., Staab, S., & Algergawy, A. (2025). "
            "Taming Hallucinations: A Semantic Matching Evaluation "
            "Framework for LLM-Generated Ontologies. "
            "CEUR-WS Proceedings."
        ),
        tasks=[
            "concept_matching", "triple_matching",
            "hallucination_detection", "reference_alignment",
        ],
    ),
    "plu_ontology_benchmark": BenchmarkDataset(
        name="Plu et al. Ontology Benchmark",
        source="https://github.com/jplu/ontology-benchmark",
        description=(
            "Comprehensive benchmark from ISWC 2024 combining quantitative "
            "metrics (comparison against human-made reference ontologies) "
            "and qualitative user assessments across diverse domains.  "
            "The quantitative evaluation uses documents for ontology generation. "
            "The qualitative evaluation includes user-generated ontologies "
            "and source documents across domains (pydantic docs, geography, "
            "music theory, business articles).  "
            "Tested Claude 3.5 Sonnet, GPT-4o, GPT-4o-mini."
        ),
        license="Not specified",
        num_samples=None,
        domains=["software", "geography", "music", "business"],
        paper_reference=(
            "Plu, J., et al. (2024). A Comprehensive Benchmark for "
            "Evaluating LLM-Generated Ontologies. ISWC 2024."
        ),
        tasks=[
            "quantitative_evaluation", "qualitative_evaluation",
            "ontology_generation_from_documents",
        ],
    ),
    "oaei_llm": BenchmarkDataset(
        name="OAEI-LLM",
        source="https://oaei.ontologymatching.org/",
        description=(
            "Extension of the Ontology Alignment Evaluation Initiative (OAEI) "
            "benchmark for evaluating LLM hallucinations in ontology matching.  "
            "Used by Agent-OM to benchmark hallucination-aware matching.  "
            "Includes standard OAEI tracks with additional evaluation of "
            "matching quality under LLM-induced errors."
        ),
        license="Various (OAEI)",
        num_samples=None,
        domains=["biomedical", "conference", "anatomy"],
        paper_reference=(
            "Qiang, Z., et al. (2024). Agent-OM: Leveraging LLM Agents "
            "for Ontology Matching. VLDB 2024."
        ),
        tasks=[
            "ontology_matching", "alignment_evaluation",
            "hallucination_detection_in_matching",
        ],
    ),
}


# =========================================================================
# OntoURL Reference Ontologies (40 ontologies across 8 domains)
# =========================================================================

ONTOURL_ONTOLOGIES: dict[str, list[dict[str, str]]] = {
    "healthcare": [
        {"name": "SNOMED CT", "abbr": "SNOMED", "source": "snomed.org"},
        {"name": "Disease Ontology", "abbr": "DO", "source": "disease-ontology.org"},
        {"name": "Gene Ontology", "abbr": "GO", "source": "geneontology.org"},
        {"name": "Human Phenotype Ontology", "abbr": "HPO", "source": "hpo.jax.org"},
        {"name": "NCI Thesaurus", "abbr": "NCIt", "source": "ncit.nci.nih.gov"},
    ],
    "geography": [
        {"name": "GeoNames", "abbr": "GN", "source": "geonames.org"},
        {"name": "OpenStreetMap Ontology", "abbr": "OSM", "source": "openstreetmap.org"},
    ],
    "ecology": [
        {"name": "Environment Ontology", "abbr": "ENVO", "source": "obofoundry.org/ontology/envo"},
        {"name": "Plant Ontology", "abbr": "PO", "source": "planteome.org"},
    ],
    "finance": [
        {"name": "Financial Industry Business Ontology", "abbr": "FIBO", "source": "spec.edmcouncil.org/fibo"},
    ],
    "food": [
        {"name": "FoodOn", "abbr": "FoodOn", "source": "foodon.org"},
    ],
}


# =========================================================================
# Dataset Loader
# =========================================================================

class DatasetManager:
    """Download, cache, and load external benchmark datasets.

    Manages a local cache directory where downloaded datasets are stored,
    and provides loaders for each registered dataset format.

    Parameters
    ----------
    cache_dir : str | Path
        Directory for caching downloaded datasets.
        Default: ``data/benchmark_datasets/``

    Examples
    --------
    >>> dm = DatasetManager()
    >>> dm.list_available()
    ['ontourl', 'taming_hallucinations', 'plu_ontology_benchmark', 'oaei_llm']
    >>> info = dm.get_info("ontourl")
    >>> info.num_samples
    58981
    """

    def __init__(self, cache_dir: str | Path = "data/benchmark_datasets") -> None:
        self.cache_dir = Path(cache_dir)

    def list_available(self) -> list[str]:
        """List all registered dataset identifiers.

        Returns
        -------
        list[str]
            Dataset keys from the registry.
        """
        return list(DATASET_REGISTRY.keys())

    def get_info(self, dataset_id: str) -> BenchmarkDataset:
        """Get metadata for a registered dataset.

        Parameters
        ----------
        dataset_id : str
            One of the registered dataset keys.

        Returns
        -------
        BenchmarkDataset
            Dataset metadata including source, description, license.

        Raises
        ------
        KeyError
            If ``dataset_id`` is not in the registry.
        """
        if dataset_id not in DATASET_REGISTRY:
            raise KeyError(
                f"Unknown dataset '{dataset_id}'. "
                f"Available: {self.list_available()}"
            )
        return DATASET_REGISTRY[dataset_id]

    def download(self, dataset_id: str) -> Path:
        """Download a dataset to the local cache.

        Parameters
        ----------
        dataset_id : str
            Which dataset to download.

        Returns
        -------
        Path
            Local path where the dataset was cached.

        Raises
        ------
        NotImplementedError
            Dataset-specific download logic is not yet implemented.
        """
        raise NotImplementedError(
            f"TODO: implement download for '{dataset_id}' from "
            f"{DATASET_REGISTRY[dataset_id].source}"
        )

    def load_ontourl(self, local_path: Path | None = None) -> dict[str, Any]:
        """Load the OntoURL benchmark dataset.

        Loads the dataset from either the provided path or the
        HuggingFace datasets library.

        Parameters
        ----------
        local_path : Path | None
            Path to a local copy of the dataset.
            If ``None``, attempts to load via HuggingFace ``datasets`` library.

        Returns
        -------
        dict[str, Any]
            Dataset split into tasks, with questions and expected answers.

        Raises
        ------
        NotImplementedError
            Loader not yet implemented.

        Notes
        -----
        Recommended download::

            from datasets import load_dataset
            ds = load_dataset("XiaoZhang98/OntoURL")
        """
        raise NotImplementedError(
            "TODO: load_dataset('XiaoZhang98/OntoURL') or read from local_path"
        )

    def load_taming_hallucinations(
        self, repo_path: Path | None = None
    ) -> dict[str, Any]:
        """Load TamingHallucinations reference data.

        Loads BioPortal reference concepts/triples and LLM-generated
        concepts/triples from the cloned repository.

        Expected directory structure::

            data/bioportal_concepts/  → reference concept JSONs
            data/bioportal_triples/   → reference triple CSVs
            data/llm_concepts/        → LLM concept JSONs
            data/llm_triples/         → LLM triple CSVs

        Parameters
        ----------
        repo_path : Path | None
            Path to the cloned TamingHallucinations repo.
            If ``None``, uses ``cache_dir / 'TamingHallucinations'``.

        Returns
        -------
        dict[str, Any]
            ``{"reference_concepts": {...}, "reference_triples": [...],
              "llm_concepts": {...}, "llm_triples": [...]}``

        Raises
        ------
        NotImplementedError
            Loader not yet implemented.
        """
        raise NotImplementedError(
            "TODO: load concept JSONs and triple CSVs from repo_path"
        )

    def load_plu_benchmark(
        self, repo_path: Path | None = None
    ) -> dict[str, Any]:
        """Load Plu et al. (2024) benchmark data.

        Loads the qualitative and quantitative evaluation data from
        the cloned ontology-benchmark repository.

        Expected directory structure::

            qualitative evaluation/
              Ontologies and source docs/
                user{N}_documents.txt
            quantitative evaluation/
              documents/
                Copie de {N}.txt

        Parameters
        ----------
        repo_path : Path | None
            Path to the cloned ontology-benchmark repo.
            If ``None``, uses ``cache_dir / 'ontology-benchmark'``.

        Returns
        -------
        dict[str, Any]
            ``{"qualitative": [...], "quantitative": [...]}``

        Raises
        ------
        NotImplementedError
            Loader not yet implemented.
        """
        raise NotImplementedError(
            "TODO: load qualitative/quantitative evaluation data"
        )

    def get_reference_ontology_sources(self) -> dict[str, list[dict[str, str]]]:
        """Get the OntoURL reference ontology catalogue.

        Returns the catalogue of 40 ontologies across 8 domains
        used in the OntoURL benchmark, for reference and potential
        use as additional evaluation sources.

        Returns
        -------
        dict[str, list[dict[str, str]]]
            Mapping from domain to list of ontology metadata dicts.
        """
        return ONTOURL_ONTOLOGIES

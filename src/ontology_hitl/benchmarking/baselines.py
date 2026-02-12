"""Baseline system adapters — unified interface for running each system.

Each adapter wraps one baseline system and exposes a common ``run()``
method that:
  1. Prepares the test-case input (seed ontology, documents, CQs).
  2. Invokes the baseline's execution command.
  3. Collects the output ontology / results.
  4. Returns a partially-filled ``BenchmarkResult`` (metrics are
     computed separately by the evaluator).

Architecture
------------
::

    BaselineAdapter (ABC)
    ├── CogAgentAdapter        — Our system (in-process)
    ├── AgentOMAdapter         — Qiang et al. VLDB 2024
    ├── LLM4ACOEAdapter        — Soularidis et al. KER 2025
    └── NLPWord2VecAdapter     — Behr et al. 2023

All adapters share:
  - ``setup()``    — one-time installation / environment prep
  - ``run()``      — execute on a single TestCase
  - ``cleanup()``  — post-run teardown (temp files, processes)
  - ``is_available()`` — check if the baseline repo is cloned and deps installed

External Reference Points (not directly adapted, used for comparison):
  - OntoURL benchmark (Zhang et al. 2025): Reference scores for 20 LLMs
    across 15 ontology tasks.  Used to contextualise our results against
    state-of-the-art.  https://github.com/LastDance500/OntoURL
  - Plu et al. (2024) ISWC benchmark: Qualitative + quantitative evaluation
    data for Claude 3.5, GPT-4o, GPT-4o-mini on ontology generation.
    https://github.com/jplu/ontology-benchmark

References
----------
- BENCHMARKING_STRATEGY.md §Phase 1: Setup Both Baselines
- BENCHMARKING_QUICKSTART.md §Step-by-Step baseline setup commands
"""

from __future__ import annotations

import abc
import subprocess
import time
from pathlib import Path
from typing import Any

import structlog

from .models import (
    BaselineSystem,
    BaselineSystemConfig,
    BenchmarkResult,
    ReductionLevel,
    TestCase,
)

logger = structlog.get_logger(__name__)


# =========================================================================
# Abstract Base
# =========================================================================

class BaselineAdapter(abc.ABC):
    """Abstract base class for benchmark system adapters.

    Every adapter must implement ``run()`` and ``is_available()``.
    The optional ``setup()`` and ``cleanup()`` hooks have no-op defaults.

    Parameters
    ----------
    config : BaselineSystemConfig
        System-specific configuration (repo path, commands, env vars).
    """

    def __init__(self, config: BaselineSystemConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """One-time setup: clone repo, install deps, prepare environment.

        Default implementation runs ``config.setup_commands`` sequentially.
        Override for system-specific initialisation.

        Raises
        ------
        subprocess.CalledProcessError
            If any setup command fails.
        """
        raise NotImplementedError(
            "TODO: iterate config.setup_commands, subprocess.run each"
        )

    def cleanup(self) -> None:
        """Post-run cleanup: remove temp files, stop background processes.

        Default: no-op.  Override if the baseline leaves artefacts.
        """
        pass  # No-op default

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check whether this baseline is installed and ready to run.

        Returns
        -------
        bool
            ``True`` if the system can be invoked right now.
        """
        ...

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def run(self, test_case: TestCase) -> BenchmarkResult:
        """Execute the baseline system on a single test case.

        Parameters
        ----------
        test_case : TestCase
            The test case specifying the reduced seed ontology and
            expected gold-standard.

        Returns
        -------
        BenchmarkResult
            Result with ``output_ontology_path``, ``wall_clock_seconds``,
            ``classes_generated``, ``properties_generated`` populated.
            Metric scores are *not* computed here — that is done by
            the evaluation module.

        Raises
        ------
        TimeoutError
            If the run exceeds ``config.timeout_seconds``.
        RuntimeError
            If the baseline produces no output or crashes.
        """
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_subprocess(
        self, command: str, cwd: Path | None = None, timeout: int | None = None
    ) -> subprocess.CompletedProcess:
        """Run a shell command as a subprocess with timeout.

        Parameters
        ----------
        command : str
            Shell command string.
        cwd : Path | None
            Working directory.  Defaults to ``config.repo_path``.
        timeout : int | None
            Seconds before SIGKILL.  Defaults to ``config.timeout_seconds``.

        Returns
        -------
        subprocess.CompletedProcess

        Raises
        ------
        subprocess.TimeoutExpired
        subprocess.CalledProcessError
        """
        raise NotImplementedError(
            "TODO: subprocess.run(command, shell=True, cwd=..., timeout=...)"
        )


# =========================================================================
# CogAgent Adapter (Our System)
# =========================================================================

class CogAgentAdapter(BaselineAdapter):
    """Adapter for running CogAgent (our multi-agent debate + HITL system).

    Unlike external baselines, CogAgent runs *in-process* using the
    existing ``FeedbackLoopOrchestrator``.  This adapter:
      1. Configures a temporary iteration directory per test case.
      2. Loads the reduced seed ontology into Fuseki staging.
      3. Runs the feedback loop (configurable iterations).
      4. Collects the extended ontology from the staging graph.

    Parameters
    ----------
    config : BaselineSystemConfig
        Normally just needs ``system=COGAGENT``; repo_path is ignored.
    iterations : int
        Number of feedback-loop iterations to run per test case.
    debate_strategy : str
        One of ``"dialectical"``, ``"socratic"``, ``"mixed"``.
    auto_approve : bool
        If True, automatically approve all proposals (no HITL pause).
        Useful for unattended benchmark runs.
    """

    def __init__(
        self,
        config: BaselineSystemConfig,
        iterations: int = 3,
        debate_strategy: str = "dialectical",
        auto_approve: bool = True,
    ) -> None:
        super().__init__(config)
        self.iterations = iterations
        self.debate_strategy = debate_strategy
        self.auto_approve = auto_approve

    def is_available(self) -> bool:
        """CogAgent is always available (it's our own system).

        Returns
        -------
        bool
            Always ``True``.
        """
        return True

    def run(self, test_case: TestCase) -> BenchmarkResult:
        """Run CogAgent on a test case using FeedbackLoopOrchestrator.

        Steps
        -----
        1. Create a temporary iteration directory:
           ``results/benchmarking/cogagent_{reduction_level}/``
        2. Copy the reduced seed ontology to the iteration input.
        3. Instantiate ``FeedbackLoopOrchestrator`` with the test case's
           seed ontology and configure debate strategy.
        4. Run ``iterations`` rounds of the feedback loop.
        5. Export the final extended ontology.
        6. Count new classes/properties vs. the seed.

        Parameters
        ----------
        test_case : TestCase

        Returns
        -------
        BenchmarkResult
            With ``classes_generated``, ``properties_generated``,
            ``output_ontology_path``, and ``wall_clock_seconds``.
        """
        raise NotImplementedError(
            "TODO: instantiate FeedbackLoopOrchestrator, run loop, "
            "export results, count additions"
        )


# =========================================================================
# Agent-OM Adapter (Qiang et al., VLDB 2024)
# =========================================================================

class AgentOMAdapter(BaselineAdapter):
    """Adapter for Agent-OM — 2-agent ontology *matching* system.

    Agent-OM is designed for ontology *alignment* (matching two
    existing ontologies), not extension.  To benchmark it fairly:
      1. We create a source ontology (the reduced seed) and a target
         ontology (the gold standard).
      2. Agent-OM produces an alignment mapping between them.
      3. We interpret matched classes as "recovered" (analogous to
         CogAgent discovering missing classes).
      4. Unmatched gold-standard classes count as misses.

    Repository: https://github.com/qzc438/ontology-llm
    Requirements: PostgreSQL + pgvector, Python 3.10+

    Parameters
    ----------
    config : BaselineSystemConfig
        Must include ``repo_path`` pointing to cloned ontology-llm repo.
    similarity_threshold : float
        Agent-OM's matching threshold (default 0.90 per their paper).

    Notes
    -----
    Agent-OM uses a *matching* paradigm that is fundamentally
    different from CogAgent's *extension* paradigm.  The benchmark
    acknowledges this asymmetry in the comparison narrative — see
    BASELINE_POSITIONING_SUMMARY.md §Red Flag 1.
    """

    def __init__(
        self,
        config: BaselineSystemConfig,
        similarity_threshold: float = 0.90,
    ) -> None:
        super().__init__(config)
        self.similarity_threshold = similarity_threshold

    def is_available(self) -> bool:
        """Check if Agent-OM repo is cloned and PostgreSQL is reachable.

        Returns
        -------
        bool
            ``True`` if repo exists at ``config.repo_path`` and
            ``run_config.py`` is present.
        """
        raise NotImplementedError(
            "TODO: check repo_path exists, run_config.py present, "
            "optionally test psql connection"
        )

    def run(self, test_case: TestCase) -> BenchmarkResult:
        """Run Agent-OM matching between reduced seed and gold standard.

        Steps
        -----
        1. Prepare input: copy reduced seed → ``{repo}/alignment/source.owl``
           and gold standard → ``{repo}/alignment/target.owl``.
        2. Configure ``run_config.py`` with similarity_threshold.
        3. Execute ``python run_config.py``.
        4. Parse ``result.csv`` for Precision / Recall / F-measure.
        5. Map matched classes to "recovered" elements for metric computation.

        Parameters
        ----------
        test_case : TestCase

        Returns
        -------
        BenchmarkResult
            With matched classes interpreted as ``classes_generated``,
            and raw Agent-OM metrics in ``raw_output``.
        """
        raise NotImplementedError(
            "TODO: prepare alignment input, run Agent-OM, parse result.csv"
        )

    def _prepare_alignment_input(
        self, test_case: TestCase
    ) -> tuple[Path, Path]:
        """Copy seed and gold-standard to Agent-OM's expected layout.

        Agent-OM expects::

            alignment/<task_name>/source.owl
            alignment/<task_name>/target.owl

        Parameters
        ----------
        test_case : TestCase

        Returns
        -------
        tuple[Path, Path]
            (source_path, target_path) inside the Agent-OM repo.
        """
        raise NotImplementedError(
            "TODO: shutil.copy seed and gold to alignment dir"
        )

    def _parse_agent_om_results(self, result_csv: Path) -> dict[str, float]:
        """Parse Agent-OM's result.csv into a metrics dict.

        Expected CSV columns: Precision, Recall, F-measure.

        Parameters
        ----------
        result_csv : Path

        Returns
        -------
        dict[str, float]
            Keys: ``precision``, ``recall``, ``f_measure``.
        """
        raise NotImplementedError(
            "TODO: csv.reader on result.csv, extract metrics"
        )


# =========================================================================
# LLM4ACOE Adapter (Soularidis et al., KER 2025)
# =========================================================================

class LLM4ACOEAdapter(BaselineAdapter):
    """Adapter for LLM4ACOE — 3-agent autonomous ontology extension.

    LLM4ACOE uses three collaborative agents (Engineer, Expert, Worker)
    to autonomously construct an ontology from source documents.
    It achieved 78 % CQ coverage on the SAR wildfire domain.

    For fair comparison:
      1. We provide the same source documents / domain context.
      2. We provide the same seed ontology as starting point
         (LLM4ACOE can use it as context even though it was designed
         for from-scratch generation).
      3. We measure the same six-dimension metrics.

    Repository: https://github.com/AndreasSoularidis/LLM-based-OE-Framework-LC3
    Requirements: Python 3.10+, OpenAI API key (or Ollama adapter)

    Parameters
    ----------
    config : BaselineSystemConfig
        Must include ``repo_path`` pointing to cloned repo.
    use_ollama : bool
        If True, patch LLM4ACOE to use local Ollama instead of OpenAI.
        This ensures fair comparison (same compute, same model family).
    """

    def __init__(
        self,
        config: BaselineSystemConfig,
        use_ollama: bool = True,
    ) -> None:
        super().__init__(config)
        self.use_ollama = use_ollama

    def is_available(self) -> bool:
        """Check if LLM4ACOE repo is cloned and dependencies installed.

        Returns
        -------
        bool
            ``True`` if repo exists and ``LLM4ACOE.py`` is present.
        """
        raise NotImplementedError(
            "TODO: check repo_path / LLM4ACOE.py exists"
        )

    def run(self, test_case: TestCase) -> BenchmarkResult:
        """Run LLM4ACOE on a test case.

        Steps
        -----
        1. Copy seed ontology and source documents to LLM4ACOE's
           expected input directory.
        2. Optionally patch the LLM backend to use Ollama.
        3. Execute ``python LLM4ACOE.py``.
        4. Collect the generated ontology from ``Experiments/<domain>/``.
        5. Parse the discussion transcript for metadata.

        Parameters
        ----------
        test_case : TestCase

        Returns
        -------
        BenchmarkResult
            With generated ontology path, class/property counts,
            and LLM4ACOE discussion transcript in ``raw_output``.
        """
        raise NotImplementedError(
            "TODO: prepare input, run LLM4ACOE.py, collect output"
        )

    def _patch_for_ollama(self) -> None:
        """Patch LLM4ACOE's OpenAI calls to use local Ollama.

        Creates a shim module that intercepts ``openai.ChatCompletion``
        calls and routes them to the Ollama-compatible endpoint at
        ``config.env_vars['OLLAMA_URL']``.

        This ensures both systems use the same model and compute,
        making the comparison fair.

        Notes
        -----
        The patch is applied via environment variables and a wrapper
        script, not by modifying the baseline's source code directly
        (we want reproducibility and clean separation).
        """
        raise NotImplementedError(
            "TODO: create Ollama-compatible shim for OpenAI API"
        )

    def _parse_llm4acoe_output(self, experiment_dir: Path) -> dict[str, Any]:
        """Parse LLM4ACOE's output directory for results.

        Looks for: generated ontology (Turtle/OWL), discussion
        transcript, agent logs, CQ evaluation results.

        Parameters
        ----------
        experiment_dir : Path
            E.g. ``Experiments/nuclear_75pct/``.

        Returns
        -------
        dict[str, Any]
            Parsed output including ontology path and metrics.
        """
        raise NotImplementedError(
            "TODO: glob for .owl/.ttl files, parse agent transcripts"
        )


# =========================================================================
# NLP-W2V Adapter (Behr et al., 2023)
# =========================================================================

class NLPWord2VecAdapter(BaselineAdapter):
    """Adapter for NLP-W2V — Word2Vec embeddings + ontology rules.

    NLP-W2V uses Word2Vec embeddings trained on domain corpora
    combined with hand-crafted ontology extension rules to propose
    new classes and relations.  It is the most traditional baseline.

    Repository: https://github.com/TUDoAD/NLP-Based-Ontology-Extender

    Parameters
    ----------
    config : BaselineSystemConfig
        Must include ``repo_path`` pointing to cloned repo.
    embedding_dim : int
        Word2Vec embedding dimensionality (default 100 per their paper).
    min_similarity : float
        Minimum cosine similarity to propose a new concept.
    """

    def __init__(
        self,
        config: BaselineSystemConfig,
        embedding_dim: int = 100,
        min_similarity: float = 0.70,
    ) -> None:
        super().__init__(config)
        self.embedding_dim = embedding_dim
        self.min_similarity = min_similarity

    def is_available(self) -> bool:
        """Check if NLP-W2V repo is cloned and ready.

        Returns
        -------
        bool
            ``True`` if repo exists at ``config.repo_path``.
        """
        raise NotImplementedError(
            "TODO: check repo_path exists, main script present"
        )

    def run(self, test_case: TestCase) -> BenchmarkResult:
        """Run NLP-W2V ontology extension on a test case.

        Steps
        -----
        1. Prepare corpus files from source documents.
        2. Train Word2Vec model on domain corpus.
        3. Execute the extension pipeline:
           a. Extract candidate terms from corpus.
           b. Match candidates to existing ontology via embeddings.
           c. Apply rules to propose new classes/relations.
        4. Collect the extended ontology output.

        Parameters
        ----------
        test_case : TestCase

        Returns
        -------
        BenchmarkResult
            With extended ontology, counts, and W2V-specific metadata.
        """
        raise NotImplementedError(
            "TODO: prepare corpus, run NLP-W2V pipeline, collect OWL output"
        )

    def _prepare_corpus(self, test_case: TestCase) -> Path:
        """Prepare domain corpus for Word2Vec training.

        Gathers text from source documents associated with the test
        case and formats them for NLP-W2V's expected input.

        Parameters
        ----------
        test_case : TestCase

        Returns
        -------
        Path
            Path to the prepared corpus file.
        """
        raise NotImplementedError(
            "TODO: extract text from source docs, write to corpus file"
        )


# =========================================================================
# Factory
# =========================================================================

def create_adapter(config: BaselineSystemConfig, **kwargs: Any) -> BaselineAdapter:
    """Factory function to create the appropriate adapter for a system.

    Parameters
    ----------
    config : BaselineSystemConfig
        Identifies which system and provides configuration.
    **kwargs
        Extra keyword arguments passed to the adapter constructor
        (e.g., ``iterations=5`` for CogAgent, ``use_ollama=True``
        for LLM4ACOE).

    Returns
    -------
    BaselineAdapter
        An instance of the appropriate adapter subclass.

    Raises
    ------
    ValueError
        If ``config.system`` is not recognised.

    Examples
    --------
    >>> cfg = BaselineSystemConfig(system=BaselineSystem.COGAGENT)
    >>> adapter = create_adapter(cfg, iterations=3)
    >>> isinstance(adapter, CogAgentAdapter)
    True
    """
    adapters = {
        BaselineSystem.COGAGENT: CogAgentAdapter,
        BaselineSystem.AGENT_OM: AgentOMAdapter,
        BaselineSystem.LLM4ACOE: LLM4ACOEAdapter,
        BaselineSystem.NLP_W2V: NLPWord2VecAdapter,
    }
    adapter_cls = adapters.get(config.system)
    if adapter_cls is None:
        raise ValueError(f"Unknown baseline system: {config.system}")
    return adapter_cls(config, **kwargs)

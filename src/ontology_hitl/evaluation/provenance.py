"""D — Provenance Chain: traceable evidence links for every proposal.

Inspired by the arXiv HITL paper (John et al., 2025) which found that
source passage highlighting helps users trust and validate AI outputs.

Every class, property, or constraint in the extended ontology is linked
back to its originating document(s) and passage(s) via PROV-O triples:

- ``prov:wasDerivedFrom`` — document chunk that inspired the class
- ``prov:wasGeneratedBy`` — the agent / debate round that produced it
- ``prov:generatedAtTime`` — timestamp
- ``rdfs:comment`` on the provenance — the actual evidence text

This enables "click to verify" in HITL review and full audit trails
for the thesis/paper.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog
from rdflib import RDFS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import PROV, XSD

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)

HITL = Namespace("urn:ontology-hitl:")


@dataclass
class EvidenceRecord:
    """A single piece of evidence linking an ontology element to a source."""

    element_uri: str               # the class/property being justified
    element_label: str
    document_id: str               # Qdrant chunk ID or document name
    passage: str                   # the actual text that supports this element
    confidence: float = 0.0        # agent confidence in this evidence
    agent_role: str = ""           # which agent cited this
    phase: str = ""                # which Ont-101 phase
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ProvenanceReport:
    """Collection of evidence records for an iteration."""

    iteration: int = 0
    records: list[EvidenceRecord] = field(default_factory=list)
    elements_with_evidence: int = 0
    elements_without_evidence: int = 0
    coverage_pct: float = 0.0


class ProvenanceTracker:
    """Track and store provenance metadata for ontology elements.

    Each proposal from the OntologyEngineer or review from the
    DomainExpert can carry evidence citations.  This tracker collects
    them and can emit PROV-O triples or a JSON audit trail.

    Parameters
    ----------
    settings:
        Application configuration.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._records: list[EvidenceRecord] = []

    # ── Recording evidence ──────────────────────────────────────────

    def record(
        self,
        element_uri: str,
        element_label: str,
        document_id: str,
        passage: str,
        confidence: float = 0.0,
        agent_role: str = "",
        phase: str = "",
    ) -> EvidenceRecord:
        """Record a provenance link between an ontology element and a source.

        Args:
            element_uri: URI of the class/property.
            element_label: Human-readable label.
            document_id: Qdrant chunk ID or document filename.
            passage: The evidence text from the document.
            confidence: Agent confidence in this evidence.
            agent_role: Which agent produced this citation.
            phase: Which Ont-101 phase.

        Returns:
            The created ``EvidenceRecord``.
        """
        rec = EvidenceRecord(
            element_uri=element_uri,
            element_label=element_label,
            document_id=document_id,
            passage=passage,
            confidence=confidence,
            agent_role=agent_role,
            phase=phase,
        )
        self._records.append(rec)
        logger.debug(
            "provenance_recorded",
            element=element_label,
            doc=document_id,
            agent=agent_role,
        )
        return rec

    def record_from_agent_message(
        self,
        element_uri: str,
        element_label: str,
        agent_content: dict,
        agent_role: str = "",
        phase: str = "",
    ) -> list[EvidenceRecord]:
        """Extract evidence citations from an agent's structured response.

        Looks for ``evidence``, ``evidence_snippets``, or ``source_evidence``
        fields in the agent's JSON content and records each as a
        provenance link.

        Returns:
            List of created ``EvidenceRecord`` objects.
        """
        records: list[EvidenceRecord] = []

        # DomainExpert typically returns accuracy_issues with evidence
        for issue in agent_content.get("accuracy_issues", []):
            if issue.get("evidence"):
                rec = self.record(
                    element_uri=element_uri,
                    element_label=element_label,
                    document_id="domain_expert_review",
                    passage=issue["evidence"],
                    agent_role=agent_role,
                    phase=phase,
                )
                records.append(rec)

        # Engineer proposals may have evidence fields
        for key in ("evidence", "evidence_snippets", "source_evidence"):
            snippets = agent_content.get(key, [])
            if isinstance(snippets, list):
                for snippet in snippets:
                    text = snippet if isinstance(snippet, str) else str(snippet)
                    rec = self.record(
                        element_uri=element_uri,
                        element_label=element_label,
                        document_id="proposal",
                        passage=text,
                        agent_role=agent_role,
                        phase=phase,
                    )
                    records.append(rec)

        return records

    # ── Retrieval ───────────────────────────────────────────────────

    def get_evidence_for(self, element_uri: str) -> list[EvidenceRecord]:
        """Get all evidence for a specific ontology element."""
        return [r for r in self._records if r.element_uri == element_uri]

    def report(self, iteration: int = 0) -> ProvenanceReport:
        """Generate a summary report of provenance coverage."""
        elements = {r.element_uri for r in self._records}
        return ProvenanceReport(
            iteration=iteration,
            records=list(self._records),
            elements_with_evidence=len(elements),
            coverage_pct=1.0 if elements else 0.0,
        )

    # ── RDF export ──────────────────────────────────────────────────

    def to_prov_graph(self) -> Graph:
        """Export all provenance as a PROV-O RDF graph.

        Produces triples like:

        .. code-block:: turtle

            <class_uri> prov:wasDerivedFrom <doc_id> .
            <doc_id> rdfs:comment "evidence passage" .
            <class_uri> prov:wasGeneratedBy <agent_role> .
            <class_uri> prov:generatedAtTime "..." .
        """
        g = Graph()
        g.bind("prov", PROV)
        g.bind("hitl", HITL)

        for rec in self._records:
            element = URIRef(rec.element_uri)
            doc = URIRef(HITL[f"doc/{rec.document_id}"])

            g.add((element, PROV.wasDerivedFrom, doc))
            g.add((doc, RDFS.comment, Literal(rec.passage[:500])))

            if rec.agent_role:
                agent = URIRef(HITL[f"agent/{rec.agent_role}"])
                g.add((element, PROV.wasGeneratedBy, agent))

            g.add((
                element,
                PROV.generatedAtTime,
                Literal(rec.timestamp.isoformat(), datatype=XSD.dateTime),
            ))

        logger.info("prov_graph_built", triples=len(g))
        return g

    # ── JSON export ─────────────────────────────────────────────────

    def to_json(self, path: str | Path | None = None) -> str:
        """Export provenance records as JSON.

        Args:
            path: Optional file path; if given, writes to file.

        Returns:
            JSON string.
        """
        data = [
            {
                "element_uri": r.element_uri,
                "element_label": r.element_label,
                "document_id": r.document_id,
                "passage": r.passage,
                "confidence": r.confidence,
                "agent_role": r.agent_role,
                "phase": r.phase,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in self._records
        ]
        text = json.dumps(data, indent=2)

        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            logger.info("provenance_exported", path=str(p), records=len(data))

        return text

    def to_dict(self) -> dict:
        """Export provenance records as a dictionary.

        Returns:
            Dictionary with provenance data.
        """
        return {
            "total_records": len(self._records),
            "records": [
                {
                    "element_uri": r.element_uri,
                    "element_label": r.element_label,
                    "document_id": r.document_id,
                    "passage": r.passage,
                    "confidence": r.confidence,
                    "agent_role": r.agent_role,
                    "phase": r.phase,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in self._records
            ]
        }

"""Tests for D — Provenance Tracker (evaluation.provenance)."""

from __future__ import annotations

import json

import pytest
from rdflib.namespace import PROV

from ontology_hitl.evaluation.provenance import (
    EvidenceRecord,
    ProvenanceReport,
    ProvenanceTracker,
)


# ── EvidenceRecord ──────────────────────────────────────────────────

def test_evidence_record_creation():
    rec = EvidenceRecord(
        element_uri="http://ex.org/Facility",
        element_label="Facility",
        document_id="chunk_42",
        passage="The facility is located...",
        confidence=0.9,
        agent_role="domain_expert",
        phase="3_terms",
    )
    assert rec.element_label == "Facility"
    assert rec.confidence == 0.9


# ── ProvenanceTracker recording ─────────────────────────────────────

def test_record():
    tracker = ProvenanceTracker()
    rec = tracker.record(
        element_uri="http://ex.org/Facility",
        element_label="Facility",
        document_id="doc_1",
        passage="Facilities must comply with...",
        agent_role="domain_expert",
        phase="3_terms",
    )
    assert rec.element_label == "Facility"
    assert len(tracker._records) == 1


def test_get_evidence_for():
    tracker = ProvenanceTracker()
    tracker.record("http://ex.org/A", "A", "doc1", "passage1")
    tracker.record("http://ex.org/B", "B", "doc2", "passage2")
    tracker.record("http://ex.org/A", "A", "doc3", "passage3")

    evidence = tracker.get_evidence_for("http://ex.org/A")
    assert len(evidence) == 2


def test_report():
    tracker = ProvenanceTracker()
    tracker.record("http://ex.org/A", "A", "doc1", "p1")
    tracker.record("http://ex.org/B", "B", "doc2", "p2")

    report = tracker.report(iteration=1)
    assert report.iteration == 1
    assert report.elements_with_evidence == 2
    assert report.coverage_pct == 1.0


def test_report_empty():
    tracker = ProvenanceTracker()
    report = tracker.report()
    assert report.elements_with_evidence == 0
    assert report.coverage_pct == 0.0


# ── Agent message extraction ───────────────────────────────────────

def test_record_from_agent_message_accuracy():
    tracker = ProvenanceTracker()
    content = {
        "accuracy_issues": [
            {"term": "Facility", "issue": "too broad", "evidence": "docs say X"},
        ],
    }
    records = tracker.record_from_agent_message(
        "http://ex.org/F", "F", content, agent_role="domain_expert",
    )
    assert len(records) == 1
    assert records[0].passage == "docs say X"


def test_record_from_agent_message_evidence_list():
    tracker = ProvenanceTracker()
    content = {"evidence": ["passage 1", "passage 2"]}
    records = tracker.record_from_agent_message(
        "http://ex.org/G", "G", content, agent_role="engineer",
    )
    assert len(records) == 2


# ── PROV-O graph export ────────────────────────────────────────────

def test_to_prov_graph():
    tracker = ProvenanceTracker()
    tracker.record("http://ex.org/A", "A", "doc1", "evidence text")
    g = tracker.to_prov_graph()
    assert len(g) > 0
    # Should have prov:wasDerivedFrom triple
    from rdflib import URIRef
    derived = list(g.objects(URIRef("http://ex.org/A"), PROV.wasDerivedFrom))
    assert len(derived) == 1


# ── JSON export ─────────────────────────────────────────────────────

def test_to_json():
    tracker = ProvenanceTracker()
    tracker.record("http://ex.org/X", "X", "doc1", "passage")
    text = tracker.to_json()
    data = json.loads(text)
    assert len(data) == 1
    assert data[0]["element_label"] == "X"


def test_to_json_file(tmp_path):
    tracker = ProvenanceTracker()
    tracker.record("http://ex.org/Y", "Y", "doc2", "passage2")
    path = tmp_path / "prov.json"
    tracker.to_json(path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert len(data) == 1


# ── Clear ───────────────────────────────────────────────────────────

def test_clear():
    tracker = ProvenanceTracker()
    tracker.record("http://ex.org/Z", "Z", "doc", "p")
    tracker.clear()
    assert len(tracker._records) == 0

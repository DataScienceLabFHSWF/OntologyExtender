"""Tests for Ontology 101 validation rules."""

from __future__ import annotations

import pytest

from ontology_hitl.methodology.ontology101 import (
    ClassHierarchy,
    HierarchyNode,
    PropertyProposal,
)
from ontology_hitl.methodology.validation_rules import (
    Severity,
    check_disjointness_opportunities,
    check_naming_conventions,
    check_no_cycles,
    check_property_attachment,
    check_single_subclass,
    check_too_many_siblings,
    validate_hierarchy,
)


# ── Fixtures ────────────────────────────────────────────────────────

def _make_hierarchy(nodes: list[dict]) -> ClassHierarchy:
    """Shorthand to build a ClassHierarchy from dicts."""
    h = ClassHierarchy()
    for n in nodes:
        h.nodes.append(HierarchyNode(
            uri=n.get("uri", f"plan:{n['label']}"),
            label=n["label"],
            parent_uri=n.get("parent_uri"),
            parent_label=n.get("parent_label"),
            is_from_seed=n.get("is_from_seed", False),
            disjoint_with=n.get("disjoint_with", []),
        ))
    return h


# ── Rule 1: Single subclass ────────────────────────────────────────

class TestSingleSubclass:
    def test_flags_single_child(self):
        h = _make_hierarchy([
            {"label": "Equipment", "uri": "plan:Equipment"},
            {"label": "Pump", "uri": "plan:Pump", "parent_uri": "plan:Equipment"},
        ])
        issues = check_single_subclass(h)
        assert len(issues) == 1
        assert issues[0].rule == "single-subclass"
        assert "Pump" in issues[0].message

    def test_ok_with_two_children(self):
        h = _make_hierarchy([
            {"label": "Equipment", "uri": "plan:Equipment"},
            {"label": "Pump", "uri": "plan:Pump", "parent_uri": "plan:Equipment"},
            {"label": "Valve", "uri": "plan:Valve", "parent_uri": "plan:Equipment"},
        ])
        issues = check_single_subclass(h)
        assert len(issues) == 0

    def test_leaf_nodes_ok(self):
        h = _make_hierarchy([
            {"label": "Pump", "uri": "plan:Pump"},
        ])
        issues = check_single_subclass(h)
        assert len(issues) == 0


# ── Rule 2: Too many siblings ──────────────────────────────────────

class TestTooManySiblings:
    def test_flags_over_12(self):
        children = [
            {"label": f"Type{i}", "uri": f"plan:Type{i}", "parent_uri": "plan:Root"}
            for i in range(15)
        ]
        h = _make_hierarchy([{"label": "Root", "uri": "plan:Root"}] + children)
        issues = check_too_many_siblings(h, max_siblings=12)
        assert len(issues) == 1
        assert "15" in issues[0].message

    def test_ok_under_limit(self):
        children = [
            {"label": f"Type{i}", "uri": f"plan:Type{i}", "parent_uri": "plan:Root"}
            for i in range(5)
        ]
        h = _make_hierarchy([{"label": "Root", "uri": "plan:Root"}] + children)
        issues = check_too_many_siblings(h, max_siblings=12)
        assert len(issues) == 0


# ── Rule 4: No cycles ─────────────────────────────────────────────

class TestNoCycles:
    def test_detects_cycle(self):
        h = _make_hierarchy([
            {"label": "A", "uri": "plan:A", "parent_uri": "plan:B"},
            {"label": "B", "uri": "plan:B", "parent_uri": "plan:A"},
        ])
        issues = check_no_cycles(h)
        assert len(issues) >= 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].rule == "hierarchy-cycle"

    def test_no_false_positive_on_tree(self):
        h = _make_hierarchy([
            {"label": "Root", "uri": "plan:Root"},
            {"label": "Child", "uri": "plan:Child", "parent_uri": "plan:Root"},
            {"label": "Leaf", "uri": "plan:Leaf", "parent_uri": "plan:Child"},
        ])
        issues = check_no_cycles(h)
        assert len(issues) == 0


# ── Rule 5: Naming ────────────────────────────────────────────────

class TestNaming:
    def test_flags_lowercase_start(self):
        h = _make_hierarchy([
            {"label": "pump", "uri": "plan:pump"},
        ])
        issues = check_naming_conventions(h)
        assert any(i.rule == "naming-not-pascal" for i in issues)

    def test_flags_plural(self):
        h = _make_hierarchy([
            {"label": "Pumps", "uri": "plan:Pumps"},
        ])
        issues = check_naming_conventions(h)
        assert any(i.rule == "naming-plural" for i in issues)

    def test_passes_good_name(self):
        h = _make_hierarchy([
            {"label": "DecommissioningProject", "uri": "plan:DecommissioningProject"},
        ])
        issues = check_naming_conventions(h)
        assert not any(i.rule == "naming-not-pascal" for i in issues)
        assert not any(i.rule == "naming-plural" for i in issues)

    def test_seed_classes_skipped(self):
        """Naming checks only apply to NEW classes, not seed."""
        h = _make_hierarchy([
            {"label": "pump", "uri": "plan:pump", "is_from_seed": True},
        ])
        issues = check_naming_conventions(h)
        assert len(issues) == 0


# ── Rule 6: Disjointness ──────────────────────────────────────────

class TestDisjointness:
    def test_suggests_disjointness_for_siblings(self):
        h = _make_hierarchy([
            {"label": "Equipment", "uri": "plan:Equipment"},
            {"label": "Pump", "uri": "plan:Pump", "parent_uri": "plan:Equipment"},
            {"label": "Valve", "uri": "plan:Valve", "parent_uri": "plan:Equipment"},
        ])
        issues = check_disjointness_opportunities(h)
        assert len(issues) == 1
        assert issues[0].rule == "disjointness-missing"

    def test_no_suggestion_if_already_disjoint(self):
        h = _make_hierarchy([
            {"label": "Equipment", "uri": "plan:Equipment"},
            {"label": "Pump", "uri": "plan:Pump", "parent_uri": "plan:Equipment",
             "disjoint_with": ["plan:Valve"]},
            {"label": "Valve", "uri": "plan:Valve", "parent_uri": "plan:Equipment"},
        ])
        issues = check_disjointness_opportunities(h)
        assert len(issues) == 0


# ── Rule 7: Property attachment ───────────────────────────────────

class TestPropertyAttachment:
    def test_flags_redundant_attachment(self):
        h = _make_hierarchy([
            {"label": "Equipment", "uri": "plan:Equipment"},
            {"label": "Pump", "uri": "plan:Pump", "parent_uri": "plan:Equipment"},
        ])
        props = [
            PropertyProposal(name="label", attached_to_class="plan:Equipment"),
            PropertyProposal(name="label", attached_to_class="plan:Pump"),
        ]
        issues = check_property_attachment(h, props)
        assert len(issues) == 1
        assert issues[0].rule == "property-redundant-attachment"

    def test_ok_for_different_properties(self):
        h = _make_hierarchy([
            {"label": "Equipment", "uri": "plan:Equipment"},
            {"label": "Pump", "uri": "plan:Pump", "parent_uri": "plan:Equipment"},
        ])
        props = [
            PropertyProposal(name="label", attached_to_class="plan:Equipment"),
            PropertyProposal(name="flowRate", attached_to_class="plan:Pump"),
        ]
        issues = check_property_attachment(h, props)
        assert len(issues) == 0


# ── Master runner ──────────────────────────────────────────────────

class TestValidateHierarchy:
    def test_returns_sorted_by_severity(self):
        h = _make_hierarchy([
            {"label": "A", "uri": "plan:A", "parent_uri": "plan:B"},
            {"label": "B", "uri": "plan:B", "parent_uri": "plan:A"},
            {"label": "pumps", "uri": "plan:pumps"},
        ])
        issues = validate_hierarchy(h)
        assert issues[0].severity == Severity.ERROR

    def test_clean_hierarchy_minimal_issues(self):
        """A well-formed hierarchy should only get info-level suggestions."""
        h = _make_hierarchy([
            {"label": "Thing", "uri": "plan:Thing", "is_from_seed": True},
            {"label": "Equipment", "uri": "plan:Equipment", "parent_uri": "plan:Thing",
             "is_from_seed": True},
            {"label": "Pump", "uri": "plan:Pump", "parent_uri": "plan:Equipment",
             "disjoint_with": ["plan:Valve"]},
            {"label": "Valve", "uri": "plan:Valve", "parent_uri": "plan:Equipment",
             "disjoint_with": ["plan:Pump"]},
        ])
        issues = validate_hierarchy(h)
        assert all(i.severity != Severity.ERROR for i in issues)

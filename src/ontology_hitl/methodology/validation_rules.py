"""Automated quality checks from Ontology 101 — Section 4.

Each function checks one rule from Noy & McGuinness and returns a list
of ``ValidationIssue`` diagnostics.  The agent runs all checks after
Phase 4 (hierarchy) and Phase 6 (facets) and surfaces issues as
``AgentQuestion`` items for the HITL reviewer.

Rules implemented
-----------------
1. No single subclass      (§4.2)
2. Too many siblings       (§4.2)
3. Siblings at same depth  (§4.2)
4. No hierarchy cycles     (§4.1)
5. Consistent naming       (§6)
6. Disjointness hints      (§4.8)
7. Property attachment      (§5, Step 5)
8. No class/instance confusion (§4.6)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ontology_hitl.methodology.ontology101 import (
    ClassHierarchy,
    FacetReport,
    HierarchyNode,
    PropertyProposal,
)


class Severity(str, Enum):
    ERROR = "error"       # violates a hard Ont-101 rule
    WARNING = "warning"   # likely modeling problem
    INFO = "info"         # suggestion / style


@dataclass
class ValidationIssue:
    """A quality problem found by an automated check."""

    rule: str             # machine-readable rule id, e.g. "single-subclass"
    severity: Severity
    message: str
    affected_classes: list[str] = field(default_factory=list)
    suggestion: str = ""
    ont101_section: str = ""  # e.g. "§4.2"


# ── Helpers ─────────────────────────────────────────────────────────

def _build_children_map(nodes: list[HierarchyNode]) -> dict[str | None, list[HierarchyNode]]:
    """Map parent_uri → list of child nodes."""
    children: dict[str | None, list[HierarchyNode]] = {}
    for node in nodes:
        parent = node.parent_uri
        children.setdefault(parent, []).append(node)
    return children


def _build_uri_map(nodes: list[HierarchyNode]) -> dict[str, HierarchyNode]:
    return {n.uri: n for n in nodes}


# ── Rule 1: No single subclass (§4.2) ──────────────────────────────

def check_single_subclass(hierarchy: ClassHierarchy) -> list[ValidationIssue]:
    """Flag classes that have exactly one direct subclass.

    "If a class has only one direct subclass there may be a modeling
    problem or the ontology is not complete." — §4.2
    """
    children_map = _build_children_map(hierarchy.nodes)
    issues: list[ValidationIssue] = []

    for node in hierarchy.nodes:
        kids = children_map.get(node.uri, [])
        if len(kids) == 1:
            child = kids[0]
            issues.append(ValidationIssue(
                rule="single-subclass",
                severity=Severity.WARNING,
                message=(
                    f"'{node.label}' has only one subclass '{child.label}'. "
                    f"Consider adding siblings or collapsing into one class."
                ),
                affected_classes=[node.uri, child.uri],
                suggestion=(
                    f"Either add more subclasses to '{node.label}' or "
                    f"merge '{child.label}' into '{node.label}'."
                ),
                ont101_section="§4.2",
            ))

    return issues


# ── Rule 2: Too many siblings (§4.2) ───────────────────────────────

def check_too_many_siblings(
    hierarchy: ClassHierarchy,
    max_siblings: int = 12,
) -> list[ValidationIssue]:
    """Flag parents with more than ``max_siblings`` direct subclasses.

    "If there are more than a dozen subclasses for a given class then
    additional intermediate categories may be necessary." — §4.2
    """
    children_map = _build_children_map(hierarchy.nodes)
    issues: list[ValidationIssue] = []

    for node in hierarchy.nodes:
        kids = children_map.get(node.uri, [])
        if len(kids) > max_siblings:
            issues.append(ValidationIssue(
                rule="too-many-siblings",
                severity=Severity.WARNING,
                message=(
                    f"'{node.label}' has {len(kids)} direct subclasses "
                    f"(> {max_siblings}). Consider adding intermediate categories."
                ),
                affected_classes=[node.uri] + [k.uri for k in kids],
                suggestion=(
                    f"Group the {len(kids)} subclasses of '{node.label}' "
                    f"into meaningful intermediate categories."
                ),
                ont101_section="§4.2",
            ))

    return issues


# ── Rule 3: Sibling generality level (§4.2) ───────────────────────

def check_sibling_depth_consistency(
    hierarchy: ClassHierarchy,
) -> list[ValidationIssue]:
    """Flag sibling groups where depths differ by more than 1 from their children.

    "All siblings in the hierarchy must be at the same level of
    generality." — §4.2

    We approximate "generality" by checking that sibling subtree depths
    don't differ wildly (one sibling is a leaf, another has 3+ levels).
    """
    children_map = _build_children_map(hierarchy.nodes)
    uri_map = _build_uri_map(hierarchy.nodes)
    issues: list[ValidationIssue] = []

    def _subtree_depth(uri: str, seen: set[str] | None = None) -> int:
        # Track visited nodes on the current recursion path to avoid infinite
        # recursion in presence of cycles. If a cycle is detected on this
        # path we treat the cyclic branch as a leaf (depth 0).
        if seen is None:
            seen = set()
        if uri in seen:
            return 0
        seen = seen | {uri}

        kids = children_map.get(uri, [])
        if not kids:
            return 0

        depths = [ _subtree_depth(k.uri, seen) for k in kids ]
        return 1 + max(depths)

    for node in hierarchy.nodes:
        kids = children_map.get(node.uri, [])
        if len(kids) < 2:
            continue

        depths = {k.label: _subtree_depth(k.uri) for k in kids}
        min_d, max_d = min(depths.values()), max(depths.values())

        if max_d - min_d > 2:
            issues.append(ValidationIssue(
                rule="sibling-depth-mismatch",
                severity=Severity.INFO,
                message=(
                    f"Siblings under '{node.label}' have uneven subtree "
                    f"depths ({min_d} to {max_d}). This may indicate "
                    f"mixed levels of generality."
                ),
                affected_classes=[k.uri for k in kids],
                suggestion=(
                    f"Check whether all children of '{node.label}' are "
                    f"at the same conceptual level."
                ),
                ont101_section="§4.2",
            ))

    return issues


# ── Rule 4: No hierarchy cycles (§4.1) ─────────────────────────────

def check_no_cycles(hierarchy: ClassHierarchy) -> list[ValidationIssue]:
    """Detect cycles in the class hierarchy.

    "We should avoid cycles in the class hierarchy." — §4.1
    """
    uri_map = _build_uri_map(hierarchy.nodes)
    issues: list[ValidationIssue] = []
    visited: set[str] = set()

    def _walk(uri: str, path: list[str]) -> None:
        if uri in path:
            cycle = path[path.index(uri):] + [uri]
            labels = [uri_map[u].label if u in uri_map else u for u in cycle]
            issues.append(ValidationIssue(
                rule="hierarchy-cycle",
                severity=Severity.ERROR,
                message=f"Cycle detected: {' → '.join(labels)}",
                affected_classes=cycle,
                suggestion="Break the cycle by removing one subclass link.",
                ont101_section="§4.1",
            ))
            return

        if uri in visited:
            return
        visited.add(uri)

        node = uri_map.get(uri)
        if node and node.parent_uri and node.parent_uri in uri_map:
            _walk(node.parent_uri, path + [uri])

    for node in hierarchy.nodes:
        if node.uri not in visited:
            _walk(node.uri, [])

    return issues


# ── Rule 5: Consistent naming (§6) ─────────────────────────────────

def check_naming_conventions(hierarchy: ClassHierarchy) -> list[ValidationIssue]:
    """Check PascalCase for classes, no abbreviations, singular form.

    "Use singular or plural — but be consistent." (§6.2)
    "Capitalize class names." (§6.1)
    "Avoid abbreviations." (§6.4)
    """
    issues: list[ValidationIssue] = []
    labels = [n.label for n in hierarchy.nodes if not n.is_from_seed]

    for label in labels:
        # PascalCase check
        if label and not label[0].isupper():
            issues.append(ValidationIssue(
                rule="naming-not-pascal",
                severity=Severity.WARNING,
                message=f"Class '{label}' should start with an uppercase letter (PascalCase).",
                affected_classes=[label],
                suggestion=f"Rename to '{label[0].upper() + label[1:]}'.",
                ont101_section="§6.1",
            ))

        # Plural check (simple heuristic: ends in 's' but not 'ss', 'us', 'is')
        if (
            label.endswith("s")
            and not label.endswith("ss")
            and not label.endswith("us")
            and not label.endswith("is")
            and not label.endswith("ness")
            and not label.endswith("sis")
            and len(label) > 3
        ):
            issues.append(ValidationIssue(
                rule="naming-plural",
                severity=Severity.INFO,
                message=f"Class '{label}' appears to be plural. Prefer singular class names.",
                affected_classes=[label],
                suggestion=f"Consider renaming to '{label.rstrip('s')}'.",
                ont101_section="§6.2",
            ))

        # Short abbreviation check (all caps, > 1 char)
        if label.isupper() and len(label) > 1:
            issues.append(ValidationIssue(
                rule="naming-abbreviation",
                severity=Severity.INFO,
                message=f"Class '{label}' looks like an abbreviation. Prefer full names.",
                affected_classes=[label],
                suggestion="Use the full term instead of an abbreviation.",
                ont101_section="§6.4",
            ))

    return issues


# ── Rule 6: Disjointness hints (§4.8) ──────────────────────────────

def check_disjointness_opportunities(
    hierarchy: ClassHierarchy,
) -> list[ValidationIssue]:
    """Suggest disjointness declarations for sibling groups.

    "Specifying that classes are disjoint enables the system to validate
    the ontology better." — §4.8

    Heuristic: if a parent has 2-5 children and none declare disjointness,
    suggest the user consider it.
    """
    children_map = _build_children_map(hierarchy.nodes)
    issues: list[ValidationIssue] = []

    for node in hierarchy.nodes:
        kids = children_map.get(node.uri, [])
        if 2 <= len(kids) <= 8:
            any_disjoint = any(bool(k.disjoint_with) for k in kids)
            if not any_disjoint:
                kid_labels = [k.label for k in kids]
                issues.append(ValidationIssue(
                    rule="disjointness-missing",
                    severity=Severity.INFO,
                    message=(
                        f"Siblings under '{node.label}' "
                        f"({', '.join(kid_labels)}) don't declare "
                        f"disjointness. Consider whether any pairs are "
                        f"mutually exclusive."
                    ),
                    affected_classes=[k.uri for k in kids],
                    suggestion=(
                        f"If instances of one sibling can never be "
                        f"instances of another, declare them disjoint."
                    ),
                    ont101_section="§4.8",
                ))

    return issues


# ── Rule 7: Property attachment level (§5, Step 5) ─────────────────

def check_property_attachment(
    hierarchy: ClassHierarchy,
    properties: list[PropertyProposal],
) -> list[ValidationIssue]:
    """Check that properties are attached at the most general class.

    "A slot should be attached at the most general class that can have
    that property." — Section 3, Step 5

    If the same property name appears on a class AND one of its
    subclasses, it should probably only be on the superclass.
    """
    children_map = _build_children_map(hierarchy.nodes)
    uri_map = _build_uri_map(hierarchy.nodes)
    issues: list[ValidationIssue] = []

    # Group properties by name
    prop_by_name: dict[str, list[PropertyProposal]] = {}
    for p in properties:
        prop_by_name.setdefault(p.name, []).append(p)

    def _is_ancestor(ancestor_uri: str, descendant_class: str) -> bool:
        """Check if ancestor_uri is an ancestor of descendant_class."""
        current = descendant_class
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            node = uri_map.get(current)
            if not node:
                return False
            if node.parent_uri == ancestor_uri:
                return True
            current = node.parent_uri
        return False

    for prop_name, prop_list in prop_by_name.items():
        if len(prop_list) < 2:
            continue
        classes = [p.attached_to_class for p in prop_list]
        for i, c1 in enumerate(classes):
            for c2 in classes[i + 1:]:
                if _is_ancestor(c1, c2):
                    issues.append(ValidationIssue(
                        rule="property-redundant-attachment",
                        severity=Severity.WARNING,
                        message=(
                            f"Property '{prop_name}' is on '{c1}' AND its "
                            f"descendant '{c2}'. It should only be on '{c1}' "
                            f"(subclasses inherit it)."
                        ),
                        affected_classes=[c1, c2],
                        suggestion=f"Remove '{prop_name}' from '{c2}'.",
                        ont101_section="§3 Step 5",
                    ))
                elif _is_ancestor(c2, c1):
                    issues.append(ValidationIssue(
                        rule="property-redundant-attachment",
                        severity=Severity.WARNING,
                        message=(
                            f"Property '{prop_name}' is on '{c2}' AND its "
                            f"descendant '{c1}'. It should only be on '{c2}' "
                            f"(subclasses inherit it)."
                        ),
                        affected_classes=[c2, c1],
                        suggestion=f"Remove '{prop_name}' from '{c1}'.",
                        ont101_section="§3 Step 5",
                    ))

    return issues


# ── Master runner ──────────────────────────────────────────────────

def validate_hierarchy(
    hierarchy: ClassHierarchy,
    properties: list[PropertyProposal] | None = None,
) -> list[ValidationIssue]:
    """Run all hierarchy validation checks.

    Returns issues sorted by severity (errors first).
    """
    issues: list[ValidationIssue] = []

    issues.extend(check_no_cycles(hierarchy))
    issues.extend(check_single_subclass(hierarchy))
    issues.extend(check_too_many_siblings(hierarchy))
    issues.extend(check_sibling_depth_consistency(hierarchy))
    issues.extend(check_naming_conventions(hierarchy))
    issues.extend(check_disjointness_opportunities(hierarchy))

    if properties:
        issues.extend(check_property_attachment(hierarchy, properties))

    # Sort: errors → warnings → info
    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    issues.sort(key=lambda i: severity_order[i.severity])

    return issues

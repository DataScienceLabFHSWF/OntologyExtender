"""Logical consistency checking for OWL ontologies and proposals.

The :class:`ConsistencyChecker` materialises an ``rdflib`` graph, applies
OWL-RL/RDFS deductive closure (via ``owlrl`` when available), and then runs a
set of TBox-level structural checks that detect logical flaws:

* **Unsatisfiable classes** — a class that is a subclass (directly or
  transitively) of two mutually disjoint classes can never have instances.
* **Disjointness violations** — a class asserted ``owl:disjointWith`` another
  while also being subsumed by it.
* **Subclass cycles** — ``A ⊑ B ⊑ … ⊑ A`` with distinct, non-equivalent
  classes (an undeclared equivalence that usually signals a modelling error).
* **Domain/range conflicts** — a property whose declared domains (or ranges)
  are mutually disjoint, making the property unsatisfiable.

These checks intentionally complement — not duplicate — the *methodological*
structural rules in ``ontology_hitl.methodology.validation_rules`` (single
child, sibling balance, naming). Here we focus purely on *logical* soundness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef

logger = structlog.get_logger(__name__)

# Default namespace for materialising proposals (mirrors schema/manager.py).
_ONTOLOGY_BASE = "http://purl.org/2024/planning-ontology#"

_XSD_TYPE_MAP: dict[str, URIRef] = {
    "xsd:string": XSD.string,
    "xsd:integer": XSD.integer,
    "xsd:int": XSD.integer,
    "xsd:float": XSD.float,
    "xsd:double": XSD.double,
    "xsd:decimal": XSD.decimal,
    "xsd:boolean": XSD.boolean,
    "xsd:dateTime": XSD.dateTime,
    "xsd:date": XSD.date,
    "xsd:anyURI": XSD.anyURI,
}


class LogicalIssueKind(str, Enum):
    """Categories of logical defect detected by the reasoner."""

    UNSATISFIABLE_CLASS = "unsatisfiable_class"
    DISJOINTNESS_VIOLATION = "disjointness_violation"
    SUBCLASS_CYCLE = "subclass_cycle"
    DOMAIN_RANGE_CONFLICT = "domain_range_conflict"
    EQUIVALENCE_CONTRADICTION = "equivalence_contradiction"


@dataclass
class LogicalIssue:
    """A single logical defect found during consistency checking."""

    kind: LogicalIssueKind
    severity: str  # "error" | "warning"
    message: str
    affected: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (for JSON / agent messages)."""
        return {
            "kind": self.kind.value,
            "severity": self.severity,
            "message": self.message,
            "affected": list(self.affected),
            "explanation": self.explanation,
        }


@dataclass
class ConsistencyReport:
    """Result of a consistency check over a graph or proposal."""

    consistent: bool
    issues: list[LogicalIssue] = field(default_factory=list)
    num_classes: int = 0
    num_axioms: int = 0
    inferred_triples: int = 0
    reasoner: str = "owlrl"

    @property
    def errors(self) -> list[LogicalIssue]:
        """Issues with ``error`` severity (block consistency)."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[LogicalIssue]:
        """Issues with ``warning`` severity (advisory only)."""
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (for JSON / agent messages)."""
        return {
            "consistent": self.consistent,
            "num_classes": self.num_classes,
            "num_axioms": self.num_axioms,
            "inferred_triples": self.inferred_triples,
            "reasoner": self.reasoner,
            "issues": [i.to_dict() for i in self.issues],
        }


class ConsistencyChecker:
    """Detect logical inconsistencies in OWL ontologies and proposals.

    Parameters
    ----------
    base_namespace:
        Namespace used when materialising proposal dicts into a graph.
    use_owlrl:
        If ``True`` (default), apply OWL-RL deductive closure before the
        structural checks. Falls back to a manual transitive subclass closure
        when ``owlrl`` is not installed.
    """

    def __init__(
        self,
        base_namespace: str = _ONTOLOGY_BASE,
        use_owlrl: bool = True,
    ) -> None:
        self.base_namespace = base_namespace
        self.use_owlrl = use_owlrl

    # ── Public API ──────────────────────────────────────────────────

    def check_graph(self, graph: Graph) -> ConsistencyReport:
        """Run the full consistency analysis over an ``rdflib`` graph.

        The input graph is never mutated; reasoning runs on a copy.
        """
        num_axioms = len(graph)
        reasoned, reasoner_name = self._materialise(graph)
        inferred = max(0, len(reasoned) - num_axioms)

        classes = self._collect_classes(reasoned)
        superclasses = self._transitive_superclasses(reasoned, classes)
        disjoint_pairs = self._disjoint_pairs(reasoned)

        issues: list[LogicalIssue] = []
        issues.extend(self._check_unsatisfiable(classes, superclasses, disjoint_pairs))
        issues.extend(self._check_disjoint_subclass(superclasses, disjoint_pairs))
        # Cycle detection runs on the *asserted* graph: OWL-RL closure turns a
        # mutual subclass cycle into an inferred owl:equivalentClass, which
        # would otherwise mask the modelling error.
        issues.extend(self._check_cycles(graph, classes))
        issues.extend(self._check_domain_range(reasoned, disjoint_pairs))

        consistent = not any(i.severity == "error" for i in issues)
        return ConsistencyReport(
            consistent=consistent,
            issues=issues,
            num_classes=len(classes),
            num_axioms=num_axioms,
            inferred_triples=inferred,
            reasoner=reasoner_name,
        )

    def check_file(self, path: str | Path) -> ConsistencyReport:
        """Parse an OWL/TTL file and check its consistency."""
        graph = Graph()
        graph.parse(str(path))
        return self.check_graph(graph)

    def check_proposal(
        self,
        proposal: dict[str, Any],
        seed_graph: Graph | None = None,
    ) -> ConsistencyReport:
        """Materialise a proposal dict (optionally merged with a seed graph)
        and check the combined graph for logical defects.
        """
        graph = Graph()
        if seed_graph is not None:
            for triple in seed_graph:
                graph.add(triple)
        self.proposal_to_graph(proposal, graph)
        return self.check_graph(graph)

    # ── Proposal materialisation ────────────────────────────────────

    def proposal_to_graph(
        self,
        proposal: dict[str, Any],
        graph: Graph | None = None,
    ) -> Graph:
        """Convert a debate proposal dict into RDF triples.

        Understands the flexible shapes produced by the OntologyEngineer:
        ``classes`` / ``nodes`` / ``terms`` lists of class-like dicts and
        ``properties`` / ``relations`` lists of property-like dicts. Each
        class dict may carry ``disjoint_with`` to declare disjointness.
        """
        g = graph if graph is not None else Graph()
        ns = Namespace(self.base_namespace)
        g.bind("ex", ns)

        def class_uri(name_or_uri: str) -> URIRef:
            if name_or_uri.startswith(("http://", "https://", "urn:")):
                return URIRef(name_or_uri)
            return ns[_local(name_or_uri)]

        # Classes (accept several key aliases used across phases).
        class_items: list[dict] = []
        for key in ("classes", "nodes", "terms", "new_classes"):
            class_items.extend(
                item for item in proposal.get(key, []) if isinstance(item, dict)
            )

        for item in class_items:
            label = item.get("label") or item.get("name") or item.get("term")
            if not label:
                continue
            c_uri = class_uri(item.get("uri", label))
            g.add((c_uri, RDF.type, OWL.Class))
            g.add((c_uri, RDFS.label, Literal(label)))
            definition = item.get("definition") or item.get("description")
            if definition:
                g.add((c_uri, RDFS.comment, Literal(definition)))

            parent = item.get("parent_uri") or item.get("parent_label") or item.get("parent")
            if parent:
                g.add((c_uri, RDFS.subClassOf, class_uri(str(parent))))

            for dj in item.get("disjoint_with", []) or []:
                if dj:
                    g.add((c_uri, OWL.disjointWith, class_uri(str(dj))))

            for eq in item.get("equivalent_to", []) or []:
                if eq:
                    g.add((c_uri, OWL.equivalentClass, class_uri(str(eq))))

            # Inline property/relation definitions on the class.
            for prop in item.get("suggested_properties", []) or item.get("properties", []) or []:
                if isinstance(prop, dict):
                    self._add_datatype_property(g, ns, prop, domain=c_uri)
            for rel in item.get("suggested_relations", []) or item.get("relations", []) or []:
                if isinstance(rel, dict):
                    self._add_object_property(g, ns, rel)

        # Top-level property / relation lists.
        for prop in proposal.get("properties", []) or []:
            if isinstance(prop, dict) and ("datatype" in prop or prop.get("type") == "datatype"):
                self._add_datatype_property(g, ns, prop)
        for rel in proposal.get("relations", []) or []:
            if isinstance(rel, dict):
                self._add_object_property(g, ns, rel)

        return g

    def _add_datatype_property(
        self,
        g: Graph,
        ns: Namespace,
        prop: dict,
        domain: URIRef | None = None,
    ) -> None:
        name = prop.get("name") or prop.get("label")
        if not name:
            return
        p_uri = ns[_local(name)]
        g.add((p_uri, RDF.type, OWL.DatatypeProperty))
        g.add((p_uri, RDFS.label, Literal(name)))
        if domain is not None:
            g.add((p_uri, RDFS.domain, domain))
        elif prop.get("domain"):
            g.add((p_uri, RDFS.domain, ns[_local(str(prop["domain"]))]))
        datatype = prop.get("datatype", "xsd:string")
        g.add((p_uri, RDFS.range, _XSD_TYPE_MAP.get(datatype, XSD.string)))

    def _add_object_property(self, g: Graph, ns: Namespace, rel: dict) -> None:
        name = rel.get("name") or rel.get("label")
        if not name:
            return
        p_uri = ns[_local(name)]
        g.add((p_uri, RDF.type, OWL.ObjectProperty))
        g.add((p_uri, RDFS.label, Literal(name)))
        if rel.get("domain"):
            g.add((p_uri, RDFS.domain, ns[_local(str(rel["domain"]))]))
        if rel.get("range"):
            g.add((p_uri, RDFS.range, ns[_local(str(rel["range"]))]))
        if rel.get("inverse_name"):
            g.add((p_uri, OWL.inverseOf, ns[_local(str(rel["inverse_name"]))]))

    # ── Reasoning / closure ─────────────────────────────────────────

    def _materialise(self, graph: Graph) -> tuple[Graph, str]:
        """Return a reasoned copy of ``graph`` and the reasoner name used."""
        reasoned = Graph()
        for triple in graph:
            reasoned.add(triple)

        if self.use_owlrl:
            try:
                import owlrl  # type: ignore[import-untyped]

                owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(reasoned)
                return reasoned, "owlrl"
            except ImportError:
                logger.warning("owlrl_unavailable_manual_closure")
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("owlrl_failed_manual_closure", error=str(e))

        self._manual_subclass_closure(reasoned)
        return reasoned, "manual"

    @staticmethod
    def _manual_subclass_closure(graph: Graph) -> None:
        """Compute transitive closure of ``rdfs:subClassOf`` in place."""
        changed = True
        while changed:
            changed = False
            edges = list(graph.triples((None, RDFS.subClassOf, None)))
            for s, _, o in edges:
                for _, _, o2 in graph.triples((o, RDFS.subClassOf, None)):
                    if (s, RDFS.subClassOf, o2) not in graph:
                        graph.add((s, RDFS.subClassOf, o2))
                        changed = True

    # ── Graph introspection helpers ─────────────────────────────────

    @staticmethod
    def _collect_classes(graph: Graph) -> set[URIRef]:
        classes: set[URIRef] = set()
        for s in graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef):
                classes.add(s)
        for s in graph.subjects(RDF.type, RDFS.Class):
            if isinstance(s, URIRef):
                classes.add(s)
        # Anything appearing in a subclass axiom is a class too.
        for s, _, o in graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef):
                classes.add(s)
            if isinstance(o, URIRef) and o != OWL.Thing:
                classes.add(o)
        # Drop OWL/RDF/RDFS built-in classes inferred by the reasoner
        # (owl:Thing, owl:Nothing, rdfs:Resource, …) — only domain classes
        # are of interest.
        return {c for c in classes if not _is_builtin(c)}

    def _transitive_superclasses(
        self,
        graph: Graph,
        classes: set[URIRef],
    ) -> dict[URIRef, set[URIRef]]:
        """Map each class to its (transitive) superclasses, folding in
        ``owl:equivalentClass`` as mutual subsumption.
        """
        # Direct edges including equivalence both ways.
        direct: dict[URIRef, set[URIRef]] = {c: set() for c in classes}
        for s, _, o in graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                direct.setdefault(s, set()).add(o)
        for s, _, o in graph.triples((None, OWL.equivalentClass, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                direct.setdefault(s, set()).add(o)
                direct.setdefault(o, set()).add(s)

        result: dict[URIRef, set[URIRef]] = {}
        for c in direct:
            seen: set[URIRef] = set()
            stack = list(direct.get(c, set()))
            while stack:
                node = stack.pop()
                if node in seen or node == c:
                    continue
                seen.add(node)
                stack.extend(direct.get(node, set()))
            result[c] = seen
        return result

    @staticmethod
    def _disjoint_pairs(graph: Graph) -> set[frozenset[URIRef]]:
        pairs: set[frozenset[URIRef]] = set()
        for s, _, o in graph.triples((None, OWL.disjointWith, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o:
                pairs.add(frozenset((s, o)))
        # owl:AllDisjointClasses members are pairwise disjoint.
        for node in graph.subjects(RDF.type, OWL.AllDisjointClasses):
            members: list[URIRef] = []
            for _, _, members_list in graph.triples((node, OWL.members, None)):
                members.extend(
                    m for m in graph.items(members_list) if isinstance(m, URIRef)
                )
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    pairs.add(frozenset((members[i], members[j])))
        return pairs

    # ── Individual checks ───────────────────────────────────────────

    def _check_unsatisfiable(
        self,
        classes: set[URIRef],
        superclasses: dict[URIRef, set[URIRef]],
        disjoint_pairs: set[frozenset[URIRef]],
    ) -> list[LogicalIssue]:
        issues: list[LogicalIssue] = []
        for c in classes:
            supers = superclasses.get(c, set())
            ancestry = supers | {c}
            for pair in disjoint_pairs:
                a, b = tuple(pair)
                if a in ancestry and b in ancestry and a != c and b != c:
                    issues.append(
                        LogicalIssue(
                            kind=LogicalIssueKind.UNSATISFIABLE_CLASS,
                            severity="error",
                            message=(
                                f"Class '{_label(c)}' is unsatisfiable: it inherits "
                                f"from disjoint classes '{_label(a)}' and '{_label(b)}'."
                            ),
                            affected=[str(c), str(a), str(b)],
                            explanation=(
                                "A class subsumed by two mutually disjoint classes "
                                "can never have instances (it is equivalent to owl:Nothing)."
                            ),
                        )
                    )
                    break
        return issues

    def _check_disjoint_subclass(
        self,
        superclasses: dict[URIRef, set[URIRef]],
        disjoint_pairs: set[frozenset[URIRef]],
    ) -> list[LogicalIssue]:
        issues: list[LogicalIssue] = []
        for pair in disjoint_pairs:
            a, b = tuple(pair)
            if b in superclasses.get(a, set()) or a in superclasses.get(b, set()):
                sub, sup = (a, b) if b in superclasses.get(a, set()) else (b, a)
                issues.append(
                    LogicalIssue(
                        kind=LogicalIssueKind.DISJOINTNESS_VIOLATION,
                        severity="error",
                        message=(
                            f"'{_label(sub)}' is declared disjoint with '{_label(sup)}' "
                            f"yet is also its subclass."
                        ),
                        affected=[str(sub), str(sup)],
                        explanation=(
                            "Disjointness and subsumption between the same two classes "
                            "force the subclass to be unsatisfiable."
                        ),
                    )
                )
        return issues

    def _check_cycles(
        self,
        graph: Graph,
        classes: set[URIRef],
    ) -> list[LogicalIssue]:
        # Direct (non-closed) subclass edges only, so we report the real cycle.
        direct: dict[URIRef, set[URIRef]] = {}
        for s, _, o in graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o:
                direct.setdefault(s, set()).add(o)
        equivalent: set[frozenset[URIRef]] = {
            frozenset((s, o))
            for s, _, o in graph.triples((None, OWL.equivalentClass, None))
            if isinstance(s, URIRef) and isinstance(o, URIRef)
        }

        issues: list[LogicalIssue] = []
        reported: set[frozenset[URIRef]] = set()
        for a, supers in direct.items():
            for b in supers:
                if a in direct.get(b, set()):  # a ⊑ b and b ⊑ a
                    key = frozenset((a, b))
                    if key in reported or key in equivalent:
                        continue
                    reported.add(key)
                    issues.append(
                        LogicalIssue(
                            kind=LogicalIssueKind.SUBCLASS_CYCLE,
                            severity="error",
                            message=(
                                f"Subclass cycle between '{_label(a)}' and '{_label(b)}'."
                            ),
                            affected=[str(a), str(b)],
                            explanation=(
                                "Mutual subclass axioms force the classes to be "
                                "equivalent; if unintended this is a modelling error. "
                                "Declare owl:equivalentClass explicitly or break the cycle."
                            ),
                        )
                    )
        return issues

    def _check_domain_range(
        self,
        graph: Graph,
        disjoint_pairs: set[frozenset[URIRef]],
    ) -> list[LogicalIssue]:
        issues: list[LogicalIssue] = []
        properties: set[URIRef] = set()
        for ptype in (OWL.ObjectProperty, OWL.DatatypeProperty, RDF.Property):
            for s in graph.subjects(RDF.type, ptype):
                if isinstance(s, URIRef):
                    properties.add(s)

        for p in properties:
            for axis, label in ((RDFS.domain, "domain"), (RDFS.range, "range")):
                decls = {
                    o for o in graph.objects(p, axis) if isinstance(o, URIRef)
                }
                for pair in disjoint_pairs:
                    a, b = tuple(pair)
                    if a in decls and b in decls:
                        issues.append(
                            LogicalIssue(
                                kind=LogicalIssueKind.DOMAIN_RANGE_CONFLICT,
                                severity="error",
                                message=(
                                    f"Property '{_label(p)}' has disjoint {label} "
                                    f"classes '{_label(a)}' and '{_label(b)}'."
                                ),
                                affected=[str(p), str(a), str(b)],
                                explanation=(
                                    f"Multiple {label} declarations are intersected; "
                                    f"disjoint {label}s make the property unsatisfiable."
                                ),
                            )
                        )
                        break
        return issues


def _local(name: str) -> str:
    """Turn a label into a URI-safe local name (PascalCase-ish)."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in name).strip()
    if not cleaned:
        return "Unnamed"
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0]
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


_BUILTIN_PREFIXES = (
    str(OWL),
    str(RDF),
    str(RDFS),
    "http://www.w3.org/2001/XMLSchema#",
)


def _is_builtin(uri: URIRef) -> bool:
    """True if ``uri`` belongs to an OWL/RDF/RDFS/XSD built-in namespace."""
    return str(uri).startswith(_BUILTIN_PREFIXES)


def _local_from_uri(uri: URIRef) -> str:
    text = str(uri)
    for sep in ("#", "/"):
        if sep in text:
            text = text.rsplit(sep, 1)[-1]
    return text


def _label(uri: URIRef) -> str:
    return _local_from_uri(uri)

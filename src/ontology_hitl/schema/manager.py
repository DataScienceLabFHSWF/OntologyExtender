"""C1.3.1 — OntologySchemaManager: add/remove classes with validation.

Implementation Guide
--------------------
This module applies accepted review decisions to a seed ontology and
produces an extended OWL file with new classes, properties, and relations.

All methods are implemented with:
  1. ``export_owl()``          — Build RDF graph with rdflib and serialize
  2. ``export_updated_cqs()``  — Generate CQs for new classes

Dependencies:
  - ``rdflib``       for Graph manipulation and OWL serialization
  - ``json``, ``pathlib`` for data I/O

Reference: KGB ``FusekiOntologyService`` in ``src/kgbuilder/storage/ontology.py``
for SPARQL patterns, and KGB ``Planning/03_INTERFACES.md §1.2`` for the
``OntologyClassDef`` / ``OntologyRelationDef`` data models.
"""

from __future__ import annotations

import json
from pathlib import Path

import rdflib
import structlog

from ontology_hitl.core.exceptions import SchemaUpdateError
from ontology_hitl.core.models import ProposedClass

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# RDF namespace URIs — used by export_owl
# ---------------------------------------------------------------------------

# These are the standard namespace strings that rdflib.Namespace() should wrap.
# Example usage in export_owl:
#   from rdflib import Graph, Namespace, Literal, RDF, RDFS, OWL, XSD
#   EX = Namespace("http://purl.org/2024/planning-ontology#")
_ONTOLOGY_BASE = "http://purl.org/2024/planning-ontology#"
_XSD_TYPE_MAP = {
    "xsd:string": "http://www.w3.org/2001/XMLSchema#string",
    "xsd:integer": "http://www.w3.org/2001/XMLSchema#integer",
    "xsd:float": "http://www.w3.org/2001/XMLSchema#float",
    "xsd:date": "http://www.w3.org/2001/XMLSchema#date",
    "xsd:boolean": "http://www.w3.org/2001/XMLSchema#boolean",
    "xsd:dateTime": "http://www.w3.org/2001/XMLSchema#dateTime",
}


class OntologySchemaManager:
    """Manage ontology schema: add/remove classes, export OWL.

    Operates on a seed ontology and applies accepted proposals
    to produce an extended version.

    Parameters
    ----------
    seed_ontology_path:
        Path to the seed ontology OWL file (e.g. ``plan-ontology-v1.0.owl``).
    """

    def __init__(self, seed_ontology_path: Path | str) -> None:
        self.seed_ontology_path = Path(seed_ontology_path)
        self._accepted_classes: list[ProposedClass] = []

    # ── Decision loading (complete) ─────────────────────────────────

    def apply_decisions(
        self,
        proposals_path: Path | str,
        decisions_path: Path | str,
    ) -> list[ProposedClass]:
        """Load proposals + decisions, return accepted ProposedClass list.

        Args:
            proposals_path: JSON file with proposals.
            decisions_path: JSON file with review decisions.

        Returns:
            List of accepted ProposedClass objects.
        """
        with open(proposals_path) as f:
            proposals = json.load(f)
        with open(decisions_path) as f:
            decisions = json.load(f)

        decision_map = {d["proposal_id"]: d for d in decisions}

        accepted: list[ProposedClass] = []
        for prop in proposals:
            pid = prop.get("id", "")
            dec = decision_map.get(pid, {})
            if dec.get("decision") == "accept":
                accepted.append(
                    ProposedClass(
                        id=pid,
                        label=prop["label"],
                        definition=prop.get("definition", ""),
                        parent_uri=prop.get("parent_uri", ""),
                        parent_label=prop.get("parent_label", ""),
                        examples=prop.get("examples", []),
                        frequency=prop.get("frequency", 0),
                        confidence=prop.get("confidence", 0.0),
                    )
                )

        self._accepted_classes = accepted
        logger.info("decisions_applied", accepted=len(accepted), total=len(proposals))
        return accepted

    # ── OWL export ───────────────────────────────────────────

    def export_owl(self, output_path: Path | str) -> None:
        """Export extended ontology as OWL/XML."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "export_owl",
            path=str(output_path),
            classes=len(self._accepted_classes),
        )
        try:
            from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS, OWL, XSD
        except ImportError as e:
            logger.error("rdflib_import_failed", error=str(e))
            raise SchemaUpdateError("rdflib is required for OWL export")
        g = Graph()
        try:
            g.parse(str(self.seed_ontology_path))
        except Exception as e:
            logger.error("seed_ontology_parse_failed", error=str(e))
            raise SchemaUpdateError("Failed to parse seed ontology")
        EX = Namespace(_ONTOLOGY_BASE)
        g.bind("ex", EX)
        for cls in self._accepted_classes:
            class_uri = EX[cls.label]
            g.add((class_uri, RDF.type, OWL.Class))
            g.add((class_uri, RDFS.label, Literal(cls.label)))
            g.add((class_uri, RDFS.comment, Literal(cls.definition)))
            parent = URIRef(cls.parent_uri) if cls.parent_uri else OWL.Thing
            g.add((class_uri, RDFS.subClassOf, parent))
            for prop in getattr(cls, 'suggested_properties', []):
                prop_uri = EX[prop.name]
                g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
                g.add((prop_uri, RDFS.domain, class_uri))
                xsd_uri = URIRef(_XSD_TYPE_MAP.get(prop.datatype, _XSD_TYPE_MAP["xsd:string"]))
                g.add((prop_uri, RDFS.range, xsd_uri))
                g.add((prop_uri, RDFS.label, Literal(prop.name)))
                g.add((prop_uri, RDFS.comment, Literal(prop.description)))
            for rel in getattr(cls, 'suggested_relations', []):
                rel_uri = EX[rel.name]
                g.add((rel_uri, RDF.type, OWL.ObjectProperty))
                g.add((rel_uri, RDFS.domain, EX[rel.domain]))
                g.add((rel_uri, RDFS.range, EX[rel.range]))
                g.add((rel_uri, RDFS.label, Literal(rel.name)))
                g.add((rel_uri, RDFS.comment, Literal(rel.description)))
                if getattr(rel, 'inverse_name', None):
                    inv_uri = EX[rel.inverse_name]
                    g.add((rel_uri, OWL.inverseOf, inv_uri))
        g.serialize(str(output_path), format="xml")
        logger.info("owl_exported", path=str(output_path), classes=len(self._accepted_classes))

    # ── CQ export ────────────────────────────────────────────

    def export_updated_cqs(self, output_path: Path | str) -> None:
        """Export updated competency questions JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("export_cqs", path=str(output_path))
        cqs = []
        for cls in self._accepted_classes:
            cqs.append({
                "id": f"cq_{cls.id}_1",
                "class": cls.label,
                "question": f"What properties does a {cls.label} have?",
                "expected_answer_type": "list",
            })
            cqs.append({
                "id": f"cq_{cls.id}_2",
                "class": cls.label,
                "question": f"Which {cls.parent_label} instances are also {cls.label}?",
                "expected_answer_type": "list",
            })
            for rel in getattr(cls, 'suggested_relations', []):
                cqs.append({
                    "id": f"cq_{cls.id}_{rel.name}",
                    "class": cls.label,
                    "question": f"What {rel.range} does {cls.label} {rel.name}?",
                    "expected_answer_type": "list",
                })
        if output_path.exists():
            try:
                with open(output_path) as f:
                    existing = json.load(f)
                cqs = existing + cqs
            except Exception:
                pass
        with open(output_path, "w") as f:
            json.dump(cqs, f, indent=2)
        logger.info("export_cqs", path=str(output_path), count=len(cqs))

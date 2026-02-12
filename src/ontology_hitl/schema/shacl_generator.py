"""C1.3.2 — SHACLGenerator: generate SHACL shapes for proposed classes.

Implementation Guide
--------------------
This module generates SHACL (Shapes Constraint Language) NodeShape
definitions that enforce property requirements, cardinality, and
datatype restrictions for proposed ontology classes.

All methods are implemented with:
  1. ``generate_shape()``         — Generates shape with property and relation constraints
  2. ``generate_all_shapes()``    — Batch generation with shared prefixes
  3. ``validate_with_pyshacl()``  — Validate data graph against shapes

Dependencies:
  - ``rdflib``    for Graph building (in ``validate_with_pyshacl``)
  - ``pyshacl``   for SHACL validation (in ``validate_with_pyshacl``)

Reference: KGB ``SHACLValidator`` in ``src/kgbuilder/validation/validators.py``
for the pyshacl integration pattern.
"""

from __future__ import annotations

from typing import Any

import structlog

from ontology_hitl.core.models import ProposedClass

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SHACL prefix header — reused across all shapes
# ---------------------------------------------------------------------------

_SHACL_PREFIXES = """\
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix ex:   <http://purl.org/2024/planning-ontology#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""

# Map our datatype strings to XSD URIs
_XSD_MAP = {
    "xsd:string": "xsd:string",
    "xsd:integer": "xsd:integer",
    "xsd:float": "xsd:float",
    "xsd:date": "xsd:date",
    "xsd:boolean": "xsd:boolean",
    "xsd:dateTime": "xsd:dateTime",
}

# Map cardinality strings to (minCount, maxCount) tuples
_CARDINALITY_MAP: dict[str, tuple[int | None, int | None]] = {
    "1..1": (1, 1),
    "0..1": (None, 1),
    "1..*": (1, None),
    "0..*": (None, None),
}


class SHACLGenerator:
    """Generate SHACL NodeShape definitions for ontology classes.

    Produces constraint shapes that enforce property requirements,
    cardinality, and datatype restrictions.
    """

    # ── Single shape (enhance with relations) ───────────────────────

    def generate_shape(self, proposed_class: ProposedClass) -> str:
        """Generate a SHACL shape definition for a proposed class."""
        logger.info("generating_shacl_shape", class_label=proposed_class.label)

        lines = [
            f"ex:{proposed_class.label}Shape",
            f"    a sh:NodeShape ;",
            f"    sh:targetClass ex:{proposed_class.label} ;",
        ]

        # DatatypeProperty constraints
        for prop in proposed_class.suggested_properties:
            lines.append(f"    sh:property [")
            lines.append(f"        sh:path ex:{prop.name} ;")
            if prop.required:
                lines.append(f"        sh:minCount 1 ;")
            if prop.max_count is not None:
                lines.append(f"        sh:maxCount {prop.max_count} ;")
            datatype = _XSD_MAP.get(prop.datatype, "xsd:string")
            lines.append(f"        sh:datatype {datatype} ;")
            lines.append(f'        sh:description "{prop.description}" ;')
            lines.append(f"    ] ;")

        for rel in getattr(proposed_class, 'suggested_relations', []):
            lines.append(f"    sh:property [")
            lines.append(f"        sh:path ex:{rel.name} ;")
            lines.append(f"        sh:nodeKind sh:IRI ;")
            lines.append(f"        sh:class ex:{rel.range} ;")
            min_c, max_c = _CARDINALITY_MAP.get(getattr(rel, 'cardinality', '0..*'), (None, None))
            if min_c is not None:
                lines.append(f"        sh:minCount {min_c} ;")
            if max_c is not None:
                lines.append(f"        sh:maxCount {max_c} ;")
            lines.append(f'        sh:description "{getattr(rel, "description", "")}" ;')
            lines.append(f"    ] ;")
        shape_turtle = "\n".join(lines) + "\n    .\n"
        return shape_turtle

    # ── Batch generation ─────────────────────────────────────

    def generate_all_shapes(self, classes: list[ProposedClass]) -> str:
        """Generate SHACL shapes for all proposed classes."""
        parts = [_SHACL_PREFIXES, ""]
        for cls in classes:
            parts.append(self.generate_shape(cls))
            parts.append("")
        return "\n".join(parts)

    # ── Validation with pyshacl ──────────────────────────────

    def validate_with_pyshacl(
        self,
        data_turtle: str,
        shapes_turtle: str,
    ) -> tuple[bool, str, str]:
        """Validate a data graph against SHACL shapes using pyshacl."""
        try:
            from rdflib import Graph
            import pyshacl
            data_graph = Graph().parse(data=data_turtle, format="turtle")
            shapes_graph = Graph().parse(data=shapes_turtle, format="turtle")
            conforms, results_graph, results_text = pyshacl.validate(
                data_graph,
                shacl_graph=shapes_graph,
                inference="rdfs",
                abort_on_first=False,
            )
            return (conforms, results_graph.serialize(format="turtle"), results_text)
        except Exception as e:
            logger.warning("pyshacl_validation_failed", error=str(e))
            return (False, "", str(e))

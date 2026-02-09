"""YARRRML mapping generator for ontology classes.

Generates YARRRML (https://rml.io/yarrrml/) declarative mapping rules
that describe how extracted data maps to the extended ontology.
The output YAML can be converted to RML via the yarrrml-parser and then
executed by any RML processor (RMLMapper, RMLStreamer, Morph-KGC, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from ontology_hitl.core.models import ProposedClass, PropertyDef, RelationDef

logger = structlog.get_logger(__name__)

# Default namespace prefixes used in generated mappings
DEFAULT_PREFIXES: dict[str, str] = {
    "ex": "http://example.org/ontology#",
    "schema": "http://schema.org/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "planning": "http://purl.org/2024/planning-ontology#",
}


class YARRRMLGenerator:
    """Generate YARRRML mapping files from accepted ontology classes.

    For each accepted class the generator produces a YARRRML mapping that
    describes:
    - the data source (JSON extraction checkpoint),
    - the subject IRI template,
    - predicate-object pairs for every property / relation, and
    - the rdf:type assertion linking instances to the new class.

    Example output (Turtle-serialised via an RML processor) for a class
    ``Facility``:

    .. code-block:: yaml

        prefixes:
          ex: http://example.org/ontology#
          ...
        mappings:
          Facility:
            sources:
              - [data/extraction.json~jsonpath, "$.entities[?(@.entity_type=='Facility')]"]
            s: ex:facility/$(id)
            po:
              - [a, ex:Facility]
              - [rdfs:label, $(label)]
    """

    def __init__(
        self,
        base_namespace: str = "http://example.org/ontology#",
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self.base_namespace = base_namespace
        self.prefixes = prefixes or dict(DEFAULT_PREFIXES)
        # Keep "ex" in sync with the user-supplied namespace
        self.prefixes["ex"] = base_namespace

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        accepted_classes: list[ProposedClass],
        source_path: str = "data/extraction.json",
        reference_formulation: str = "jsonpath",
    ) -> dict[str, Any]:
        """Build a complete YARRRML document for a set of accepted classes.

        Args:
            accepted_classes: Ontology classes that passed expert review.
            source_path: Path (or URL) to the JSON data source.
            reference_formulation: jsonpath | xpath | csv.

        Returns:
            A Python dict that, when serialised with ``yaml.dump``, produces
            a valid YARRRML document.
        """
        logger.info("yarrrml_generate_start", classes=len(accepted_classes))

        doc: dict[str, Any] = {
            "prefixes": dict(self.prefixes),
            "mappings": {},
        }

        for cls in accepted_classes:
            mapping = self._class_to_mapping(cls, source_path, reference_formulation)
            doc["mappings"][cls.label] = mapping

        logger.info("yarrrml_generate_done", mappings=len(doc["mappings"]))
        return doc

    def write(
        self,
        yarrrml_doc: dict[str, Any],
        output_path: Path | str,
    ) -> Path:
        """Serialise a YARRRML document to a ``.yml`` file.

        Args:
            yarrrml_doc: Output of :meth:`generate`.
            output_path: Where to write the YAML file.

        Returns:
            Resolved output path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as fh:
            yaml.dump(yarrrml_doc, fh, default_flow_style=False, sort_keys=False)

        logger.info("yarrrml_written", path=str(output_path))
        return output_path

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _class_to_mapping(
        self,
        cls: ProposedClass,
        source_path: str,
        ref_form: str,
    ) -> dict[str, Any]:
        """Convert a single ProposedClass to a YARRRML mapping block."""
        entity_type = cls.label
        iterator = f"$.entities[?(@.entity_type=='{entity_type}')]"

        # Source shorthand: [path~refFormulation, iterator]
        source = [f"{source_path}~{ref_form}", iterator]

        po: list[list[str]] = [
            ["a", f"ex:{entity_type}"],
            ["rdfs:label", "$(label)"],
        ]

        # Add data properties
        for prop in cls.suggested_properties:
            po.append(self._property_to_po(prop))

        # Add object properties (relations)
        for rel in cls.suggested_relations:
            po.append(self._relation_to_po(rel))

        return {
            "sources": [source],
            "s": f"ex:{entity_type.lower()}/$(id)",
            "po": po,
        }

    @staticmethod
    def _property_to_po(prop: PropertyDef) -> list[str]:
        """Map a PropertyDef to a YARRRML predicate-object pair."""
        predicate = f"ex:{prop.name}"
        obj = f"$({prop.name})"
        if prop.datatype and prop.datatype != "xsd:string":
            return [predicate, f"{obj}~{prop.datatype}"]
        return [predicate, obj]

    @staticmethod
    def _relation_to_po(rel: RelationDef) -> list[str]:
        """Map a RelationDef to a YARRRML predicate-object pair (IRI)."""
        predicate = f"ex:{rel.name}"
        # Link to the related entity by IRI template
        target = f"ex:{rel.range.lower()}/$(related_{rel.name}_id)~iri"
        return [predicate, target]

"""C1.3.2 — SHACLGenerator: generate SHACL shapes for proposed classes."""

from __future__ import annotations

import structlog

from ontology_hitl.core.models import ProposedClass

logger = structlog.get_logger(__name__)


class SHACLGenerator:
    """Generate SHACL NodeShape definitions for ontology classes.

    Produces constraint shapes that enforce property requirements,
    cardinality, and datatype restrictions.
    """

    def generate_shape(self, proposed_class: ProposedClass) -> str:
        """Generate a SHACL shape definition for a proposed class.

        Args:
            proposed_class: The class to generate constraints for.

        Returns:
            SHACL shape as Turtle string.

        TODO: Implement full SHACL shape generation.
        """
        logger.info("generating_shacl_shape", class_label=proposed_class.label)

        # Placeholder — will generate proper SHACL Turtle
        lines = [
            f"ex:{proposed_class.label}Shape",
            f"    a sh:NodeShape ;",
            f'    sh:targetClass ex:{proposed_class.label} ;',
        ]

        for prop in proposed_class.suggested_properties:
            lines.append(f"    sh:property [")
            lines.append(f'        sh:path ex:{prop.name} ;')
            if prop.required:
                lines.append(f"        sh:minCount 1 ;")
            if prop.max_count is not None:
                lines.append(f"        sh:maxCount {prop.max_count} ;")
            lines.append(f'        sh:datatype {prop.datatype} ;')
            lines.append(f"    ] ;")

        shape_turtle = "\n".join(lines) + "\n    .\n"
        return shape_turtle

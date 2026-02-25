"""OntologyContext — shared TBox knowledge loaded once at startup.

Ported from GraphQAAgent.  Provides a structured summary of the ontology
(classes, hierarchy, properties, domain/range constraints) that every
retrieval component can use:
- **CypherRetriever**: injects class/property catalog into Cypher prompt
- **EntityLinker**: maps detected types to ontology classes
- **GraphRetriever**: knows which relations to follow for a given entity type
- **HybridRetriever**: adaptive weights informed by ontology richness
- **AgenticGraphRAG**: full schema awareness for tool-calling agent

The ontology is loaded from Fuseki (SPARQL) and cached in memory.
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from typing import Any

from ontology_hitl.connectors.fuseki import FusekiConnector

logger = structlog.get_logger(__name__)


@dataclass
class TBoxClass:
    """A class from the TBox with its position in the hierarchy."""

    name: str
    uri: str
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    properties_as_domain: list[str] = field(default_factory=list)
    properties_as_range: list[str] = field(default_factory=list)


@dataclass
class TBoxProperty:
    """An object or datatype property from the TBox."""

    name: str
    uri: str
    prop_type: str  # "object" or "data"
    domain: str  # Class local name
    range: str  # Class or XSD type local name


class OntologyContext:
    """Shared ontology (TBox) knowledge loaded once from Fuseki.

    Call ``await load()`` at startup. Then use the cached data:
    - ``classes``: dict of class name → TBoxClass
    - ``properties``: dict of property name → TBoxProperty
    - ``schema_summary``: pre-formatted text for LLM prompts
    """

    def __init__(self, fuseki: FusekiConnector) -> None:
        self._fuseki = fuseki
        self.classes: dict[str, TBoxClass] = {}
        self.properties: dict[str, TBoxProperty] = {}
        self.schema_summary: str = ""
        self.neo4j_to_ontology: dict[str, str] = {}
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        """Load the full ontology from Fuseki and build cached structures."""
        try:
            await self._load_classes()
            await self._load_properties()
            self._build_hierarchy()
            self._build_neo4j_mapping()
            self.schema_summary = self._build_schema_summary()
            self._loaded = True
            logger.info(
                "ontology_context.loaded",
                classes=len(self.classes),
                properties=len(self.properties),
                summary_chars=len(self.schema_summary),
            )
        except Exception as exc:
            logger.warning("ontology_context.load_failed", error=str(exc))
            self.schema_summary = self._fallback_summary()
            self._loaded = True

    async def _load_classes(self) -> None:
        rows = await self._fuseki.query("""
        SELECT ?cls ?parent WHERE {
          ?cls a owl:Class .
          OPTIONAL { ?cls rdfs:subClassOf ?parent . ?parent a owl:Class }
        }
        """)
        for row in rows:
            uri = row.get("cls", "")
            name = self._local_name(uri)
            parent_uri = row.get("parent", "")
            parent_name = self._local_name(parent_uri) if parent_uri else None

            if name not in self.classes:
                self.classes[name] = TBoxClass(name=name, uri=uri, parent=parent_name)
            elif parent_name:
                self.classes[name].parent = parent_name

    async def _load_properties(self) -> None:
        rows = await self._fuseki.query("""
        SELECT ?prop ?type ?domain ?range WHERE {
          {
            ?prop a owl:ObjectProperty .
            BIND("object" AS ?type)
          } UNION {
            ?prop a owl:DatatypeProperty .
            BIND("data" AS ?type)
          }
          OPTIONAL { ?prop rdfs:domain ?domain }
          OPTIONAL { ?prop rdfs:range ?range }
        }
        """)
        for row in rows:
            uri = row.get("prop", "")
            name = self._local_name(uri)
            prop_type = row.get("type", "object")
            domain = self._local_name(row.get("domain", ""))
            range_ = self._local_name(row.get("range", ""))

            self.properties[name] = TBoxProperty(
                name=name,
                uri=uri,
                prop_type=prop_type,
                domain=domain,
                range=range_,
            )

    def _build_hierarchy(self) -> None:
        for cls in self.classes.values():
            if cls.parent and cls.parent in self.classes:
                parent = self.classes[cls.parent]
                if cls.name not in parent.children:
                    parent.children.append(cls.name)

        for prop in self.properties.values():
            if prop.domain in self.classes:
                self.classes[prop.domain].properties_as_domain.append(prop.name)
            if prop.range in self.classes:
                self.classes[prop.range].properties_as_range.append(prop.name)

    def _build_neo4j_mapping(self) -> None:
        for name in self.classes:
            self.neo4j_to_ontology[name] = name

    def _build_schema_summary(self) -> str:
        lines = ["ONTOLOGY SCHEMA (TBox):"]
        lines.append("")

        lines.append("Classes (with hierarchy):")
        roots = [c for c in self.classes.values() if c.parent is None]
        for root in sorted(roots, key=lambda c: c.name):
            self._render_class_tree(root, lines, indent=1)

        lines.append("")

        lines.append("Properties (domain → range):")
        by_domain: dict[str, list[TBoxProperty]] = {}
        for prop in self.properties.values():
            by_domain.setdefault(prop.domain, []).append(prop)

        for domain in sorted(by_domain):
            props = by_domain[domain]
            for p in sorted(props, key=lambda x: x.name):
                arrow = "→" if p.prop_type == "object" else "⇒"
                lines.append(f"  {p.domain}.{p.name} {arrow} {p.range}")

        return "\n".join(lines)

    def _render_class_tree(
        self,
        cls: TBoxClass,
        lines: list[str],
        indent: int,
    ) -> None:
        prefix = "  " * indent
        props = ", ".join(cls.properties_as_domain[:5]) if cls.properties_as_domain else ""
        suffix = f" [{props}]" if props else ""
        lines.append(f"{prefix}- {cls.name}{suffix}")
        for child_name in sorted(cls.children):
            if child_name in self.classes:
                self._render_class_tree(self.classes[child_name], lines, indent + 1)

    def _fallback_summary(self) -> str:
        return "ONTOLOGY SCHEMA (TBox): no ontology information available."

    def get_relations_for_type(self, entity_type: str) -> list[str]:
        onto_type = self.neo4j_to_ontology.get(entity_type, entity_type)
        cls = self.classes.get(onto_type)
        if not cls:
            return []
        return cls.properties_as_domain + cls.properties_as_range

    def get_subclass_names(self, class_name: str) -> list[str]:
        cls = self.classes.get(class_name)
        if not cls:
            return []
        result = []
        for child in cls.children:
            result.append(child)
            result.extend(self.get_subclass_names(child))
        return result

    def get_related_types(self, class_name: str) -> list[str]:
        cls = self.classes.get(class_name)
        if not cls:
            return []
        related: set[str] = set()
        for prop_name in cls.properties_as_domain:
            prop = self.properties.get(prop_name)
            if prop and prop.range in self.classes:
                related.add(prop.range)
        for prop_name in cls.properties_as_range:
            prop = self.properties.get(prop_name)
            if prop and prop.domain in self.classes:
                related.add(prop.domain)
        return list(related)

    @staticmethod
    def _local_name(uri: str) -> str:
        if not uri:
            return ""
        if "#" in uri:
            return uri.split("#")[-1]
        return uri.split("/")[-1]

"""Export ontology from Fuseki to structured JSON format.

This exporter queries a Fuseki RDF triple store and produces a JSON
document with classes, attributes, and relations matching the format:

    {
      "id": "ontology-id",
      "name": "Ontology Name",
      "version": "1.0.0",
      "classes": [...],
      "relations": [...]
    }

Usage:
    exporter = FusekiJsonExporter(
        fuseki_url="http://localhost:3030",
        dataset="kgbuilder"
    )
    ontology_json = await exporter.export()
    exporter.save(ontology_json, "ontology.json")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class FusekiJsonExporter:
    """Export ontology from Fuseki to structured JSON format."""

    def __init__(
        self,
        fuseki_url: str = "http://localhost:3030",
        dataset: str = "kgbuilder",
        ontology_id: str = "ontology-export",
        ontology_name: str = "Exported Ontology",
        version: str = "1.0.0",
    ) -> None:
        """Initialize the exporter.

        Args:
            fuseki_url: Base URL of Fuseki server
            dataset: Fuseki dataset name
            ontology_id: Identifier for the exported ontology
            ontology_name: Display name for the ontology
            version: Version string for the ontology
        """
        self.fuseki_url = fuseki_url.rstrip("/")
        self.dataset = dataset
        self.ontology_id = ontology_id
        self.ontology_name = ontology_name
        self.version = version
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Connect to Fuseki."""
        self._client = httpx.AsyncClient(timeout=30.0)
        logger.info("fuseki_exporter.connected", url=self.fuseki_url)

    async def close(self) -> None:
        """Close the connection."""
        if self._client:
            await self._client.aclose()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def export(self) -> dict[str, Any]:
        """Export ontology from Fuseki to JSON.

        Returns:
            Dictionary with keys: id, name, version, classes, relations
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() or use as async context manager.")

        logger.info("fuseki_exporter.export_start", dataset=self.dataset)

        # Fetch classes and attributes
        classes = await self._fetch_classes()
        logger.info("fuseki_exporter.classes_fetched", count=len(classes))

        # Fetch relations
        relations = await self._fetch_relations()
        logger.info("fuseki_exporter.relations_fetched", count=len(relations))

        result = {
            "id": self.ontology_id,
            "name": self.ontology_name,
            "version": self.version,
            "classes": classes,
            "relations": relations,
        }

        logger.info("fuseki_exporter.export_complete", classes=len(classes), relations=len(relations))
        return result

    async def _fetch_classes(self) -> list[dict[str, Any]]:
        """Fetch all classes and their attributes from Fuseki."""
        # Query for classes
        classes_sparql = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?class ?label ?description ?parent
WHERE {
    ?class a owl:Class .
    OPTIONAL { ?class rdfs:label ?label . }
    OPTIONAL { ?class rdfs:comment ?description . }
    OPTIONAL { ?class rdfs:subClassOf ?parent . FILTER(?parent != owl:Thing) }
}
ORDER BY ?label
        """

        class_results = await self._query_sparql(classes_sparql)
        if not class_results:
            logger.warning("no_classes_found")
            return []

        classes = {}
        for row in class_results:
            class_uri = row.get("class", "")
            if not class_uri:
                continue

            if class_uri not in classes:
                classes[class_uri] = {
                    "id": self._uri_to_id(class_uri),
                    "name": row.get("label", self._uri_to_label(class_uri)),
                    "module": "Core",  # Default module
                    "description": row.get("description", ""),
                    "parentClassId": self._uri_to_id(row.get("parent", "")) if row.get("parent") else None,
                    "exampleInstanceId": None,
                    "attributes": [],
                }

        # Query for datatype properties (attributes) on each class
        for class_uri in classes.keys():
            attributes = await self._fetch_class_attributes(class_uri)
            classes[class_uri]["attributes"] = attributes

        return list(classes.values())

    async def _fetch_class_attributes(self, class_uri: str) -> list[dict[str, Any]]:
        """Fetch datatype properties (attributes) for a class."""
        attr_sparql = f"""
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?prop ?propLabel ?description ?range ?cardinality
WHERE {{
    ?prop a owl:DatatypeProperty .
    ?prop rdfs:domain <{class_uri}> .
    OPTIONAL {{ ?prop rdfs:label ?propLabel . }}
    OPTIONAL {{ ?prop rdfs:comment ?description . }}
    OPTIONAL {{ ?prop rdfs:range ?range . }}
    OPTIONAL {{ ?prop owl:cardinality ?cardinality . }}
}}
ORDER BY ?propLabel
        """

        attr_results = await self._query_sparql(attr_sparql)
        attributes = []

        for row in attr_results:
            prop_uri = row.get("prop", "")
            if not prop_uri:
                continue

            range_uri = row.get("range", "xsd:string")
            data_type = self._range_to_datatype(range_uri)
            cardinality = row.get("cardinality", "")

            attributes.append(
                {
                    "id": self._uri_to_id(prop_uri),
                    "name": row.get("propLabel", self._uri_to_label(prop_uri)),
                    "dataType": data_type,
                    "required": cardinality == "1",
                    "description": row.get("description", ""),
                    "sourceDataType": range_uri,
                    "cardinality": cardinality or "0..1",
                    "exampleValue": None,
                }
            )

        return attributes

    async def _fetch_relations(self) -> list[dict[str, Any]]:
        """Fetch all object properties (relations) from Fuseki."""
        relations_sparql = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?prop ?label ?description ?domain ?range ?inverse
WHERE {
    ?prop a owl:ObjectProperty .
    OPTIONAL { ?prop rdfs:label ?label . }
    OPTIONAL { ?prop rdfs:comment ?description . }
    OPTIONAL { ?prop rdfs:domain ?domain . }
    OPTIONAL { ?prop rdfs:range ?range . }
    OPTIONAL { ?prop owl:inverseOf ?inverse . }
}
ORDER BY ?label
        """

        rel_results = await self._query_sparql(relations_sparql)
        relations = []

        for row in rel_results:
            prop_uri = row.get("prop", "")
            if not prop_uri:
                continue

            domain_uri = row.get("domain", "")
            range_uri = row.get("range", "")

            relations.append(
                {
                    "id": self._uri_to_id(prop_uri),
                    "name": row.get("label", self._uri_to_label(prop_uri)),
                    "domainClassId": self._uri_to_id(domain_uri) if domain_uri else None,
                    "rangeClassId": self._uri_to_id(range_uri) if range_uri else None,
                    "description": row.get("description", ""),
                    "inverseName": self._uri_to_label(row.get("inverse", "")),
                    "cardinality": "0..n",  # Default; could be refined
                    "exampleTriple": None,
                }
            )

        return relations

    async def _query_sparql(self, sparql: str) -> list[dict[str, str]]:
        """Execute a SPARQL query against Fuseki.

        Args:
            sparql: SPARQL query string

        Returns:
            List of result bindings (dictionaries)
        """
        if not self._client:
            return []

        # Add prefixes if not already present
        if not sparql.strip().upper().startswith("PREFIX"):
            sparql = self._default_prefixes() + "\n" + sparql

        try:
            resp = await self._client.post(
                f"{self.fuseki_url}/{self.dataset}/sparql",
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
            data = resp.json()
            bindings = data.get("results", {}).get("bindings", [])

            return [
                {k: v.get("value", "") for k, v in binding.items()}
                for binding in bindings
            ]
        except Exception as exc:
            logger.warning("sparql_query_failed", error=str(exc))
            return []

    @staticmethod
    def _default_prefixes() -> str:
        """Return default SPARQL prefixes."""
        return """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        """

    @staticmethod
    def _uri_to_id(uri: str) -> str:
        """Convert a URI to a compact ID.

        Examples:
            "https://example.org/ontology#Facility" → "cls:Facility"
            "https://example.org/ontology#hasSystem" → "rel:hasSystem"
        """
        if not uri:
            return ""

        # Extract local name (after # or last /)
        if "#" in uri:
            local = uri.split("#")[-1]
        else:
            local = uri.split("/")[-1]

        # Guess prefix based on naming convention
        # (Class names are typically PascalCase, property/relation names are camelCase)
        if local and local[0].isupper():
            return f"cls:{local}"
        else:
            return f"rel:{local}"

    @staticmethod
    def _uri_to_label(uri: str) -> str:
        """Convert a URI to a human-readable label.

        Examples:
            "https://example.org/ontology#Facility" → "Facility"
            "https://example.org/ontology#hasSystem" → "hasSystem"
        """
        if not uri:
            return ""

        # Extract local name
        if "#" in uri:
            local = uri.split("#")[-1]
        else:
            local = uri.split("/")[-1]

        # Convert camelCase to space-separated
        import re
        label = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", local)
        return label.lower()

    @staticmethod
    def _range_to_datatype(range_uri: str) -> str:
        """Convert RDF range URI to JSON dataType.

        Examples:
            "http://www.w3.org/2001/XMLSchema#string" → "string"
            "http://www.w3.org/2001/XMLSchema#integer" → "integer"
        """
        if not range_uri:
            return "string"

        # Map XSD types to JSON types
        xsd_map = {
            "xsd:string": "string",
            "xsd:integer": "integer",
            "xsd:int": "integer",
            "xsd:float": "float",
            "xsd:double": "float",
            "xsd:boolean": "boolean",
            "xsd:date": "date",
            "xsd:dateTime": "datetime",
        }

        # Check for exact match
        for key, value in xsd_map.items():
            if key in range_uri or range_uri.endswith(key.split(":")[-1]):
                return value

        return "string"  # Default

    def save(self, ontology_data: dict[str, Any], filepath: str | Path) -> Path:
        """Save exported ontology to a JSON file.

        Args:
            ontology_data: Ontology dictionary (from export())
            filepath: Output file path

        Returns:
            Path to the saved file
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(ontology_data, f, indent=2)

        logger.info("ontology_saved", path=str(filepath))
        return filepath


async def export_ontology_from_fuseki(
    output_path: str | Path = "ontology.json",
    fuseki_url: str = "http://localhost:3030",
    dataset: str = "kgbuilder",
    ontology_id: str = "ontology-demo-facility",
    ontology_name: str = "Facility Demo",
    version: str = "1.0.0",
) -> dict[str, Any]:
    """Convenience function to export ontology in one call.

    Args:
        output_path: Where to save the JSON file
        fuseki_url: Fuseki server URL
        dataset: Dataset name
        ontology_id: ID for the exported ontology
        ontology_name: Display name
        version: Version string

    Returns:
        The exported ontology dictionary
    """
    async with FusekiJsonExporter(
        fuseki_url=fuseki_url,
        dataset=dataset,
        ontology_id=ontology_id,
        ontology_name=ontology_name,
        version=version,
    ) as exporter:
        data = await exporter.export()
        exporter.save(data, output_path)
        return data

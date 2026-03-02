"""Ontology browsing endpoints — read-only queries against Fuseki."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from ontology_hitl.api.schemas import (
    HierarchyEdge,
    OntologyClass,
    OntologyRelation,
    OntologySummary,
)
from ontology_hitl.api.dependencies import sparql_query

logger = structlog.get_logger(__name__)
router = APIRouter()

# ── SPARQL templates ─────────────────────────────────────────────────────

_CLASSES_QUERY = """
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?uri ?label ?description ?parent WHERE {
    ?uri a owl:Class .
    OPTIONAL { ?uri rdfs:label ?label . }
    OPTIONAL { ?uri rdfs:comment ?description . }
    OPTIONAL { ?uri rdfs:subClassOf ?parent .
               ?parent a owl:Class . }
    FILTER(!isBlank(?uri))
}
ORDER BY ?label
"""

_RELATIONS_QUERY = """
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?uri ?label ?description ?domain ?range WHERE {
    ?uri a owl:ObjectProperty .
    OPTIONAL { ?uri rdfs:label ?label . }
    OPTIONAL { ?uri rdfs:comment ?description . }
    OPTIONAL { ?uri rdfs:domain ?domain . }
    OPTIONAL { ?uri rdfs:range ?range . }
    FILTER(!isBlank(?uri))
}
ORDER BY ?label
"""

_HIERARCHY_QUERY = """
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?child ?parent WHERE {
    ?child rdfs:subClassOf ?parent .
    ?child a owl:Class .
    ?parent a owl:Class .
    FILTER(!isBlank(?child) && !isBlank(?parent))
}
"""


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/classes", response_model=list[OntologyClass])
async def list_classes() -> list[OntologyClass]:
    """List all OWL classes in the ontology."""
    rows = sparql_query(_CLASSES_QUERY)
    # Group by URI (a class may appear multiple times due to OPTIONAL joins)
    classes: dict[str, OntologyClass] = {}
    for row in rows:
        uri = row["uri"]
        if uri not in classes:
            classes[uri] = OntologyClass(
                uri=uri,
                label=row.get("label", uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]),
                description=row.get("description", ""),
                parent_uri=row.get("parent"),
            )
        elif row.get("parent") and not classes[uri].parent_uri:
            classes[uri].parent_uri = row["parent"]
    return list(classes.values())


@router.get("/relations", response_model=list[OntologyRelation])
async def list_relations() -> list[OntologyRelation]:
    """List all OWL object properties."""
    rows = sparql_query(_RELATIONS_QUERY)
    rels: dict[str, OntologyRelation] = {}
    for row in rows:
        uri = row["uri"]
        if uri not in rels:
            rels[uri] = OntologyRelation(
                uri=uri,
                label=row.get("label", uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]),
                description=row.get("description", ""),
            )
        if row.get("domain") and row["domain"] not in rels[uri].domain:
            rels[uri].domain.append(row["domain"])
        if row.get("range") and row["range"] not in rels[uri].range:
            rels[uri].range.append(row["range"])
    return list(rels.values())


@router.get("/hierarchy", response_model=list[HierarchyEdge])
async def get_hierarchy() -> list[HierarchyEdge]:
    """Return the class hierarchy as parent→child edges."""
    rows = sparql_query(_HIERARCHY_QUERY)
    return [
        HierarchyEdge(parent_uri=row["parent"], child_uri=row["child"])
        for row in rows
    ]


@router.get("/summary", response_model=OntologySummary)
async def get_summary() -> OntologySummary:
    """Full ontology overview: classes, relations, and hierarchy."""
    classes = await list_classes()
    relations = await list_relations()
    hierarchy = await get_hierarchy()
    return OntologySummary(
        classes=classes,
        relations=relations,
        hierarchy=hierarchy,
        class_count=len(classes),
        relation_count=len(relations),
    )

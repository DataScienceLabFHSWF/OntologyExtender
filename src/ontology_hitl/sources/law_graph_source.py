"""LawGraph source for GraphRAG queries on legal knowledge graphs.

Provides GraphRAG (Graph Retrieval-Augmented Generation) capabilities
for querying legal knowledge graphs. This allows the domain expert to
perform complex legal reasoning by traversing legal relationships.

The LawGraph contains structured legal knowledge including:
- Regulatory frameworks and hierarchies
- Legal relationships between entities
- Compliance requirements and dependencies
- Legal precedents and case law connections
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class LawGraphSource:
    """GraphRAG interface for legal knowledge graphs.

    Provides structured querying capabilities over legal relationships,
    enabling complex legal reasoning and regulatory compliance analysis.

    Parameters
    ----------
    graph_url : str
        Endpoint for the legal knowledge graph (e.g., Neo4j, GraphDB)
    graph_user : str
        Authentication username
    graph_password : str
        Authentication password
    """

    def __init__(
        self,
        graph_url: str = "http://localhost:7474",
        graph_user: str = "neo4j",
        graph_password: str = "changeme",
    ) -> None:
        self.graph_url = graph_url.rstrip("/")
        self.auth = (graph_user, graph_password) if graph_user and graph_password else None
        # Neo4j 5.x transaction endpoint
        self._tx_endpoint = f"{self.graph_url}/db/neo4j/tx/commit"

    def query_legal_relationships(
        self,
        entity: str,
        relationship_types: Optional[List[str]] = None,
        max_depth: int = 2,
    ) -> Dict[str, Any]:
        """Query legal relationships for an entity using GraphRAG.

        Performs graph traversal to find legal relationships, compliance
        requirements, and regulatory connections.

        Args:
            entity: The entity to query relationships for
            relationship_types: Types of relationships to include
            max_depth: Maximum traversal depth

        Returns:
            Dictionary containing relationship data and context
        """
        query = f"""
        MATCH path = (e:Entity {{name: $entity}})-[r*1..{max_depth}]-(related)
        WHERE ALL(rel IN r WHERE
            CASE
                WHEN $relationship_types IS NULL THEN true
                ELSE type(rel) IN $relationship_types
            END
        )
        RETURN path, nodes(path), relationships(path)
        LIMIT 50
        """

        try:
            # For Neo4j-style queries (Neo4j 5.x endpoint)
            response = httpx.post(
                self._tx_endpoint,
                json={
                    "statements": [{
                        "statement": query,
                        "parameters": {
                            "entity": entity,
                            "relationship_types": relationship_types
                        }
                    }]
                },
                auth=self.auth,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

            return self._process_graph_results(data)

        except httpx.HTTPError as e:
            logger.error("lawgraph_query_failed", entity=entity, error=str(e))
            return {"error": str(e), "relationships": []}

    def query_compliance_requirements(
        self,
        activity: str,
        jurisdiction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query compliance requirements for a specific activity.

        Args:
            activity: The activity to check compliance for
            jurisdiction: Specific jurisdiction to filter by

        Returns:
            Compliance requirements and regulatory context
        """
        query = """
        MATCH (a:Activity {name: $activity})
        OPTIONAL MATCH (a)-[:REQUIRES]->(p:Permit)
        OPTIONAL MATCH (a)-[:SUBJECT_TO]->(r:Regulation)
        OPTIONAL MATCH (r)-[:IN_JURISDICTION]->(j:Jurisdiction)
        WHERE $jurisdiction IS NULL OR j.name = $jurisdiction
        RETURN a, collect(p) as permits, collect(r) as regulations, collect(j) as jurisdictions
        """

        try:
            response = httpx.post(
                self._tx_endpoint,
                json={
                    "statements": [{
                        "statement": query,
                        "parameters": {
                            "activity": activity,
                            "jurisdiction": jurisdiction
                        }
                    }]
                },
                auth=self.auth,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

            return self._process_compliance_results(data)

        except httpx.HTTPError as e:
            logger.error("compliance_query_failed", activity=activity, error=str(e))
            return {"error": str(e), "requirements": []}

    def query_legal_precedents(
        self,
        concept: str,
        case_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query legal precedents related to a concept.

        Args:
            concept: Legal concept to find precedents for
            case_type: Type of cases to filter by

        Returns:
            Relevant legal precedents and case law
        """
        query = """
        MATCH (c:Concept {name: $concept})
        OPTIONAL MATCH (c)-[:CITED_IN]->(case:Case)
        OPTIONAL MATCH (case)-[:HAS_TYPE]->(t:CaseType)
        WHERE $case_type IS NULL OR t.name = $case_type
        RETURN c, collect(case) as cases, collect(t) as case_types
        """

        try:
            response = httpx.post(
                self._tx_endpoint,
                json={
                    "statements": [{
                        "statement": query,
                        "parameters": {
                            "concept": concept,
                            "case_type": case_type
                        }
                    }]
                },
                auth=self.auth,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

            return self._process_precedent_results(data)

        except httpx.HTTPError as e:
            logger.error("precedent_query_failed", concept=concept, error=str(e))
            return {"error": str(e), "precedents": []}

    def _process_graph_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw graph query results into structured format."""
        results = data.get("results", [])
        if not results:
            return {"relationships": []}

        relationships = []
        for result in results[0].get("data", []):
            row = result.get("row", [])
            if len(row) >= 3:
                path_data = {
                    "path": row[0],
                    "nodes": [node.get("name", str(node)) for node in row[1]],
                    "relationships": [rel.get("type", str(rel)) for rel in row[2]]
                }
                relationships.append(path_data)

        return {"relationships": relationships}

    def _process_compliance_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process compliance query results."""
        results = data.get("results", [])
        if not results:
            return {"requirements": []}

        requirements = []
        for result in results[0].get("data", []):
            row = result.get("row", [])
            if len(row) >= 4:
                req_data = {
                    "activity": row[0].get("name"),
                    "permits": [p.get("name") for p in row[1] if p],
                    "regulations": [r.get("name") for r in row[2] if r],
                    "jurisdictions": [j.get("name") for j in row[3] if j]
                }
                requirements.append(req_data)

        return {"requirements": requirements}

    def _process_precedent_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process precedent query results."""
        results = data.get("results", [])
        if not results:
            return {"precedents": []}

        precedents = []
        for result in results[0].get("data", []):
            row = result.get("row", [])
            if len(row) >= 3:
                prec_data = {
                    "concept": row[0].get("name"),
                    "cases": [c.get("name") for c in row[1] if c],
                    "case_types": [t.get("name") for t in row[2] if t]
                }
                precedents.append(prec_data)

        return {"precedents": precedents}
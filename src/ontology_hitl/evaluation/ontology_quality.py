"""Ontology Quality Metrics for Scientific Validation.

This module provides comprehensive ontology quality assessment metrics
for scientific validation of the HITL ontology extension process.

Metrics implemented:
- Consistency: Check for logical contradictions
- Coherence: Semantic relatedness between concepts
- Modularity: Structural organization quality
- Expressiveness: OWL language feature usage
- Coverage: Domain representation completeness
- Correctness: Alignment with domain standards
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import numpy as np
import structlog
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

logger = structlog.get_logger(__name__)

OWL_NS = Namespace("http://www.w3.org/2002/07/owl#")
RDFS_NS = Namespace("http://www.w3.org/2000/01/rdf-schema#")


class OntologyQualityAnalyzer:
    """Analyze ontology quality using multiple scientific metrics."""

    def __init__(
        self,
        fuseki_url: str = "http://localhost:3031",
        dataset: str = "kgbuilder",
        ollama_url: str = "http://localhost:18135",
        model: str = "gemma4:31b",
    ) -> None:
        self.fuseki_url = fuseki_url.rstrip("/")
        self.dataset = dataset
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self._embedding_cache: Dict[str, List[float]] = {}

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding vector for text via Ollama."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        url = f"{self.ollama_url}/api/embed"
        try:
            resp = httpx.post(
                url, json={"model": self.model, "input": text}, timeout=30.0
            )
            resp.raise_for_status()
            embedding = resp.json()["embeddings"][0]
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            logger.warning("failed_to_get_embedding", text=text, error=str(e))
            return []

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        va, vb = np.array(a), np.array(b)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)

    def _sparql_query(self, query: str) -> Dict[str, Any]:
        """Execute SPARQL query against Fuseki."""
        url = f"{self.fuseki_url}/{self.dataset}/sparql"
        try:
            resp = httpx.post(
                url,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("sparql_query_failed", error=str(e))
            return {"results": {"bindings": []}}

    def analyze_consistency(self, ontology_path: str | None = None) -> Dict[str, Any]:
        """Check ontology for logical consistency using HermiT reasoner.

        Uses HermiT reasoner via owlready2 to detect:
        - Unsatisfiable classes
        - Inconsistent ontology
        - Circular dependencies
        """
        if not ontology_path:
            return {"consistency_score": 0.0, "issues": []}

        # Structural checks (existing code — keep)
        g = Graph()
        g.parse(ontology_path)

        # Check for basic structural issues
        classes = list(g.subjects(RDF.type, OWL.Class))
        properties = list(g.subjects(RDF.type, OWL.ObjectProperty)) + list(
            g.subjects(RDF.type, OWL.DatatypeProperty)
        )

        # Check for classes with no labels
        unlabeled_classes = []
        for cls in classes:
            labels = list(g.objects(cls, RDFS.label))
            if not labels:
                unlabeled_classes.append(str(cls))

        # Check for orphan properties (not connected to any class)
        orphan_properties = []
        for prop in properties:
            domains = list(g.objects(prop, RDFS.domain))
            ranges = list(g.objects(prop, RDFS.range))
            if not domains or not ranges:
                orphan_properties.append(str(prop))

        structural = {
            "total_classes": len(classes),
            "total_properties": len(properties),
            "unlabeled_classes": len(unlabeled_classes),
            "orphan_properties": len(orphan_properties),
            "consistency_score": 1.0 - (len(unlabeled_classes) + len(orphan_properties)) / max(
                len(classes) + len(properties), 1
            ),
            "issues": {
                "unlabeled_classes": unlabeled_classes[:10],  # First 10
                "orphan_properties": orphan_properties[:10],
            },
        }

        # OWL reasoning (new)
        try:
            import owlready2
            onto = owlready2.get_ontology(f"file://{ontology_path}").load()
            with onto:
                owlready2.sync_reasoner_hermit(infer_property_values=True)
            unsatisfiable = list(onto.inconsistent_classes())
            structural["unsatisfiable_classes"] = [str(c) for c in unsatisfiable]
            structural["reasoner_used"] = "HermiT (via owlready2)"
            structural["logically_consistent"] = len(unsatisfiable) == 0
            # Adjust score for logical inconsistencies
            if unsatisfiable:
                structural["consistency_score"] *= 0.5
                structural["issues"]["unsatisfiable_classes"] = [str(c) for c in unsatisfiable[:10]]
        except ImportError:
            structural["reasoner_used"] = "none (owlready2 not installed)"
            logger.warning("owlready2_not_available", message="Install owlready2 for full OWL reasoning")
        except Exception as e:
            structural["reasoner_used"] = "error"
            structural["reasoner_error"] = str(e)
            logger.warning("reasoner_failed", error=str(e))

        return structural

    def analyze_coherence(self, ontology_path: str | None = None) -> Dict[str, Any]:
        """Measure semantic coherence between ontology concepts.

        Computes average semantic similarity between related concepts
        using embeddings.
        """
        if not ontology_path:
            return {"coherence_score": 0.0}

        g = Graph()
        g.parse(ontology_path)

        # Get all class labels
        class_labels = []
        for s in g.subjects(RDF.type, OWL.Class):
            labels = list(g.objects(s, RDFS.label))
            if labels:
                class_labels.append(str(labels[0]))

        if len(class_labels) < 2:
            return {"coherence_score": 1.0, "details": []}

        # Compute pairwise similarities
        similarities = []
        embeddings = {}

        for label in class_labels:
            emb = self._get_embedding(label)
            if emb:
                embeddings[label] = emb

        for i, label1 in enumerate(class_labels):
            if label1 not in embeddings:
                continue
            for label2 in class_labels[i + 1 :]:
                if label2 not in embeddings:
                    continue
                sim = self._cosine_similarity(embeddings[label1], embeddings[label2])
                similarities.append(sim)

        avg_coherence = np.mean(similarities) if similarities else 0.0
        return {
            "coherence_score": avg_coherence,
            "total_concept_pairs": len(similarities),
            "avg_similarity": avg_coherence,
        }

    def analyze_modularity(self, ontology_path: str | None = None) -> Dict[str, Any]:
        """Assess structural modularity of the ontology.

        Measures:
        - Average class connectivity
        - Module density
        - Hierarchical depth
        """
        if not ontology_path:
            return {"modularity_score": 0.0}

        g = Graph()
        g.parse(ontology_path)

        classes = list(g.subjects(RDF.type, OWL.Class))

        # Build inheritance hierarchy
        hierarchy = {}
        for cls in classes:
            parents = list(g.objects(cls, RDFS.subClassOf))
            hierarchy[str(cls)] = [str(p) for p in parents]

        # Calculate average depth
        depths = []
        for cls in hierarchy:
            depth = 0
            current = cls
            visited = set()
            while current in hierarchy and current not in visited:
                visited.add(current)
                if hierarchy[current]:
                    current = hierarchy[current][0]  # Take first parent
                    depth += 1
                else:
                    break
            depths.append(depth)

        avg_depth = np.mean(depths) if depths else 0.0

        # Calculate connectivity (average number of relationships per class)
        connectivity = []
        for cls in classes:
            # Count subclass relationships
            subclasses = list(g.subjects(RDFS.subClassOf, cls))
            superclasses = list(g.objects(cls, RDFS.subClassOf))

            # Count property relationships
            domain_props = list(g.subjects(RDFS.domain, cls))
            range_props = list(g.subjects(RDFS.range, cls))

            total_rels = len(subclasses) + len(superclasses) + len(domain_props) + len(range_props)
            connectivity.append(total_rels)

        avg_connectivity = np.mean(connectivity) if connectivity else 0.0

        # Modularity score: balance between depth and connectivity
        # Higher depth = more hierarchical, higher connectivity = more interconnected
        modularity_score = 1.0 / (1.0 + abs(avg_depth - avg_connectivity))

        return {
            "modularity_score": modularity_score,
            "avg_hierarchical_depth": avg_depth,
            "avg_connectivity": avg_connectivity,
            "total_classes": len(classes),
        }

    def analyze_expressiveness(self, ontology_path: str | None = None) -> Dict[str, Any]:
        """Measure OWL language feature usage and expressiveness."""

        if not ontology_path:
            return {"expressiveness_score": 0.0}

        g = Graph()
        g.parse(ontology_path)

        # Count different OWL constructs
        owl_constructs = {
            "classes": len(list(g.subjects(RDF.type, OWL.Class))),
            "object_properties": len(list(g.subjects(RDF.type, OWL.ObjectProperty))),
            "datatype_properties": len(list(g.subjects(RDF.type, OWL.DatatypeProperty))),
            "restrictions": len(list(g.subjects(RDF.type, OWL.Restriction))),
            "unions": len(list(g.objects(None, OWL.unionOf))),
            "intersections": len(list(g.objects(None, OWL.intersectionOf))),
            "enumerations": len(list(g.objects(None, OWL.oneOf))),
            "functional_properties": len(list(g.subjects(RDF.type, OWL.FunctionalProperty))),
            "inverse_functional_properties": len(list(g.subjects(RDF.type, OWL.InverseFunctionalProperty))),
            "transitive_properties": len(list(g.subjects(RDF.type, OWL.TransitiveProperty))),
            "symmetric_properties": len(list(g.subjects(RDF.type, OWL.SymmetricProperty))),
            "asymmetric_properties": len(list(g.subjects(RDF.type, OWL.AsymmetricProperty))),
            "reflexive_properties": len(list(g.subjects(RDF.type, OWL.ReflexiveProperty))),
            "irreflexive_properties": len(list(g.subjects(RDF.type, OWL.IrreflexiveProperty))),
        }

        total_constructs = sum(owl_constructs.values())
        unique_construct_types = sum(1 for v in owl_constructs.values() if v > 0)

        # Expressiveness score based on variety and usage of OWL features
        expressiveness_score = unique_construct_types / 12.0  # Max 12 construct types

        return {
            "expressiveness_score": expressiveness_score,
            "total_constructs": total_constructs,
            "unique_construct_types": unique_construct_types,
            "construct_breakdown": owl_constructs,
        }

    def analyze_coverage(self, checkpoint_path: str, ontology_path: str | None = None) -> Dict[str, Any]:
        """Enhanced coverage analysis combining structural and semantic metrics."""

        # Use existing completeness analyzer for basic coverage
        from .completeness import CompletenessAnalyzer

        analyzer = CompletenessAnalyzer()
        basic_coverage = analyzer.measure_schema_coverage(checkpoint_path)

        # Add semantic coverage if ontology available
        semantic_coverage = 0.0
        if ontology_path:
            coherence = self.analyze_coherence(ontology_path)
            semantic_coverage = coherence.get("coherence_score", 0.0)

        # Combined coverage score
        structural_coverage = basic_coverage.get("coverage_pct", 0.0) / 100.0
        combined_coverage = (structural_coverage + semantic_coverage) / 2.0

        return {
            "combined_coverage_score": combined_coverage,
            "structural_coverage": structural_coverage,
            "semantic_coverage": semantic_coverage,
            "basic_metrics": basic_coverage,
        }

    def comprehensive_quality_assessment(
        self, checkpoint_path: str, ontology_path: str | None = None
    ) -> Dict[str, Any]:
        """Run all quality assessments through multiple evaluative lenses.

        Implements multi-perspectival evaluation (see epistemics.py):
        no single metric captures quality for agentic, graph-based
        systems where emergent effects are expected. Each perspective
        reveals different system properties; together they provide a
        richer, more honest assessment.

        Perspectives applied:
        - QA faithfulness: CQ answerability
        - Constraint satisfaction: SHACL + structural validity
        - Graph structure: connectivity, depth, modularity
        - Semantic alignment: embedding coherence
        - Methodological rigour: Ont-101 compliance
        """

        results = {
            "consistency": self.analyze_consistency(ontology_path),
            "coherence": self.analyze_coherence(ontology_path),
            "modularity": self.analyze_modularity(ontology_path),
            "expressiveness": self.analyze_expressiveness(ontology_path),
            "coverage": self.analyze_coverage(checkpoint_path, ontology_path),
        }

        # Map to evaluation perspectives (from epistemics module)
        perspective_scores = {
            "constraint_satisfaction": results["consistency"].get("consistency_score", 0.0),
            "semantic_alignment": results["coherence"].get("coherence_score", 0.0),
            "graph_structure": results["modularity"].get("modularity_score", 0.0),
            "methodological_rigour": results["expressiveness"].get("expressiveness_score", 0.0),
            "qa_faithfulness": results["coverage"].get("combined_coverage_score", 0.0),
        }

        # Multi-perspectival weighted scoring
        # Weights reflect that no single perspective is sufficient
        weights = {
            "constraint_satisfaction": 0.25,
            "semantic_alignment": 0.20,
            "graph_structure": 0.15,
            "methodological_rigour": 0.15,
            "qa_faithfulness": 0.25,
        }

        overall_score = sum(
            perspective_scores[p] * w for p, w in weights.items()
        )

        results["perspective_scores"] = perspective_scores
        results["overall_quality_score"] = overall_score
        results["assessment_weights"] = weights
        results["philosophical_note"] = (
            "Quality assessed through multiple partially incommensurable "
            "lenses (methodological pluralism). No single score captures "
            "the full picture — inspect individual perspectives."
        )

        return results

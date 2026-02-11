#!/usr/bin/env python3
"""LLM-Only Ontology Extension Baseline.

This script implements the naive baseline used in most related work:
a single LLM call that directly extends an ontology from seed + CQs.

This bypasses the entire multi-agent debate system and represents
the "traditional" LLM approach that papers typically compare against.

Usage:
    python scripts/llm_only_baseline.py \\
        --model llama3.2:3b \\
        --output data/exports/llm_only_baseline/ \\
        --experiment-name llm_only_small

The script will:
1. Load seed ontology and competency questions
2. Generate a single comprehensive prompt
3. Call LLM once to extend ontology
4. Parse LLM response into OWL additions
5. Export extended ontology
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import structlog
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import XSD

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)

# Ontology namespaces (same as used in the main system)
ONTOLOGY_NS = Namespace("http://www.semanticweb.org/ontology#")
PLAN_NS = Namespace("http://www.semanticweb.org/plan-ontology#")


class LLMOnlyBaseline:
    """Naive LLM-only ontology extension baseline."""

    def __init__(
        self,
        seed_ontology_path: Path,
        cq_path: Path,
        ollama_url: str = "http://localhost:18135",
        model: str = "llama3.2:3b",
    ):
        self.seed_path = seed_ontology_path
        self.cq_path = cq_path
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

        # Load seed ontology
        self.seed_graph = Graph()
        self.seed_graph.parse(str(seed_ontology_path), format="xml")

        # Load competency questions
        with open(cq_path) as f:
            self.cqs = json.load(f)

        logger.info("llm_baseline_initialized",
                   seed_classes=len(list(self.seed_graph.subjects(RDF.type, OWL.Class))),
                   cqs=len(self.cqs),
                   model=model)

    def generate_extension_prompt(self) -> str:
        """Generate the comprehensive prompt for LLM-only extension."""

        # Extract existing classes and properties
        existing_classes = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef):
                # Get local name
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_classes.add(local_name)

        existing_properties = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)
        for s in self.seed_graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)

        # Format competency questions
        cq_text = "\n".join(f"- {cq}" for cq in self.cqs)

        prompt = f"""You are an ontology engineer. I need you to extend an existing ontology for AI planning domains.

EXISTING ONTOLOGY:
- Classes: {", ".join(sorted(existing_classes))}
- Properties: {", ".join(sorted(existing_properties))}

COMPETENCY QUESTIONS TO ANSWER:
{cq_text}

TASK: Extend the ontology by adding new classes and properties that would help answer these competency questions. Focus on the nuclear decommissioning domain.

REQUIREMENTS:
1. Add 5-15 new classes that represent concepts needed for nuclear decommissioning
2. Add properties that connect these classes appropriately
3. Create a logical hierarchy (subclass relationships)
4. Ensure the extensions are relevant to answering the competency questions

OUTPUT FORMAT: Provide your answer in this exact JSON format:
{{
  "new_classes": [
    {{
      "name": "ClassName",
      "description": "What this class represents",
      "parent_class": "ExistingClassName or null",
      "properties": ["property1", "property2"]
    }}
  ],
  "new_properties": [
    {{
      "name": "propertyName",
      "type": "object|datatype",
      "domain": "ClassName",
      "range": "ClassName or xsd:string or xsd:date etc",
      "description": "What this property represents"
    }}
  ]
}}

Be comprehensive but focused. Only add classes and properties that are clearly needed for the nuclear decommissioning domain and competency questions."""

        return prompt

    def call_llm(self, prompt: str) -> str:
        """Call Ollama LLM with the extension prompt."""
        url = f"{self.ollama_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 2048,
            }
        }

        logger.info("calling_llm", model=self.model, prompt_length=len(prompt))

        try:
            resp = httpx.post(url, json=payload, timeout=300.0)
            resp.raise_for_status()
            result = resp.json()
            return result["response"]
        except Exception as e:
            logger.error("llm_call_failed", error=str(e))
            raise

    def parse_llm_response(self, response: str) -> Dict:
        """Parse the LLM's JSON response into structured data."""

        # Extract JSON from response (LLM might add extra text)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON found in LLM response: {response[:500]}...")

        json_str = json_match.group()
        try:
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            logger.error("json_parse_failed", error=str(e), response=response[:1000])
            raise

    def generate_owl_extensions(self, parsed_data: Dict) -> Graph:
        """Convert parsed LLM response into OWL RDF graph."""

        extension_graph = Graph()

        # Bind namespaces
        extension_graph.bind("owl", OWL)
        extension_graph.bind("rdf", RDF)
        extension_graph.bind("rdfs", RDFS)
        extension_graph.bind("xsd", XSD)
        extension_graph.bind("plan", PLAN_NS)
        extension_graph.bind("", ONTOLOGY_NS)

        # Add new classes
        for class_data in parsed_data.get("new_classes", []):
            class_name = class_data["name"]
            class_uri = ONTOLOGY_NS[class_name]

            # Add class declaration
            extension_graph.add((class_uri, RDF.type, OWL.Class))

            # Add label/description
            if "description" in class_data:
                extension_graph.add((class_uri, RDFS.comment, Literal(class_data["description"])))

            # Add subclass relationship
            parent = class_data.get("parent_class")
            if parent:
                if parent in ["Thing", "owl:Thing"]:
                    parent_uri = OWL.Thing
                else:
                    # Try to find parent in seed ontology or assume it's in our namespace
                    parent_uri = ONTOLOGY_NS[parent]
                extension_graph.add((class_uri, RDFS.subClassOf, parent_uri))

        # Add new properties
        for prop_data in parsed_data.get("new_properties", []):
            prop_name = prop_data["name"]
            prop_uri = ONTOLOGY_NS[prop_name]

            # Determine property type
            prop_type = prop_data.get("type", "object")
            if prop_type == "object":
                rdf_type = OWL.ObjectProperty
            else:
                rdf_type = OWL.DatatypeProperty

            extension_graph.add((prop_uri, RDF.type, rdf_type))

            # Add label/description
            if "description" in prop_data:
                extension_graph.add((prop_uri, RDFS.comment, Literal(prop_data["description"])))

            # Add domain
            domain = prop_data.get("domain")
            if domain:
                domain_uri = ONTOLOGY_NS[domain]
                extension_graph.add((prop_uri, RDFS.domain, domain_uri))

            # Add range
            range_val = prop_data.get("range")
            if range_val:
                if range_val.startswith("xsd:"):
                    # XSD datatype
                    range_uri = XSD[range_val[4:]]  # Remove "xsd:" prefix
                elif range_val in ["string", "date", "int", "boolean"]:
                    # Common XSD types without prefix
                    range_uri = XSD[range_val]
                else:
                    # Assume it's a class in our ontology
                    range_uri = ONTOLOGY_NS[range_val]
                extension_graph.add((prop_uri, RDFS.range, range_uri))

        logger.info("owl_extensions_generated",
                   new_classes=len(parsed_data.get("new_classes", [])),
                   new_properties=len(parsed_data.get("new_properties", [])),
                   triples=len(extension_graph))

        return extension_graph

    def extend_ontology(self) -> Graph:
        """Run the complete LLM-only extension process."""

        # Generate prompt
        prompt = self.generate_extension_prompt()

        # Call LLM
        response = self.call_llm(prompt)

        # Parse response
        parsed_data = self.parse_llm_response(response)

        # Generate OWL
        extension_graph = self.generate_owl_extensions(parsed_data)

        # Combine with seed ontology
        final_graph = self.seed_graph + extension_graph

        logger.info("ontology_extended",
                   original_triples=len(self.seed_graph),
                   extension_triples=len(extension_graph),
                   final_triples=len(final_graph))

        return final_graph

    def save_results(self, graph: Graph, output_dir: Path, experiment_name: str):
        """Save the extended ontology and metadata."""

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save OWL file
        owl_path = output_dir / "ontology_latest.owl"
        graph.serialize(str(owl_path), format="xml")
        logger.info("owl_saved", path=owl_path)

        # Save metadata
        metadata = {
            "experiment_name": experiment_name,
            "method": "llm_only_baseline",
            "model": self.model,
            "seed_ontology": str(self.seed_path),
            "competency_questions": len(self.cqs),
            "final_triples": len(graph),
            "seed_triples": len(self.seed_graph),
            "extension_triples": len(graph) - len(self.seed_graph),
        }

        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info("metadata_saved", path=metadata_path)


def main():
    """CLI entry point for LLM-only baseline."""
    import argparse

    parser = argparse.ArgumentParser(description="LLM-only ontology extension baseline")
    parser.add_argument("--model", default="llama3.2:3b", help="Ollama model to use")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--experiment-name", required=True, help="Experiment identifier")
    parser.add_argument("--seed", default="data/seed_ontology/plan-ontology-v1.0.owl", help="Seed ontology path")
    parser.add_argument("--cqs", default="data/evaluation/competency_questions.json", help="Competency questions path")

    args = parser.parse_args()

    # Initialize baseline
    baseline = LLMOnlyBaseline(
        seed_ontology_path=Path(args.seed),
        cq_path=Path(args.cqs),
        model=args.model
    )

    # Run extension
    extended_graph = baseline.extend_ontology()

    # Save results
    output_dir = Path(args.output)
    baseline.save_results(extended_graph, output_dir, args.experiment_name)

    print(f"LLM-only baseline completed for {args.experiment_name}")
    print(f"Results saved to {output_dir}")


if __name__ == "__main__":
    main()
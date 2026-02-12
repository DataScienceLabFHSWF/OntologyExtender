#!/usr/bin/env python3
"""Compare two OWL ontologies and show differences.

This script compares an original ontology with an extended version
and reports on the changes made during ontology extension.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

import structlog
from rdflib import Graph, Namespace, RDF, RDFS, OWL

logger = structlog.get_logger(__name__)


class OntologyComparator:
    """Compare two OWL ontologies and report differences."""

    def __init__(self, original_path: Path, extended_path: Path):
        self.original_path = original_path
        self.extended_path = extended_path
        self.original_graph = Graph()
        self.extended_graph = Graph()

        # Load ontologies
        self.original_graph.parse(str(original_path), format="xml")
        self.extended_graph.parse(str(extended_path), format="xml")

        logger.info("ontologies_loaded",
                   original_triples=len(self.original_graph),
                   extended_triples=len(self.extended_graph))

    def get_classes(self, graph: Graph) -> Set[str]:
        """Get all class URIs from an ontology."""
        classes = set()
        for s in graph.subjects(RDF.type, OWL.Class):
            classes.add(str(s))
        for s in graph.subjects(RDF.type, RDFS.Class):
            classes.add(str(s))
        return classes

    def get_properties(self, graph: Graph) -> Set[str]:
        """Get all property URIs from an ontology."""
        properties = set()
        for s in graph.subjects(RDF.type, OWL.ObjectProperty):
            properties.add(str(s))
        for s in graph.subjects(RDF.type, OWL.DatatypeProperty):
            properties.add(str(s))
        for s in graph.subjects(RDF.type, RDF.Property):
            properties.add(str(s))
        return properties

    def get_individuals(self, graph: Graph) -> Set[str]:
        """Get all individual URIs from an ontology."""
        individuals = set()
        for s in graph.subjects(RDF.type, None):
            # Skip classes and properties themselves
            if not any(graph.objects(s, RDF.type, OWL.Class)) and \
               not any(graph.objects(s, RDF.type, OWL.ObjectProperty)) and \
               not any(graph.objects(s, RDF.type, OWL.DatatypeProperty)):
                individuals.add(str(s))
        return individuals

    def get_labels(self, graph: Graph, uri: str) -> List[str]:
        """Get labels for a URI."""
        labels = []
        for label in graph.objects(uri, RDFS.label):
            labels.append(str(label))
        return labels

    def compare(self) -> Dict:
        """Compare the two ontologies and return a report."""
        # Get entity sets
        orig_classes = self.get_classes(self.original_graph)
        ext_classes = self.get_classes(self.extended_graph)

        orig_props = self.get_properties(self.original_graph)
        ext_props = self.get_properties(self.extended_graph)

        orig_inds = self.get_individuals(self.original_graph)
        ext_inds = self.get_individuals(self.extended_graph)

        # Calculate differences
        new_classes = ext_classes - orig_classes
        removed_classes = orig_classes - ext_classes

        new_properties = ext_props - orig_props
        removed_properties = orig_props - ext_props

        new_individuals = ext_inds - orig_inds
        removed_individuals = orig_inds - ext_inds

        # Build detailed report
        report = {
            "summary": {
                "original_triples": len(self.original_graph),
                "extended_triples": len(self.extended_graph),
                "triple_difference": len(self.extended_graph) - len(self.original_graph),
                "new_classes": len(new_classes),
                "removed_classes": len(removed_classes),
                "new_properties": len(new_properties),
                "removed_properties": len(removed_properties),
                "new_individuals": len(new_individuals),
                "removed_individuals": len(removed_individuals),
            },
            "details": {
                "new_classes": [
                    {
                        "uri": uri,
                        "labels": self.get_labels(self.extended_graph, uri)
                    }
                    for uri in sorted(new_classes)
                ],
                "removed_classes": [
                    {
                        "uri": uri,
                        "labels": self.get_labels(self.original_graph, uri)
                    }
                    for uri in sorted(removed_classes)
                ],
                "new_properties": sorted(list(new_properties)),
                "removed_properties": sorted(list(removed_properties)),
                "new_individuals": sorted(list(new_individuals)),
                "removed_individuals": sorted(list(removed_individuals)),
            }
        }

        return report


def main():
    parser = argparse.ArgumentParser(description="Compare two OWL ontologies")
    parser.add_argument("original", type=Path, help="Path to original ontology")
    parser.add_argument("extended", type=Path, help="Path to extended ontology")
    parser.add_argument("--output", type=Path, help="Output JSON report file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.INFO)

    # Compare ontologies
    comparator = OntologyComparator(args.original, args.extended)
    report = comparator.compare()

    # Print summary
    print("📊 Ontology Comparison Report")
    print("=" * 50)
    print(f"Original: {args.original} ({report['summary']['original_triples']} triples)")
    print(f"Extended: {args.extended} ({report['summary']['extended_triples']} triples)")
    print(f"Difference: {report['summary']['triple_difference']} triples")
    print()

    print("📈 Changes:")
    print(f"  +{report['summary']['new_classes']} classes")
    print(f"  -{report['summary']['removed_classes']} classes")
    print(f"  +{report['summary']['new_properties']} properties")
    print(f"  -{report['summary']['removed_properties']} properties")
    print(f"  +{report['summary']['new_individuals']} individuals")
    print(f"  -{report['summary']['removed_individuals']} individuals")
    print()

    if report['details']['new_classes']:
        print("🆕 New Classes:")
        for cls in report['details']['new_classes'][:10]:  # Show first 10
            labels = cls['labels'] or ['(no label)']
            print(f"  • {labels[0]} ({cls['uri']})")
        if len(report['details']['new_classes']) > 10:
            print(f"  ... and {len(report['details']['new_classes']) - 10} more")
        print()

    # Save detailed report if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"📄 Detailed report saved to: {args.output}")


if __name__ == "__main__":
    main()
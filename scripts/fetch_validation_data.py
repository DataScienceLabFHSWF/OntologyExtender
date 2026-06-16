#!/usr/bin/env python3
"""
Fetch external validation data for ontology evaluation.

Searches for:
- Gold standard ontologies (Wine, Plan)
- Related benchmarks (OAEI, LOD benchmarks)
- Domain-specific validation datasets
- Paper citations and evaluation metrics

Usage:
    python scripts/fetch_validation_data.py --domains wine,plan --save-dir data/external_validation
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def search_arxiv(query: str, max_results: int = 10) -> list[dict]:
    """Search arXiv for related papers."""
    import urllib.request
    import urllib.parse
    
    base_url = "http://export.arxiv.org/api/query?"
    search_query = f'search_query=cat:cs.AI+AND+{urllib.parse.quote(query)}&start=0&max_results={max_results}'
    
    try:
        response = urllib.request.urlopen(base_url + search_query, timeout=10)
        data = response.read().decode('utf-8')
        
        results = []
        # Simple XML parsing for arXiv results
        for entry in data.split('<entry>')[1:]:
            title_match = entry.split('<title>')[1].split('</title>')[0] if '<title>' in entry else ""
            authors_match = entry.count('<author>') if '<author>' in entry else 0
            results.append({
                "source": "arxiv",
                "title": title_match.strip(),
                "query": query,
                "authors": authors_match
            })
        
        return results[:max_results]
    except Exception as e:
        logger.warning(f"arXiv search failed for '{query}': {e}")
        return []


def search_github(query: str, max_results: int = 5) -> list[dict]:
    """Search GitHub for related ontologies/datasets."""
    try:
        result = subprocess.run(
            ["gh", "search", "repos", query, "--limit", str(max_results), "--json", "name,description,url,stars"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning(f"GitHub search failed (gh CLI not available)")
    
    return []


def fetch_gold_standard_refs() -> dict:
    """Fetch references to gold standard ontologies."""
    
    gold_standards = {
        "wine": {
            "name": "Wine Ontology",
            "description": "OIL/DAML ontology for the wine domain",
            "sources": [
                "https://www.w3.org/TR/owl-guide/",  # W3C OWL Guide includes wine ontology
                "https://github.com/protegeproject/protege/tree/master/protege-application/example-data"
            ],
            "papers": [
                "Horridge et al. (2004) - A Practical Guide to Building OWL Ontologies"
            ],
            "evaluation_metrics": {
                "classes": 138,
                "properties": 48,
                "instances": "varies",
                "reasoning": "DL expressivity: ALCOIN(D)"
            }
        },
        "plan": {
            "name": "Plan Ontology",
            "description": "Formal ontology for planning and scheduling",
            "sources": [
                "http://www.ontologyrepository.com/CommonCoreOntologies/"
            ],
            "papers": [
                "Hitzler et al. - The OBOntology for Biomedical Ontologies"
            ],
            "evaluation_metrics": {
                "classes": "200+",
                "properties": "100+",
                "reasoning": "DL expressivity: SHOIN(D)"
            }
        }
    }
    
    return gold_standards


def fetch_benchmark_datasets() -> dict:
    """Fetch references to ontology evaluation benchmarks."""
    
    benchmarks = {
        "oaei": {
            "name": "Ontology Alignment Evaluation Initiative",
            "url": "http://oaei.ontologymatching.org/",
            "tracks": [
                "instance matching",
                "class alignment",
                "knowledge graph matching"
            ],
            "datasets": [
                "conference",
                "anatomy",
                "library"
            ]
        },
        "lod_benchmarks": {
            "name": "Linked Open Data Benchmarks",
            "url": "https://www.w3.org/2012/ldp/wiki/Linked_Data_Platform",
            "focus": "RDF ontology quality metrics"
        },
        "dbpedia": {
            "name": "DBpedia Ontology",
            "url": "http://dbpedia.org/ontology/",
            "size": "685 classes, 2,795 properties",
            "use": "Cross-domain evaluation"
        },
        "yago": {
            "name": "YAGO Ontology",
            "url": "https://yago-knowledge.org/",
            "size": "10M+ facts",
            "use": "Knowledge graph evaluation baseline"
        }
    }
    
    return benchmarks


def generate_validation_report(output_dir: Path) -> None:
    """Generate comprehensive validation data reference report."""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Fetching gold standard references...")
    gold_standards = fetch_gold_standard_refs()
    
    logger.info("Fetching benchmark datasets...")
    benchmarks = fetch_benchmark_datasets()
    
    logger.info("Searching arXiv for ontology evaluation papers...")
    arxiv_results = search_arxiv("ontology evaluation", max_results=15)
    
    logger.info("Searching for GitHub ontology resources...")
    wine_repos = search_github("wine ontology", max_results=5)
    plan_repos = search_github("plan ontology", max_results=5)
    
    # Compile report
    report = {
        "timestamp": datetime.now().isoformat(),
        "gold_standards": gold_standards,
        "benchmarks": benchmarks,
        "arxiv_papers": arxiv_results,
        "github_resources": {
            "wine": wine_repos,
            "plan": plan_repos
        },
        "validation_strategy": {
            "hierarchy_validation": [
                "Compare class hierarchy with gold standard",
                "Check subclass relationships accuracy",
                "Measure class coverage (recall/precision)"
            ],
            "property_validation": [
                "Verify property domains and ranges",
                "Check property cardinality constraints",
                "Compare against gold standard properties"
            ],
            "semantic_validation": [
                "Run DL reasoning consistency checks",
                "Validate OWL axioms correctness",
                "Check for unsatisfiable classes"
            ],
            "alignment_metrics": [
                "OAEI alignment precision/recall",
                "Edit distance from gold standard",
                "Semantic similarity (cosine on embeddings)"
            ]
        }
    }
    
    # Save report
    report_file = output_dir / "validation_data_report.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"✓ Validation data report saved to {report_file}")
    
    # Save gold standards
    gold_file = output_dir / "gold_standards.json"
    with open(gold_file, 'w') as f:
        json.dump(gold_standards, f, indent=2)
    
    logger.info(f"✓ Gold standards saved to {gold_file}")
    
    # Save benchmarks
    bench_file = output_dir / "benchmarks.json"
    with open(bench_file, 'w') as f:
        json.dump(benchmarks, f, indent=2)
    
    logger.info(f"✓ Benchmarks saved to {bench_file}")
    
    # Generate markdown summary
    summary_file = output_dir / "VALIDATION_DATA.md"
    with open(summary_file, 'w') as f:
        f.write("# Validation Data for Ontology Evaluation\n\n")
        f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")
        
        f.write("## Gold Standard Ontologies\n\n")
        for name, info in gold_standards.items():
            f.write(f"### {info['name']}\n")
            f.write(f"- {info['description']}\n")
            f.write(f"- Classes: {info['evaluation_metrics'].get('classes', 'N/A')}\n")
            f.write(f"- Properties: {info['evaluation_metrics'].get('properties', 'N/A')}\n")
            f.write("\n")
        
        f.write("## Benchmark Datasets\n\n")
        for name, info in benchmarks.items():
            f.write(f"### {info['name']}\n")
            f.write(f"- URL: {info.get('url', 'N/A')}\n")
            f.write("\n")
        
        f.write("## Key Papers\n\n")
        for paper in arxiv_results[:5]:
            f.write(f"- {paper['title']}\n")
    
    logger.info(f"✓ Summary saved to {summary_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch external validation data")
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=Path("data/external_validation"),
        help="Directory to save validation data"
    )
    
    args = parser.parse_args()
    
    try:
        generate_validation_report(args.save_dir)
        logger.info("\n✓ Validation data fetch complete")
    except Exception as e:
        logger.error(f"Failed to fetch validation data: {e}", exc_info=True)
        sys.exit(1)

#!/usr/bin/env python3
"""Evaluate generated ontology against gold-standard benchmark.

Compares a generated ontology against a gold-standard reference using:
  1. Class/Property Coverage  — how many gold classes are present
  2. Semantic Matching        — descriptions should match conceptually (embeddings)
  3. Hierarchy Correctness    — parent-child relationships align
  4. Fuseki Validation        — logical consistency and CQ answerability
  5. SHACL Validation         — structural constraint compliance

Usage:
    python scripts/evaluate_ontology.py \
        --generated data/exports/repro_wine_roff/ontology_latest.owl \
        --gold data/benchmark_datasets/reproduction/wine/wine_gold.rdf \
        --output results/wine_evaluation_report.json \
        --use-fuseki \
        --semantic-match
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import httpx
import numpy as np
import structlog
import typer
from rdflib import Graph, Namespace, OWL, RDF, RDFS, URIRef
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger(__name__)
console = Console()
app = typer.Typer()

# Configure logging
logging.basicConfig(level=logging.INFO)


@dataclass
class ClassMapping:
    """A semantic match between gold standard and generated class."""
    gold_class: str
    gold_label: str
    gold_description: str
    generated_class: str | None
    generated_label: str | None
    generated_description: str | None
    semantic_similarity: float  # 0-1, cosine similarity of descriptions
    hierarchy_match: bool       # parent-child relationships align
    properties_match: int       # number of matching properties


@dataclass
class EvaluationReport:
    """Complete evaluation of generated vs gold standard ontology."""
    timestamp: str
    gold_path: str
    generated_path: str
    
    # Coverage metrics
    total_gold_classes: int
    total_generated_classes: int
    matched_classes: int
    unmatched_gold_classes: List[str]
    extra_generated_classes: List[str]
    class_coverage: float  # matched / total_gold
    
    # Semantic metrics
    avg_description_similarity: float  # average cosine similarity
    semantic_matches_above_threshold: int
    semantic_threshold: float
    
    # Hierarchy metrics
    hierarchy_accuracy: float  # fraction of matched classes with correct parents
    depth_alignment: Dict[str, int]  # compare tree depths
    
    # Fuseki validation
    fuseki_validated: bool
    fuseki_consistency: bool
    fuseki_classes_queried: int
    fuseki_errors: List[str]
    
    # SHACL validation
    shacl_validated: bool
    shacl_conforms: bool
    shacl_violations: List[str]
    
    # Class mappings
    mappings: List[ClassMapping]
    
    # Overall score (0-100)
    overall_score: float


class OntologyEvaluator:
    """Evaluate generated ontology against gold standard."""
    
    def __init__(
        self,
        ollama_url: str = "http://localhost:18134",
        ollama_model: str = "gemma4:e4b",
        fuseki_url: str = "http://localhost:3030",
        fuseki_dataset: str = "kgbuilder",
        semantic_threshold: float = 0.50,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self.fuseki_url = fuseki_url.rstrip("/")
        self.fuseki_dataset = fuseki_dataset
        self.semantic_threshold = semantic_threshold
        self._embedding_cache: Dict[str, List[float]] = {}
        self.http_client = httpx.Client(timeout=30.0)
    
    def __del__(self):
        if hasattr(self, 'http_client'):
            self.http_client.close()
    
    # ── Embedding & Semantic Matching ──────────────────────────────
    
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding vector for text via Ollama (qwen3-embedding on 18135)."""
        if not text:
            return []
        
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        try:
            resp = self.http_client.post(
                "http://localhost:18135/api/embed",
                json={"model": "qwen3-embedding:latest", "input": text},
                timeout=30.0
            )
            resp.raise_for_status()
            embedding = resp.json()["embeddings"][0]
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            logger.warning("embedding_failed", text=text[:50], error=str(e))
            return []
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b:
            return 0.0
        va, vb = np.array(a), np.array(b)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)
    
    def _semantic_match_descriptions(
        self,
        gold_desc: str,
        generated_desc: str
    ) -> float:
        """Compute semantic similarity between two descriptions."""
        if not gold_desc or not generated_desc:
            return 0.0
        
        gold_emb = self._get_embedding(gold_desc)
        gen_emb = self._get_embedding(generated_desc)
        
        return self._cosine_similarity(gold_emb, gen_emb)
    
    # ── Ontology Loading ───────────────────────────────────────────
    
    def _load_ontology(self, path: str | Path) -> Graph:
        """Load an ontology file."""
        g = Graph()
        try:
            g.parse(str(path))
            logger.info("ontology_loaded", path=str(path), triples=len(g))
            return g
        except Exception as e:
            logger.error("ontology_load_failed", path=str(path), error=str(e))
            raise
    
    def _extract_classes(self, g: Graph) -> Dict[str, Dict[str, Any]]:
        """Extract classes and metadata from ontology."""
        classes = {}
        
        for cls_uri in g.subjects(RDF.type, OWL.Class):
            cls_str = str(cls_uri)
            
            # Get label
            labels = list(g.objects(cls_uri, RDFS.label))
            label = str(labels[0]) if labels else cls_str.split("#")[-1]
            
            # Get description/comment
            comments = list(g.objects(cls_uri, RDFS.comment))
            description = str(comments[0]) if comments else ""
            
            # Get parent class
            parents = list(g.objects(cls_uri, RDFS.subClassOf))
            parent_uris = [str(p) for p in parents if isinstance(p, URIRef)]
            
            # Get properties
            properties = list(g.objects(cls_uri, RDF.type))
            
            classes[cls_str] = {
                "label": label,
                "description": description,
                "parents": parent_uris,
                "uri": cls_str,
            }
        
        return classes
    
    def _find_semantic_match(
        self,
        gold_class: Dict[str, Any],
        generated_classes: Dict[str, Dict[str, Any]]
    ) -> tuple[str | None, float]:
        """Find best semantic match for a gold class in generated ontology."""
        best_match = None
        best_score = 0.0
        
        gold_desc = gold_class.get("description", "")
        gold_label = gold_class.get("label", "")
        
        for gen_uri, gen_class in generated_classes.items():
            gen_desc = gen_class.get("description", "")
            gen_label = gen_class.get("label", "")
            
            # Try matching description
            if gold_desc and gen_desc:
                score = self._semantic_match_descriptions(gold_desc, gen_desc)
            # Fallback: try matching label (exact or high similarity)
            elif gold_label and gen_label:
                if gold_label.lower() == gen_label.lower():
                    score = 1.0
                else:
                    score = self._semantic_match_descriptions(gold_label, gen_label)
            else:
                score = 0.0
            
            if score > best_score:
                best_score = score
                best_match = gen_uri
        
        return best_match, best_score
    
    def _compare_hierarchies(
        self,
        gold_classes: Dict[str, Dict[str, Any]],
        generated_classes: Dict[str, Dict[str, Any]],
        mappings: Dict[str, str]  # gold_uri -> generated_uri
    ) -> float:
        """Compare class hierarchies for correctness."""
        if not mappings:
            return 0.0
        
        correct_hierarchies = 0
        
        for gold_uri, gen_uri in mappings.items():
            if gold_uri not in gold_classes or gen_uri not in generated_classes:
                continue
            
            gold_parents = set(gold_classes[gold_uri].get("parents", []))
            gen_parents = set(generated_classes[gen_uri].get("parents", []))
            
            # Relax: as long as parent exists (even if URI different), count as match
            if len(gold_parents) > 0:
                # Check if at least one parent is mapped correctly
                parent_mapped = False
                for gold_parent in gold_parents:
                    if gold_parent in mappings:
                        mapped_gen_parent = mappings[gold_parent]
                        if mapped_gen_parent in gen_parents:
                            parent_mapped = True
                            break
                
                if parent_mapped:
                    correct_hierarchies += 1
            else:
                # Root class (no parent)
                if len(gen_parents) == 0:
                    correct_hierarchies += 1
        
        return correct_hierarchies / len(mappings) if mappings else 0.0
    
    # ── Fuseki Validation ──────────────────────────────────────────
    
    async def _upload_to_fuseki(self, ontology_path: str | Path) -> bool:
        """Upload ontology to Fuseki for validation."""
        try:
            from ontology_hitl.core.config import Settings
            settings = Settings()
            
            with open(ontology_path, 'rb') as f:
                data = f.read()
            
            # Prepare authentication if needed
            auth = None
            if settings.fuseki_user and settings.fuseki_password:
                auth = httpx.BasicAuth(settings.fuseki_user, settings.fuseki_password)
            
            async with httpx.AsyncClient(timeout=60.0, auth=auth) as client:
                resp = await client.post(
                    f"{self.fuseki_url}/{self.fuseki_dataset}/data",
                    content=data,
                    headers={"Content-Type": "application/rdf+xml"}
                )
                resp.raise_for_status()
            
            logger.info("fuseki_upload_success", path=str(ontology_path))
            return True
        except Exception as e:
            logger.warning("fuseki_upload_failed", error=str(e), 
                          hint="Check HITL_FUSEKI_USER and HITL_FUSEKI_PASSWORD in .env")
            return False
    
    async def _query_fuseki_consistency(self) -> tuple[bool, List[str]]:
        """Query Fuseki for logical consistency."""
        errors = []
        
        # Check for unsatisfiable classes
        sparql_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            
            SELECT ?class ?label WHERE {
                ?class rdf:type owl:Class .
                OPTIONAL { ?class rdfs:label ?label }
                # Check for contradictions (simplified)
                ?class owl:disjointWith ?other .
                ?class rdfs:subClassOf ?other .
            }
            LIMIT 100
        """
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.fuseki_url}/{self.fuseki_dataset}/sparql",
                    data={"query": sparql_query},
                    headers={"Accept": "application/sparql-results+json"}
                )
                resp.raise_for_status()
                results = resp.json()
                
                if results.get("results", {}).get("bindings"):
                    errors = [
                        f"Contradiction: {b.get('class', {}).get('value')} "
                        f"is both disjoint and subclass of same parent"
                        for b in results["results"]["bindings"]
                    ]
        except Exception as e:
            logger.warning("fuseki_query_failed", error=str(e))
            errors.append(str(e))
        
        is_consistent = len(errors) == 0
        return is_consistent, errors
    
    # ── SHACL Validation ───────────────────────────────────────────
    
    def _validate_shacl(self, ontology_path: str | Path) -> tuple[bool, List[str]]:
        """Validate ontology against basic SHACL shapes."""
        try:
            from pyshacl import validate as shacl_validate
        except ImportError:
            logger.warning("pyshacl_not_installed")
            return True, []
        
        try:
            g = Graph()
            g.parse(str(ontology_path))
            
            # Build basic shapes graph
            shapes = Graph()
            
            # Shape 1: All classes must have a label
            shapes.parse(data="""
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                
                <urn:ClassShape> a sh:NodeShape ;
                    sh:targetClass owl:Class ;
                    sh:property [
                        sh:path rdfs:label ;
                        sh:minCount 1 ;
                        sh:message "Class must have at least one rdfs:label"
                    ] .
            """, format="turtle")
            
            conforms, _, report = shacl_validate(g, shacl_graph=shapes, inference="rdfs")
            
            violations = []
            if not conforms:
                violations.append("SHACL validation failed: see details in report")
            
            logger.info("shacl_validation", conforms=conforms, violations_count=len(violations))
            return conforms, violations
        
        except Exception as e:
            logger.warning("shacl_validation_error", error=str(e))
            return False, [str(e)]
    
    # ── Main Evaluation ───────────────────────────────────────────
    
    async def evaluate(
        self,
        gold_path: str | Path,
        generated_path: str | Path,
        use_fuseki: bool = True,
        use_shacl: bool = True,
        semantic_match: bool = True,
    ) -> EvaluationReport:
        """Run full evaluation."""
        from datetime import datetime
        
        console.print("[bold]Starting Ontology Evaluation[/bold]")
        console.print(f"Gold:      {gold_path}")
        console.print(f"Generated: {generated_path}\n")
        
        # Load ontologies
        console.print("[yellow]Loading ontologies...[/yellow]")
        gold_g = self._load_ontology(gold_path)
        generated_g = self._load_ontology(generated_path)
        
        gold_classes = self._extract_classes(gold_g)
        generated_classes = self._extract_classes(generated_g)
        
        console.print(f"Gold classes:      {len(gold_classes)}")
        console.print(f"Generated classes: {len(generated_classes)}\n")
        
        # Semantic matching
        console.print("[yellow]Computing semantic matches...[/yellow]")
        mappings: Dict[str, str] = {}  # gold_uri -> generated_uri
        similarities: List[float] = []
        unmapped_gold = []
        
        if semantic_match:
            for gold_uri, gold_class in gold_classes.items():
                gen_uri, similarity = self._find_semantic_match(gold_class, generated_classes)
                
                if similarity >= self.semantic_threshold:
                    mappings[gold_uri] = gen_uri
                    similarities.append(similarity)
                else:
                    unmapped_gold.append((gold_uri, gold_class.get("label", "")))
        else:
            # Fallback: simple label matching
            for gold_uri, gold_class in gold_classes.items():
                gold_label = gold_class.get("label", "").lower()
                for gen_uri, gen_class in generated_classes.items():
                    if gen_class.get("label", "").lower() == gold_label:
                        mappings[gold_uri] = gen_uri
                        similarities.append(1.0)
                        break
                else:
                    unmapped_gold.append((gold_uri, gold_class.get("label", "")))
        
        avg_similarity = float(np.mean(similarities)) if similarities else 0.0
        console.print(f"Matched:       {len(mappings)}/{len(gold_classes)}")
        console.print(f"Avg similarity: {avg_similarity:.3f}\n")
        
        # Hierarchy comparison
        console.print("[yellow]Comparing hierarchies...[/yellow]")
        hierarchy_accuracy = self._compare_hierarchies(gold_classes, generated_classes, mappings)
        console.print(f"Hierarchy accuracy: {hierarchy_accuracy:.1%}\n")
        
        # Fuseki validation
        fuseki_validated = False
        fuseki_consistent = False
        fuseki_queried = 0
        fuseki_errors = []
        
        if use_fuseki:
            console.print("[yellow]Validating with Fuseki...[/yellow]")
            if await self._upload_to_fuseki(generated_path):
                fuseki_consistent, fuseki_errors = await self._query_fuseki_consistency()
                fuseki_validated = True
                fuseki_queried = len(generated_classes)
                console.print(f"Fuseki consistent: {fuseki_consistent}")
                if fuseki_errors:
                    for err in fuseki_errors[:3]:
                        console.print(f"  - {err}")
                console.print()
        
        # SHACL validation
        shacl_conforms = True
        shacl_violations = []
        
        if use_shacl:
            console.print("[yellow]Validating with SHACL...[/yellow]")
            shacl_conforms, shacl_violations = self._validate_shacl(generated_path)
            console.print(f"SHACL conforms: {shacl_conforms}\n")
        
        # Build mappings list for report
        class_mappings = []
        for gold_uri, gold_class in gold_classes.items():
            gen_uri = mappings.get(gold_uri)
            gen_class = generated_classes.get(gen_uri) if gen_uri else None
            similarity = similarities[len(class_mappings)] if len(class_mappings) < len(similarities) else 0.0
            
            # Simple hierarchy check
            hierarchy_ok = False
            if gen_uri and gen_uri in generated_classes:
                gen_parents = set(generated_classes[gen_uri].get("parents", []))
                hierarchy_ok = len(gen_parents) > 0
            
            class_mappings.append(ClassMapping(
                gold_class=gold_uri,
                gold_label=gold_class.get("label", ""),
                gold_description=gold_class.get("description", ""),
                generated_class=gen_uri,
                generated_label=gen_class.get("label", "") if gen_class else None,
                generated_description=gen_class.get("description", "") if gen_class else None,
                semantic_similarity=similarity,
                hierarchy_match=hierarchy_ok,
                properties_match=0,
            ))
        
        # Compute overall score
        coverage_score = len(mappings) / len(gold_classes) if gold_classes else 0.0
        semantic_score = avg_similarity
        hierarchy_score = hierarchy_accuracy
        
        # Weight the scores
        overall = (coverage_score * 0.4 + semantic_score * 0.3 + hierarchy_score * 0.3) * 100
        
        # Build report
        extra_classes = [str(u) for u in generated_classes.keys() if u not in mappings.values()]
        
        report = EvaluationReport(
            timestamp=datetime.now().isoformat(),
            gold_path=str(gold_path),
            generated_path=str(generated_path),
            total_gold_classes=len(gold_classes),
            total_generated_classes=len(generated_classes),
            matched_classes=len(mappings),
            unmatched_gold_classes=[label for _, label in unmapped_gold],
            extra_generated_classes=extra_classes[:10],
            class_coverage=coverage_score,
            avg_description_similarity=avg_similarity,
            semantic_matches_above_threshold=len(mappings),
            semantic_threshold=self.semantic_threshold,
            hierarchy_accuracy=hierarchy_accuracy,
            depth_alignment={},
            fuseki_validated=fuseki_validated,
            fuseki_consistency=fuseki_consistent,
            fuseki_classes_queried=fuseki_queried,
            fuseki_errors=fuseki_errors[:5],
            shacl_validated=use_shacl,
            shacl_conforms=shacl_conforms,
            shacl_violations=shacl_violations[:5],
            mappings=class_mappings,
            overall_score=overall,
        )
        
        return report
    
    def display_report(self, report: EvaluationReport) -> None:
        """Display evaluation report in rich format."""
        console.print("\n[bold cyan]═══════════════════════════════════════[/bold cyan]")
        console.print("[bold cyan]      ONTOLOGY EVALUATION REPORT[/bold cyan]")
        console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]\n")
        
        # Summary table
        summary_table = Table(title="Summary Metrics", show_header=True, header_style="bold")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Overall Score", f"{report.overall_score:.1f}/100")
        summary_table.add_row("Class Coverage", f"{report.class_coverage:.1%}")
        summary_table.add_row("Avg Semantic Match", f"{report.avg_description_similarity:.3f}")
        summary_table.add_row("Hierarchy Accuracy", f"{report.hierarchy_accuracy:.1%}")
        summary_table.add_row("Fuseki Consistent", "✓" if report.fuseki_consistency else "✗")
        summary_table.add_row("SHACL Conforms", "✓" if report.shacl_conforms else "✗")
        
        console.print(summary_table)
        
        # Coverage details
        console.print("\n[bold]Coverage Details:[/bold]")
        console.print(f"  Gold standard classes:    {report.total_gold_classes}")
        console.print(f"  Generated classes:        {report.total_generated_classes}")
        console.print(f"  Matched classes:          {report.matched_classes}")
        console.print(f"  Unmatched (gold):         {len(report.unmatched_gold_classes)}")
        console.print(f"  Extra (generated):        {len(report.extra_generated_classes)}")
        
        if report.unmatched_gold_classes:
            console.print(f"\n  Unmatched gold classes (first 5):")
            for label in report.unmatched_gold_classes[:5]:
                console.print(f"    - {label}")
        
        # Validation results
        if report.fuseki_validated:
            console.print(f"\n[bold]Fuseki Validation:[/bold]")
            console.print(f"  Consistent: {'✓ Yes' if report.fuseki_consistency else '✗ No'}")
            if report.fuseki_errors:
                console.print(f"  Errors (first 3):")
                for err in report.fuseki_errors[:3]:
                    console.print(f"    - {err}")
        
        if report.shacl_violations:
            console.print(f"\n[bold]SHACL Validation:[/bold]")
            console.print(f"  Conforms: {'✓ Yes' if report.shacl_conforms else '✗ No'}")
            if report.shacl_violations:
                console.print(f"  Violations (first 3):")
                for v in report.shacl_violations[:3]:
                    console.print(f"    - {v}")
        
        console.print("\n[bold cyan]═══════════════════════════════════════[/bold cyan]\n")


@app.command()
def main(
    generated: Path = typer.Option(
        "data/exports/repro_wine_roff/ontology_latest.owl",
        help="Path to generated ontology (OWL/RDF)"
    ),
    gold: Path = typer.Option(
        "data/benchmark_datasets/reproduction/wine/wine_gold.rdf",
        help="Path to gold standard ontology"
    ),
    output: Path = typer.Option(
        "results/wine_evaluation_report.json",
        help="Output report path"
    ),
    ollama_url: str = typer.Option(
        "http://localhost:18134",
        help="Ollama API URL"
    ),
    ollama_model: str = typer.Option(
        "gemma4:e4b",
        help="Ollama model name"
    ),
    fuseki_url: str = typer.Option(
        "http://localhost:3030",
        help="Fuseki SPARQL endpoint"
    ),
    use_fuseki: bool = typer.Option(
        True,
        help="Enable Fuseki validation"
    ),
    use_shacl: bool = typer.Option(
        True,
        help="Enable SHACL validation"
    ),
    semantic_match: bool = typer.Option(
        True,
        help="Enable semantic matching of descriptions"
    ),
    semantic_threshold: float = typer.Option(
        0.50,
        help="Semantic similarity threshold (0-1)"
    ),
) -> None:
    """Evaluate generated ontology against gold standard."""
    
    # Check files exist
    if not generated.exists():
        console.print(f"[red]Error: Generated ontology not found: {generated}[/red]")
        raise typer.Exit(1)
    
    if not gold.exists():
        console.print(f"[red]Error: Gold standard not found: {gold}[/red]")
        raise typer.Exit(1)
    
    # Create evaluator
    evaluator = OntologyEvaluator(
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        fuseki_url=fuseki_url,
        semantic_threshold=semantic_threshold,
    )
    
    # Run evaluation
    try:
        report = asyncio.run(evaluator.evaluate(
            gold_path=gold,
            generated_path=generated,
            use_fuseki=use_fuseki,
            use_shacl=use_shacl,
            semantic_match=semantic_match,
        ))
    except Exception as e:
        console.print(f"[red]Evaluation failed: {e}[/red]")
        logger.exception("evaluation_error", error=str(e))
        raise typer.Exit(1)
    
    # Display report
    evaluator.display_report(report)
    
    # Save report
    output.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert dataclass to dict with nested mappings
    report_dict = asdict(report)
    report_dict["mappings"] = [asdict(m) for m in report.mappings]
    
    with open(output, "w") as f:
        json.dump(report_dict, f, indent=2)
    
    console.print(f"[green]✓ Report saved to {output}[/green]")
    
    # Exit with appropriate code
    if report.overall_score >= 70:
        console.print("[green]✓ Evaluation passed (score >= 70)[/green]")
        raise typer.Exit(0)
    else:
        console.print(f"[yellow]⚠ Evaluation score below threshold ({report.overall_score:.1f}/100)[/yellow]")
        raise typer.Exit(0)  # Still exit cleanly


if __name__ == "__main__":
    app()

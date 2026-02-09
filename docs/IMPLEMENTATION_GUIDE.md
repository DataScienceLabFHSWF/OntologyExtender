# OntologyExtender — Detailed Implementation Guide

> **Audience**: Developers implementing the remaining TODOs.  
> **Last updated**: 2026-02-09  
> **Total TODOs**: 15 across 10 modules (7 modules are already complete)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Infrastructure & Services](#2-infrastructure--services)
3. [Completed Modules (reference only)](#3-completed-modules)
4. [Implementation Priority Order](#4-implementation-priority-order)
5. [TODO 1 — `gap_analyzer._get_ontology_classes()`](#todo-1--gap_analyzer_get_ontology_classes)
6. [TODO 2 — `gap_analyzer._classify_entities()` (semantic matching)](#todo-2--gap_analyzer_classify_entities)
7. [TODO 3 — `gap_analyzer._build_gap_candidates()` (embedding grouping)](#todo-3--gap_analyzer_build_gap_candidates)
8. [TODO 4 — `class_generator._generate_single()` (LLM call)](#todo-4--class_generator_generate_single)
9. [TODO 5 — `class_generator._suggest_default_properties()` (LLM call)](#todo-5--class_generator_suggest_default_properties)
10. [TODO 6 — `relation_generator.suggest_relations()` (LLM call)](#todo-6--relation_generatorsuggest_relations)
11. [TODO 7 — `manager.export_owl()` (rdflib serialization)](#todo-7--managerexport_owl)
12. [TODO 8 — `manager.export_updated_cqs()`](#todo-8--managerexport_updated_cqs)
13. [TODO 9 — `shacl_generator.generate_shape()` (full SHACL)](#todo-9--shacl_generatorgenerate_shape)
14. [TODO 10-13 — `version_manager` (Fuseki graph ops)](#todo-10-13--version_manager)
15. [TODO 14 — `cq_evaluator.evaluate_coverage()` (SPARQL)](#todo-14--cq_evaluatorevaluate_coverage)
16. [TODO 15 — `completeness.measure_schema_coverage()`](#todo-15--completenessmeasure_schema_coverage)
17. [TODO 16 — `cli.review()` (Rich interactive loop)](#todo-16--clireview)
18. [TODO 17 — `web.py` (Streamlit dashboard)](#todo-17--webpy)
19. [W&B Logging Integration](#18-wandb-logging-integration)
20. [LLM Prompt Templates](#19-llm-prompt-templates)
21. [Fuseki SPARQL Reference](#20-fuseki-sparql-reference)
22. [Testing Strategy](#21-testing-strategy)

---

## 1. Project Overview

OntologyExtender takes the seed Planning Ontology (18 classes, 26 relations for AI planning research) and iteratively extends it with domain-specific concepts discovered from nuclear decommissioning documents. The pipeline:

```
KGB checkpoint → Gap Analysis → LLM Proposals → Expert Review → OWL Export → Re-extract
```

Each iteration should improve CQ answerability and entity coverage toward 80%+.

---

## 2. Infrastructure & Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **Ollama** | `ollama-ontology-extender` | `18135` | LLM inference (qwen3-next 79.7B Q4_K_M) |
| **Fuseki** (shared) | existing KGB fuseki | `3030` | Main ontology + KG store |
| **Fuseki** (staging) | `hitl-fuseki` | `3031` | Staging graphs for review |

### Ollama Configuration

- **Model**: `qwen3-next:latest` (79.7B params, Q4_K_M quantization, ~52 GB VRAM)
- **GPU**: 2× NVIDIA H200 NVL (143 GB VRAM each) — model fits entirely in VRAM
- **Caching**: `OLLAMA_KEEP_ALIVE=24h` — model stays loaded for 24 hours after last request
- **Parallelism**: `OLLAMA_NUM_PARALLEL=2` — 2 concurrent requests
- **Flash Attention**: `OLLAMA_FLASH_ATTENTION=1` — faster inference

### Key Endpoints

```
Ollama generate:  POST http://localhost:18135/api/generate
Ollama chat:      POST http://localhost:18135/api/chat
Fuseki SPARQL:    POST http://localhost:3030/{dataset}/sparql
Fuseki GSP:       PUT  http://localhost:3030/{dataset}/data?graph={uri}
```

### Calling Ollama (httpx pattern used throughout)

```python
import httpx

async def call_ollama(prompt: str, model: str = "qwen3-next") -> str:
    """Standard Ollama call pattern. Use for all LLM TODOs."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            "http://localhost:18135/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_predict": 2048, "temperature": 0.5},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
```

> **Note**: qwen3-next has a thinking mode. For structured JSON output, consider adding
> "think": false to skip internal reasoning (faster) or leave it on for better quality
> on complex ontology decisions. Thinking output is in `resp.json()["message"].get("thinking")`.

### Calling Fuseki (httpx pattern)

```python
import httpx

def sparql_query(query: str, dataset: str = "kgbuilder") -> list[dict]:
    """Standard Fuseki SPARQL query pattern."""
    resp = httpx.post(
        f"http://localhost:3030/{dataset}/sparql",
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        auth=("admin", "YOUR_PASSWORD"),  # from Settings
    )
    resp.raise_for_status()
    results = resp.json()["results"]["bindings"]
    return [{k: v["value"] for k, v in row.items()} for row in results]
```

---

## 3. Completed Modules

These are **done** — reference them for conventions and patterns but don't modify:

| Module | What it does |
|--------|-------------|
| `core/models.py` | 11 dataclasses: `ProposedClass`, `GapCandidate`, `ReviewDecision`, `GapReport`, etc. |
| `core/protocols.py` | 4 Protocol interfaces: `OntologyProvider`, `LLMProvider`, `CheckpointReader`, `ReviewBackend` |
| `core/config.py` | Pydantic `Settings` with `HITL_` env prefix, W&B config |
| `core/exceptions.py` | 6 typed exceptions with structured data |
| `review/feedback.py` | `FeedbackCollector` — saves/loads decisions JSON, computes agreement rate |
| `evaluation/reporter.py` | `IterationReporter.compare()` — loads two metric JSONs, computes deltas |
| `mapping/yarrrml_generator.py` | `YARRRMLGenerator` — full YARRRML generation from `ProposedClass` list |

---

## 4. Implementation Priority Order

Implement in this order (dependencies flow downward):

```
Week 1:  TODOs 1-3   (gap_analyzer — Fuseki + semantic matching)
Week 2:  TODOs 4-6   (class_generator + relation_generator — LLM calls)
Week 3:  TODOs 7-9   (schema manager + SHACL — rdflib export)
Week 4:  TODOs 10-13 (version_manager — Fuseki graph management)
Week 5:  TODOs 14-16 (evaluation + review CLI)
Week 6:  TODO 17     (Streamlit dashboard — optional)
```

---

## TODO 1 — `gap_analyzer._get_ontology_classes()`

**File**: `src/ontology_hitl/discovery/gap_analyzer.py`  
**Method**: `_get_ontology_classes(self) -> list[str]`  
**Current state**: Returns empty list `[]`  
**Difficulty**: Easy

### What to implement

Query Fuseki for all `owl:Class` labels in the current ontology graph.

### Exact implementation

```python
def _get_ontology_classes(self) -> list[str]:
    """Get all class labels from the current ontology via SPARQL."""
    import httpx

    query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX planning: <http://purl.org/2024/planning-ontology#>

    SELECT DISTINCT ?label WHERE {
        ?class a owl:Class .
        ?class rdfs:label ?label .
    }
    ORDER BY ?label
    """

    try:
        resp = httpx.post(
            f"{self.fuseki_url}/{self.dataset}/sparql",
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
        classes = [b["label"]["value"] for b in bindings]
        logger.info("ontology_classes_loaded", count=len(classes))
        return classes
    except httpx.HTTPError as e:
        logger.error("fuseki_query_failed", error=str(e))
        return []
```

### Testing

- Mock `httpx.post` to return SPARQL JSON with 3 class labels
- Verify empty list on connection error (graceful degradation)

---

## TODO 2 — `gap_analyzer._classify_entities()` (semantic matching)

**File**: `src/ontology_hitl/discovery/gap_analyzer.py`  
**Method**: `_classify_entities(self, entities, ontology_classes) -> tuple[list, list]`  
**Current state**: Exact string match only (`entity_type.lower() in ontology_set`)  
**Difficulty**: Medium

### What to implement

Add **semantic similarity** matching using Ollama embeddings so that entities like "Nuclear Facility" match ontology class "Facility".

### Strategy

1. Keep the fast exact-match as first pass.
2. For unmatched entities, compute embedding similarity against ontology class labels.
3. Use `self.similarity_threshold` (default 0.65) as cutoff.

### Implementation

```python
def _classify_entities(
    self,
    entities: list[ExtractedEntitySummary],
    ontology_classes: list[str],
) -> tuple[list[ExtractedEntitySummary], list[ExtractedEntitySummary]]:
    """Split entities into covered/uncovered using exact + semantic match."""
    import httpx

    covered: list[ExtractedEntitySummary] = []
    uncovered: list[ExtractedEntitySummary] = []

    ontology_set = {c.lower() for c in ontology_classes}

    # Phase 1: exact match
    needs_semantic: list[ExtractedEntitySummary] = []
    for entity in entities:
        if entity.entity_type.lower() in ontology_set:
            covered.append(entity)
        else:
            needs_semantic.append(entity)

    if not needs_semantic or not ontology_classes:
        return covered, needs_semantic

    # Phase 2: semantic similarity via Ollama embeddings
    try:
        class_embeddings = self._get_embeddings(ontology_classes)
        for entity in needs_semantic:
            entity_emb = self._get_embeddings([entity.entity_type])[0]
            max_sim = max(
                self._cosine_similarity(entity_emb, ce)
                for ce in class_embeddings
            )
            if max_sim >= self.similarity_threshold:
                covered.append(entity)
                logger.debug("semantic_match", entity=entity.entity_type, sim=max_sim)
            else:
                uncovered.append(entity)
    except Exception as e:
        logger.warning("semantic_matching_failed", error=str(e))
        uncovered.extend(needs_semantic)

    return covered, uncovered

def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
    """Get embeddings from Ollama."""
    import httpx
    embeddings = []
    for text in texts:
        resp = httpx.post(
            f"{self.fuseki_url.replace(':3030', ':18135')}/api/embed",
            json={"model": "qwen3-next", "input": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        embeddings.append(resp.json()["embeddings"][0])
    return embeddings

@staticmethod
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
```

### Design decisions

- Use `self.fuseki_url` to derive Ollama URL — or better yet, accept `ollama_url` in constructor. **Consider adding `ollama_url` param to `__init__`** from `Settings`.
- For embedding model: Check if `qwen3-next` supports `/api/embed`. If not, pull a dedicated embedding model (`nomic-embed-text` or `qwen3-embedding`).
- Batch embeddings where possible for performance.

### Testing

- Mock the embedding endpoint to return known vectors
- Test that exact matches bypass semantic phase
- Test threshold boundary (sim = 0.64 → uncovered, 0.65 → covered)

---

## TODO 3 — `gap_analyzer._build_gap_candidates()` (embedding grouping)

**File**: `src/ontology_hitl/discovery/gap_analyzer.py`  
**Method**: `_build_gap_candidates(self, uncovered) -> list[GapCandidate]`  
**Current state**: Groups only by exact `entity_type` string  
**Difficulty**: Medium

### What to implement

Group semantically similar uncovered entities together, even if they have different `entity_type` strings (e.g., "Nuclear Plant" and "Power Station" → same gap candidate).

### Implementation sketch

```python
def _build_gap_candidates(
    self,
    uncovered: list[ExtractedEntitySummary],
) -> list[GapCandidate]:
    """Group uncovered entities into gap candidates using semantic clustering."""
    from collections import defaultdict

    # Step 1: group by exact entity_type (fast path)
    type_groups: dict[str, list[ExtractedEntitySummary]] = defaultdict(list)
    for entity in uncovered:
        type_groups[entity.entity_type].append(entity)

    # Step 2: merge semantically similar groups
    #   Get embedding for each entity_type key
    #   If cosine_similarity(type_A, type_B) > 0.8, merge groups
    group_keys = list(type_groups.keys())
    if len(group_keys) > 1:
        try:
            embeddings = self._get_embeddings(group_keys)
            merged = self._merge_similar_groups(
                group_keys, embeddings, type_groups, threshold=0.80
            )
            type_groups = merged
        except Exception as e:
            logger.warning("group_merging_failed", error=str(e))

    # Step 3: filter by min_frequency and build candidates
    candidates: list[GapCandidate] = []
    for entity_type, group in type_groups.items():
        freq = len(group)
        if freq < self.min_frequency:
            continue
        candidates.append(
            GapCandidate(
                entity_type=entity_type,
                representative_label=group[0].label,
                examples=[e.label for e in group[:5]],
                frequency=freq,
                avg_confidence=sum(e.confidence for e in group) / freq,
            )
        )

    candidates.sort(key=lambda c: c.frequency, reverse=True)
    return candidates

def _merge_similar_groups(
    self,
    keys: list[str],
    embeddings: list[list[float]],
    groups: dict[str, list],
    threshold: float,
) -> dict[str, list]:
    """Merge groups whose type labels are semantically similar."""
    merged: dict[str, list] = {}
    used = set()
    for i, key_i in enumerate(keys):
        if key_i in used:
            continue
        merged[key_i] = list(groups[key_i])
        for j in range(i + 1, len(keys)):
            key_j = keys[j]
            if key_j in used:
                continue
            sim = self._cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                merged[key_i].extend(groups[key_j])
                used.add(key_j)
                logger.info("merged_groups", a=key_i, b=key_j, sim=f"{sim:.3f}")
        used.add(key_i)
    return merged
```

---

## TODO 4 — `class_generator._generate_single()` (LLM call)

**File**: `src/ontology_hitl/discovery/class_generator.py`  
**Method**: `_generate_single(self, proposal_id, entity_type, examples, frequency, avg_confidence) -> ProposedClass`  
**Current state**: Returns static placeholder with hard-coded parent "DomainConstant"  
**Difficulty**: Medium-High

### What to implement

Call Ollama to generate a structured class definition, then parse the JSON response.

### Constructor update needed

The constructor currently uses old defaults (`ollama_url=18134`, `model=qwen3:8b`). It should read from `Settings`:

```python
def __init__(self, settings: Settings | None = None) -> None:
    from ontology_hitl.core.config import Settings
    s = settings or Settings()
    self.ollama_url = s.ollama_url
    self.model = s.ollama_model
    self.fuseki_url = s.fuseki_url
    self.dataset = s.fuseki_dataset
    self.temperature = s.llm_temperature
```

### Implementation

```python
def _generate_single(
    self,
    proposal_id: str,
    entity_type: str,
    examples: list[str],
    frequency: int,
    avg_confidence: float,
) -> ProposedClass:
    """Generate a single class proposal via LLM."""
    import httpx
    import json as json_mod

    # Build prompt (see Section 19 for full template)
    prompt = self._build_class_prompt(entity_type, examples)

    try:
        resp = httpx.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": CLASS_GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": self.temperature,
                    "num_predict": 1024,
                },
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json_mod.loads(content)

        return ProposedClass(
            id=proposal_id,
            label=parsed.get("label", entity_type),
            definition=parsed.get("definition", f"A {entity_type}."),
            parent_uri=parsed.get("parent_uri", "http://purl.org/2024/planning-ontology#DomainConstant"),
            parent_label=parsed.get("parent_label", "DomainConstant"),
            examples=examples,
            frequency=frequency,
            confidence=avg_confidence,
            suggested_properties=[
                PropertyDef(**p) for p in parsed.get("properties", [])
            ],
            source_gap_candidates=[entity_type],
        )
    except Exception as e:
        logger.error("llm_class_generation_failed", entity=entity_type, error=str(e))
        # Fallback to placeholder
        return ProposedClass(
            id=proposal_id,
            label=entity_type,
            definition=f"A {entity_type} in the nuclear decommissioning domain.",
            parent_uri="http://purl.org/2024/planning-ontology#DomainConstant",
            parent_label="DomainConstant",
            examples=examples,
            frequency=frequency,
            confidence=avg_confidence,
            suggested_properties=self._suggest_default_properties(entity_type),
            source_gap_candidates=[entity_type],
        )
```

See [Section 19](#19-llm-prompt-templates) for the full `CLASS_GENERATION_SYSTEM_PROMPT` and `_build_class_prompt()`.

---

## TODO 5 — `class_generator._suggest_default_properties()` (LLM call)

**File**: `src/ontology_hitl/discovery/class_generator.py`  
**Method**: `_suggest_default_properties(self, entity_type) -> list[PropertyDef]`  
**Current state**: Returns 2 hard-coded props (label, description)  
**Difficulty**: Medium

### What to implement

Call the LLM to suggest domain-specific properties for the entity type.

```python
def _suggest_default_properties(self, entity_type: str) -> list[PropertyDef]:
    """Generate domain-specific properties for entity type via LLM."""
    import httpx
    import json as json_mod

    prompt = f"""Suggest 3-6 datatype properties for the OWL class "{entity_type}"
in a nuclear decommissioning ontology. Return JSON array:
[{{"name": "propertyName", "datatype": "xsd:string", "description": "...", "required": true/false, "max_count": null}}]

Always include rdfs:label (required, max 1) and rdfs:comment (optional).
Use XSD datatypes: xsd:string, xsd:integer, xsd:decimal, xsd:date, xsd:boolean."""

    try:
        resp = httpx.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {"temperature": self.temperature, "num_predict": 512},
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        parsed = json_mod.loads(resp.json()["message"]["content"])
        if isinstance(parsed, list):
            return [PropertyDef(**p) for p in parsed]
    except Exception as e:
        logger.warning("property_suggestion_fallback", error=str(e))

    # Fallback
    return [
        PropertyDef(name="label", datatype="xsd:string",
                    description=f"Human-readable label.", required=True, max_count=1),
        PropertyDef(name="description", datatype="xsd:string",
                    description=f"Description.", required=False),
    ]
```

---

## TODO 6 — `relation_generator.suggest_relations()` (LLM call)

**File**: `src/ontology_hitl/discovery/relation_generator.py`  
**Method**: `suggest_relations(self, proposed_class, existing_classes) -> list[RelationDef]`  
**Current state**: Returns empty list `[]`  
**Difficulty**: Medium

### Constructor update needed

Same as class_generator — update defaults to use `Settings`.

### Implementation

```python
def suggest_relations(
    self,
    proposed_class: ProposedClass,
    existing_classes: list[str],
) -> list[RelationDef]:
    """Suggest ObjectProperty relations via LLM."""
    import httpx
    import json as json_mod

    if not existing_classes:
        return []

    class_list = ", ".join(existing_classes[:30])  # Cap to avoid huge prompts
    prompt = f"""Given the new ontology class "{proposed_class.label}" (definition: {proposed_class.definition})
and these existing classes: [{class_list}],
suggest 2-5 ObjectProperty relations connecting them.

Return JSON array:
[{{
  "name": "relationName",
  "domain": "{proposed_class.label}",
  "range": "ExistingClassName",
  "description": "What this relation means",
  "inverse_name": "inverseRelationName or null",
  "cardinality": "0..*"
}}]

Use meaningful camelCase names (e.g., requiresPermit, locatedAt, managedBy).
Only suggest relations that make semantic sense in nuclear decommissioning."""

    try:
        resp = httpx.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {"temperature": self.temperature, "num_predict": 1024},
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json_mod.loads(content)

        relations = []
        items = parsed if isinstance(parsed, list) else parsed.get("relations", [])
        for r in items:
            relations.append(RelationDef(
                name=r["name"],
                domain=r.get("domain", proposed_class.label),
                range=r["range"],
                description=r.get("description", ""),
                inverse_name=r.get("inverse_name"),
                cardinality=r.get("cardinality", "0..*"),
            ))
        logger.info("relations_suggested", cls=proposed_class.label, count=len(relations))
        return relations
    except Exception as e:
        logger.error("relation_suggestion_failed", cls=proposed_class.label, error=str(e))
        return []
```

---

## TODO 7 — `manager.export_owl()` (rdflib serialization)

**File**: `src/ontology_hitl/schema/manager.py`  
**Method**: `export_owl(self, output_path) -> None`  
**Current state**: `raise NotImplementedError`  
**Difficulty**: Medium

### What to implement

Load the seed ontology, add accepted classes as `owl:Class` with `rdfs:subClassOf`, properties, and relations, then serialize as OWL/XML.

```python
def export_owl(self, output_path: Path | str) -> None:
    """Export extended ontology as OWL/XML using rdflib."""
    from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS, OWL, XSD

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load seed ontology
    g = Graph()
    if self.seed_ontology_path.exists():
        g.parse(str(self.seed_ontology_path))

    EX = Namespace("http://example.org/ontology#")
    PLANNING = Namespace("http://purl.org/2024/planning-ontology#")
    g.bind("ex", EX)
    g.bind("planning", PLANNING)

    for cls in self._accepted_classes:
        class_uri = EX[cls.label.replace(" ", "")]
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.label, Literal(cls.label, lang="en")))
        g.add((class_uri, RDFS.comment, Literal(cls.definition, lang="en")))

        # Parent class
        if cls.parent_uri:
            g.add((class_uri, RDFS.subClassOf, URIRef(cls.parent_uri)))

        # Datatype properties
        for prop in cls.suggested_properties:
            prop_uri = EX[prop.name]
            g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.domain, class_uri))
            g.add((prop_uri, RDFS.label, Literal(prop.name)))
            g.add((prop_uri, RDFS.comment, Literal(prop.description)))

        # Object properties (relations)
        for rel in cls.suggested_relations:
            rel_uri = EX[rel.name]
            g.add((rel_uri, RDF.type, OWL.ObjectProperty))
            g.add((rel_uri, RDFS.domain, class_uri))
            g.add((rel_uri, RDFS.range, EX[rel.range.replace(" ", "")]))
            g.add((rel_uri, RDFS.label, Literal(rel.name)))
            g.add((rel_uri, RDFS.comment, Literal(rel.description)))
            if rel.inverse_name:
                inv_uri = EX[rel.inverse_name]
                g.add((inv_uri, OWL.inverseOf, rel_uri))

    g.serialize(str(output_path), format="xml")
    logger.info("owl_exported", path=str(output_path), triples=len(g))
```

---

## TODO 8 — `manager.export_updated_cqs()`

**File**: `src/ontology_hitl/schema/manager.py`  
**Method**: `export_updated_cqs(self, output_path) -> None`  
**Current state**: `raise NotImplementedError`  
**Difficulty**: Easy

### What to implement

Read existing CQs from `data/evaluation/competency_questions.json`, add new CQs derived from accepted classes, write updated file.

```python
def export_updated_cqs(self, output_path: Path | str) -> None:
    """Export updated competency questions with new entries from accepted classes."""
    import json as json_mod

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing CQs
    cq_source = Path("data/evaluation/competency_questions.json")
    existing_cqs = []
    if cq_source.exists():
        with open(cq_source) as f:
            existing_cqs = json_mod.load(f)

    # Generate new CQs from accepted classes
    max_id = max(
        (int(cq["id"].split("_")[1]) for cq in existing_cqs if "id" in cq),
        default=0,
    )

    for cls in self._accepted_classes:
        max_id += 1
        new_cq = {
            "id": f"CQ_{max_id:03d}",
            "question": f"What are the key properties and relationships of {cls.label}?",
            "expected_entity_types": [cls.label],
            "expected_relations": [r.name for r in cls.suggested_relations],
            "difficulty": 3,
            "priority": 2,
            "added_in_iteration": "auto",
        }
        existing_cqs.append(new_cq)

    with open(output_path, "w") as f:
        json_mod.dump(existing_cqs, f, indent=2)

    logger.info("cqs_exported", path=str(output_path), total=len(existing_cqs))
```

---

## TODO 9 — `shacl_generator.generate_shape()` (full SHACL)

**File**: `src/ontology_hitl/schema/shacl_generator.py`  
**Method**: `generate_shape(self, proposed_class) -> str`  
**Current state**: Basic Turtle without proper prefixes or descriptions  
**Difficulty**: Easy-Medium

### What to implement

Generate a complete SHACL NodeShape with proper prefixes, `sh:description`, and relation constraints.

```python
def generate_shape(self, proposed_class: ProposedClass) -> str:
    """Generate a complete SHACL NodeShape as Turtle."""
    label = proposed_class.label.replace(" ", "")

    lines = [
        "@prefix sh: <http://www.w3.org/ns/shacl#> .",
        "@prefix ex: <http://example.org/ontology#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "",
        f"ex:{label}Shape",
        f"    a sh:NodeShape ;",
        f"    sh:targetClass ex:{label} ;",
        f'    sh:description "{proposed_class.definition}" ;',
    ]

    # Datatype properties
    for prop in proposed_class.suggested_properties:
        lines.append(f"    sh:property [")
        lines.append(f"        sh:path ex:{prop.name} ;")
        lines.append(f'        sh:name "{prop.name}" ;')
        lines.append(f'        sh:description "{prop.description}" ;')
        if prop.required:
            lines.append(f"        sh:minCount 1 ;")
        if prop.max_count is not None:
            lines.append(f"        sh:maxCount {prop.max_count} ;")
        # Map datatype
        dt = prop.datatype
        if dt.startswith("xsd:"):
            lines.append(f"        sh:datatype {dt} ;")
        else:
            lines.append(f"        sh:datatype xsd:string ;")
        lines.append(f"    ] ;")

    # Object property constraints (relations)
    for rel in proposed_class.suggested_relations:
        range_label = rel.range.replace(" ", "")
        lines.append(f"    sh:property [")
        lines.append(f"        sh:path ex:{rel.name} ;")
        lines.append(f'        sh:name "{rel.name}" ;')
        lines.append(f'        sh:description "{rel.description}" ;')
        lines.append(f"        sh:class ex:{range_label} ;")
        # Parse cardinality
        if rel.cardinality == "1..1":
            lines.append(f"        sh:minCount 1 ;")
            lines.append(f"        sh:maxCount 1 ;")
        elif rel.cardinality == "0..1":
            lines.append(f"        sh:maxCount 1 ;")
        elif rel.cardinality == "1..*":
            lines.append(f"        sh:minCount 1 ;")
        lines.append(f"    ] ;")

    # Close shape
    if lines[-1].endswith(";"):
        lines[-1] = lines[-1][:-1] + "."
    else:
        lines.append("    .")

    return "\n".join(lines) + "\n"
```

---

## TODO 10-13 — `version_manager` (Fuseki graph operations)

**File**: `src/ontology_hitl/schema/version_manager.py`  
**4 methods** to implement, all using Fuseki Graph Store Protocol

### TODO 10: `create_version()`

Replace the stub with actual Fuseki graph creation:

```python
def create_version(self, version_id: str, parent_version: str | None = None, notes: str = "") -> OntologyVersion:
    """Create a new named graph in Fuseki for this version."""
    import httpx

    graph_uri = f"urn:ontology:{self.staging_prefix}-{version_id}"

    # Create empty graph via GSP PUT
    resp = httpx.put(
        f"{self.fuseki_url}/{self.main_dataset}/data",
        params={"graph": graph_uri},
        content=b"",  # Empty graph
        headers={"Content-Type": "text/turtle"},
        timeout=30.0,
    )
    # 200 or 201 both acceptable
    logger.info("fuseki_graph_created", graph=graph_uri, status=resp.status_code)

    version = OntologyVersion(
        version_id=version_id,
        parent_version=parent_version,
        notes=notes,
    )
    self._versions.append(version)
    return version
```

### TODO 11: `compute_diff()`

```python
def compute_diff(self, from_version: str, to_version: str) -> OntologyDiff:
    """Compute class/relation differences via SPARQL."""
    import httpx

    def get_classes(graph_uri: str) -> set[str]:
        query = f"""
        SELECT ?label WHERE {{
            GRAPH <{graph_uri}> {{
                ?c a <http://www.w3.org/2002/07/owl#Class> ;
                   <http://www.w3.org/2000/01/rdf-schema#label> ?label .
            }}
        }}
        """
        resp = httpx.post(
            f"{self.fuseki_url}/{self.main_dataset}/sparql",
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return {b["label"]["value"] for b in resp.json()["results"]["bindings"]}

    from_uri = f"urn:ontology:{self.staging_prefix}-{from_version}"
    to_uri = f"urn:ontology:{self.staging_prefix}-{to_version}"

    from_classes = get_classes(from_uri)
    to_classes = get_classes(to_uri)

    return OntologyDiff(
        from_version=from_version,
        to_version=to_version,
        added_classes=sorted(to_classes - from_classes),
        removed_classes=sorted(from_classes - to_classes),
    )
```

### TODO 12: `promote_staging_to_main()`

```python
def promote_staging_to_main(self, version_id: str) -> None:
    """Copy staging graph triples into the main default graph."""
    import httpx

    staging_uri = f"urn:ontology:{self.staging_prefix}-{version_id}"
    query = f"""
    INSERT {{ ?s ?p ?o }}
    WHERE {{ GRAPH <{staging_uri}> {{ ?s ?p ?o }} }}
    """
    resp = httpx.post(
        f"{self.fuseki_url}/{self.main_dataset}/update",
        data={"update": query},
        timeout=60.0,
    )
    resp.raise_for_status()
    logger.info("staging_promoted", version=version_id)
```

### TODO 13: `create_snapshot()`

```python
def create_snapshot(self, label: str | None = None) -> str:
    """Create a timestamped copy of the main graph."""
    import httpx
    from datetime import datetime

    snapshot_name = label or f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    snapshot_uri = f"urn:ontology:{snapshot_name}"

    query = f"""
    COPY DEFAULT TO <{snapshot_uri}>
    """
    resp = httpx.post(
        f"{self.fuseki_url}/{self.main_dataset}/update",
        data={"update": query},
        timeout=60.0,
    )
    resp.raise_for_status()
    logger.info("snapshot_created", name=snapshot_name)
    return snapshot_name
```

---

## TODO 14 — `cq_evaluator.evaluate_coverage()` (SPARQL)

**File**: `src/ontology_hitl/evaluation/cq_evaluator.py`  
**Method**: `evaluate_coverage(self, cq_path) -> dict`  
**Current state**: Returns zeros  
**Difficulty**: Medium

### What to implement

Load CQs, convert each to a SPARQL query, execute against Fuseki, measure answerability.

```python
def evaluate_coverage(self, cq_path: str) -> dict:
    """Evaluate CQ answerability against the graph."""
    import json as json_mod
    import httpx

    with open(cq_path) as f:
        cqs = json_mod.load(f)

    results = []
    answerable = 0

    for cq in cqs:
        cq_id = cq["id"]
        expected_types = cq.get("expected_entity_types", [])
        expected_rels = cq.get("expected_relations", [])

        # Check: do expected entity types exist as classes?
        type_found = 0
        for etype in expected_types:
            query = f"""
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            ASK {{
                ?c a owl:Class ; rdfs:label ?l .
                FILTER(CONTAINS(LCASE(?l), LCASE("{etype}")))
            }}
            """
            try:
                resp = httpx.post(
                    f"{self.fuseki_url}/{self.dataset}/sparql",
                    data={"query": query},
                    headers={"Accept": "application/sparql-results+json"},
                    timeout=15.0,
                )
                if resp.json().get("boolean", False):
                    type_found += 1
            except Exception:
                pass

        # Check: do expected relations exist as properties?
        rel_found = 0
        for rel in expected_rels:
            query = f"""
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            ASK {{
                ?p a owl:ObjectProperty ; rdfs:label ?l .
                FILTER(CONTAINS(LCASE(?l), LCASE("{rel}")))
            }}
            """
            try:
                resp = httpx.post(
                    f"{self.fuseki_url}/{self.dataset}/sparql",
                    data={"query": query},
                    headers={"Accept": "application/sparql-results+json"},
                    timeout=15.0,
                )
                if resp.json().get("boolean", False):
                    rel_found += 1
            except Exception:
                pass

        total_expected = len(expected_types) + len(expected_rels)
        total_found = type_found + rel_found
        is_answerable = total_found >= (total_expected * 0.5) if total_expected else False

        if is_answerable:
            answerable += 1

        results.append({
            "cq_id": cq_id,
            "answerable": is_answerable,
            "types_found": type_found,
            "types_expected": len(expected_types),
            "relations_found": rel_found,
            "relations_expected": len(expected_rels),
        })

    total = len(cqs)
    return {
        "total_cqs": total,
        "answerable": answerable,
        "coverage_pct": answerable / total if total else 0.0,
        "results": results,
    }
```

---

## TODO 15 — `completeness.measure_schema_coverage()`

**File**: `src/ontology_hitl/evaluation/completeness.py`  
**Current state**: Returns zeros  
**Difficulty**: Medium

### What to implement

Load checkpoint entities, compare entity types against ontology classes to measure what percentage of entity types have matching classes.

```python
def measure_schema_coverage(self, checkpoint_path: str) -> dict:
    """Measure entity-type-to-ontology-class coverage."""
    import json as json_mod
    import httpx

    # Load entities from checkpoint
    with open(checkpoint_path) as f:
        data = json_mod.load(f)
    entities = data.get("entities", [])

    # Get ontology classes
    query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?label WHERE { ?c a owl:Class ; rdfs:label ?label . }
    """
    try:
        resp = httpx.post(
            f"{self.fuseki_url}/{self.dataset}/sparql",
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        class_labels = {
            b["label"]["value"].lower()
            for b in resp.json()["results"]["bindings"]
        }
    except Exception:
        class_labels = set()

    # Classify each entity
    covered = 0
    total = len(entities)
    for ent in entities:
        etype = ent.get("entity_type", "").lower()
        if etype in class_labels:
            covered += 1

    gap = total - covered
    return {
        "covered_entities": covered,
        "total_entities": total,
        "coverage_pct": covered / total if total else 0.0,
        "gap_entities": gap,
    }
```

---

## TODO 16 — `cli.review()` (Rich interactive loop)

**File**: `src/ontology_hitl/review/cli.py`  
**Current state**: Prints placeholder text  
**Difficulty**: Medium

### What to implement

Interactive Rich-based review loop that displays each proposal and collects accept/reject/revise.

```python
@app.command()
def review(
    proposals: str = typer.Option(..., help="Path to proposals JSON"),
    output: str = typer.Option("decisions.json", help="Output decisions JSON"),
    reviewer: str = typer.Option("expert", help="Reviewer name"),
) -> None:
    """Interactive review session for proposed ontology classes."""
    import json
    from pathlib import Path
    from datetime import datetime
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt

    path = Path(proposals)
    if not path.exists():
        console.print(f"[red]Proposals file not found: {proposals}[/red]")
        raise typer.Exit(1)

    with open(path) as f:
        props = json.load(f)

    console.print(f"\n[bold blue]Ontology Extension Review[/bold blue]")
    console.print(f"  Reviewer: {reviewer}")
    console.print(f"  Proposals: {len(props)}\n")

    decisions = []
    for i, prop in enumerate(props, 1):
        # Display proposal
        table = Table(title=f"Proposal {i}/{len(props)}: {prop.get('label', '?')}")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("ID", prop.get("id", ""))
        table.add_row("Label", prop.get("label", ""))
        table.add_row("Definition", prop.get("definition", ""))
        table.add_row("Parent", prop.get("parent_label", ""))
        table.add_row("Frequency", str(prop.get("frequency", 0)))
        table.add_row("Confidence", f"{prop.get('confidence', 0):.2f}")
        table.add_row("Examples", ", ".join(prop.get("examples", [])[:5]))

        props_list = prop.get("suggested_properties", [])
        if props_list:
            table.add_row("Properties", ", ".join(
                p.get("name", "") if isinstance(p, dict) else p.name
                for p in props_list
            ))

        console.print(Panel(table))

        # Collect decision
        choice = Prompt.ask(
            "[bold]Decision[/bold]",
            choices=["accept", "reject", "revise", "skip"],
            default="accept",
        )

        if choice == "skip":
            continue

        rationale = ""
        if choice in ("reject", "revise"):
            rationale = Prompt.ask("Rationale", default="")

        decisions.append({
            "proposal_id": prop.get("id", f"prop_{i}"),
            "reviewer": reviewer,
            "decision": choice,
            "rationale": rationale,
            "timestamp": datetime.now().isoformat(),
            "confidence": 0.8 if choice == "accept" else 0.5,
        })

    # Save
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(decisions, f, indent=2)

    accepted = sum(1 for d in decisions if d["decision"] == "accept")
    console.print(f"\n[bold green]Done![/bold green] {accepted}/{len(decisions)} accepted → {output}")
```

---

## TODO 17 — `web.py` (Streamlit dashboard)

**File**: `src/ontology_hitl/review/web.py`  
**Priority**: Low (optional, CLI works first)  
**Difficulty**: Medium

This is a nice-to-have web alternative. Implement after the CLI is stable. Use Streamlit with `st.data_editor` for batch review.

---

## 18. W&B Logging Integration

The project is configured to log to the **`ontology-hitl`** W&B project (separate from `kg-builder`).

### Config (already set in `.env`)

```
HITL_WANDB_ENABLED=true
HITL_WANDB_ENTITY=dsfhswf
HITL_WANDB_PROJECT=ontology-hitl
```

### Usage pattern for scripts

```python
from ontology_hitl.core.config import Settings

settings = Settings()

if settings.wandb_enabled:
    import wandb
    wandb.init(
        project=settings.wandb_project,
        entity=settings.wandb_entity,
        config={
            "iteration": "v1",
            "model": settings.ollama_model,
            "min_frequency": settings.min_entity_frequency,
            "similarity_threshold": settings.semantic_similarity_threshold,
        },
    )

# After gap analysis:
if settings.wandb_enabled:
    wandb.log({
        "gap/total_entities": report.total_extracted_entities,
        "gap/covered": report.covered_entities,
        "gap/coverage_pct": report.coverage_pct,
        "gap/candidates": len(report.gap_candidates),
    })

# After evaluation:
if settings.wandb_enabled:
    wandb.log({
        "eval/cq_coverage": cq_result["coverage_pct"],
        "eval/entity_coverage": coverage_result["coverage_pct"],
    })
    wandb.finish()
```

### What to log per iteration

| Metric | W&B key | Source |
|--------|---------|--------|
| Entity coverage % | `gap/coverage_pct` | GapReport |
| Gap candidates count | `gap/candidates` | GapReport |
| Proposals generated | `proposals/count` | ClassGenerator |
| Proposals accepted | `review/accepted` | FeedbackCollector |
| CQ answerability | `eval/cq_coverage` | CQEvaluator |
| Schema coverage | `eval/entity_coverage` | CompletenessAnalyzer |
| LLM latency | `llm/latency_s` | httpx timings |

---

## 19. LLM Prompt Templates

### System prompt for class generation (TODO 4)

```python
CLASS_GENERATION_SYSTEM_PROMPT = """You are an ontology engineer specializing in nuclear decommissioning.
You help extend the Planning Ontology (https://github.com/BharathMuppasani/AI-Planning-Ontology)
with domain-specific classes discovered from German decommissioning documents.

The seed ontology has these top-level classes:
- DomainConstant (physical objects, resources)
- DomainPredicate (states, conditions)
- Action (activities, processes)
- Goal (objectives, targets)
- Plan (strategies, schedules)

When defining a new class, you MUST return valid JSON with exactly these fields:
{
  "label": "ClassName",
  "definition": "A clear, concise definition (1-2 sentences).",
  "parent_uri": "http://purl.org/2024/planning-ontology#ParentClass",
  "parent_label": "ParentClass",
  "properties": [
    {"name": "propName", "datatype": "xsd:string", "description": "...", "required": true, "max_count": 1}
  ]
}

Choose the most appropriate parent class from the seed ontology.
Use English labels with CamelCase naming."""
```

### User prompt builder

```python
def _build_class_prompt(self, entity_type: str, examples: list[str]) -> str:
    examples_str = ", ".join(f'"{e}"' for e in examples[:5])
    return f"""Define a new OWL class for the entity type "{entity_type}".

Example instances from documents: [{examples_str}]

Return JSON with: label, definition, parent_uri, parent_label, properties (3-6 datatype properties).
The class should fit into the nuclear decommissioning planning domain."""
```

---

## 20. Fuseki SPARQL Reference

### Get all classes

```sparql
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?class ?label WHERE {
    ?class a owl:Class .
    OPTIONAL { ?class rdfs:label ?label }
}
```

### Get class hierarchy

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?child ?parent WHERE {
    ?child rdfs:subClassOf ?parent .
}
```

### Count instances per class

```sparql
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?class (COUNT(?inst) AS ?count) WHERE {
    ?inst rdf:type ?class .
}
GROUP BY ?class ORDER BY DESC(?count)
```

### ASK if a class exists

```sparql
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
ASK {
    ?c a owl:Class ; rdfs:label "Facility"@en .
}
```

### Graph Store Protocol — upload Turtle

```bash
curl -X PUT \
  'http://localhost:3030/kgbuilder/data?graph=urn:ontology:staging-v1' \
  -H 'Content-Type: text/turtle' \
  --data-binary @shapes.ttl
```

---

## 21. Testing Strategy

### Existing tests (22 passing)

All in `tests/` — run with `pytest -v`.

### Tests to add for each TODO

| TODO | Test file | Key assertions |
|------|-----------|----------------|
| 1 | `tests/discovery/test_gap_analyzer.py` | Mock httpx → SPARQL returns classes; handle connection error |
| 2-3 | same | Mock embeddings; test threshold boundary; test group merging |
| 4-5 | `tests/discovery/test_class_generator.py` | Mock LLM JSON response; test fallback on error; validate ProposedClass fields |
| 6 | `tests/discovery/test_relation_generator.py` | Mock LLM; test empty existing_classes; validate RelationDef fields |
| 7 | `tests/schema/test_manager.py` | Write OWL, parse back with rdflib, verify triples |
| 8 | same | Verify CQ JSON has new entries |
| 9 | `tests/schema/test_shacl_generator.py` | Parse output Turtle, verify sh:targetClass, sh:property present |
| 10-13 | `tests/schema/test_version_manager.py` | Mock Fuseki HTTP calls; verify URIs and SPARQL |
| 14 | `tests/evaluation/test_cq_evaluator.py` | Mock SPARQL ASK responses; verify coverage calculation |
| 15 | `tests/evaluation/test_completeness.py` | Mock SPARQL + checkpoint; verify counts |
| 16 | `tests/review/test_cli.py` | Use `typer.testing.CliRunner`; mock stdin input |

### Mock pattern for httpx

```python
from unittest.mock import patch, MagicMock

def test_get_ontology_classes():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": {"bindings": [
            {"label": {"value": "Facility"}},
            {"label": {"value": "Permit"}},
        ]}
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        analyzer = OntologyGapAnalyzer()
        classes = analyzer._get_ontology_classes()
        assert classes == ["Facility", "Permit"]
```

---

## Appendix: File → TODO Quick Reference

| File | TODO IDs | Status |
|------|----------|--------|
| `discovery/gap_analyzer.py` | 1, 2, 3 | Partial |
| `discovery/class_generator.py` | 4, 5 | Stub |
| `discovery/relation_generator.py` | 6 | Stub |
| `schema/manager.py` | 7, 8 | Partial |
| `schema/shacl_generator.py` | 9 | Partial |
| `schema/version_manager.py` | 10, 11, 12, 13 | Stub |
| `evaluation/cq_evaluator.py` | 14 | Stub |
| `evaluation/completeness.py` | 15 | Stub |
| `review/cli.py` | 16 | Partial |
| `review/web.py` | 17 | Stub (optional) |

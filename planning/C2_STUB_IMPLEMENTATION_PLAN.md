# C2 — Stub Implementation Plan

> Detailed implementation guide for the 10 remaining stub modules.
> Designed so smaller GitHub Copilot models can fill in the TODOs
> with strict, step-by-step instructions.

## Cross-Reference: KnowledgeGraphBuilder Patterns

The sibling repository `DataScienceLabFHSWF/KnowledgeGraphBuilder` provides
reference implementations for several patterns we reuse here:

| KGB Pattern | Source File | What We Adopt |
|---|---|---|
| **FusionRAG** | `src/kgbuilder/retrieval/__init__.py` | Dense+Sparse retrieval, fusion scoring, query expansion |
| **FusekiOntologyService** | `src/kgbuilder/storage/ontology.py` | SPARQL queries for `owl:Class`, `owl:ObjectProperty`, `owl:DatatypeProperty` |
| **OntologyClassDef** | `src/kgbuilder/extraction/entity.py` | URI, label, description, examples, properties |
| **OntologyRelationDef** | `src/kgbuilder/extraction/schemas.py` | URI, label, domain, range, cardinality |
| **Structured LLM Output** | `src/kgbuilder/extraction/chains.py` | JSON schema in prompt → Pydantic validation |
| **KG Node Schema** | `Planning/IMPLEMENTATION_PLAN_V2.md §3.1` | id, label, entity_type, confidence, description, embedding, CQs |
| **KG Edge Schema** | `Planning/IMPLEMENTATION_PLAN_V2.md §3.2` | source, target, predicate, confidence, domain_type, cardinality |

## Infrastructure

| Service | URL | Purpose |
|---|---|---|
| Fuseki (main) | `http://localhost:3030` | Ontology RDF store (OWL classes, SPARQL) |
| Fuseki (staging) | `http://localhost:3031` | Staging ontology for in-flight extensions |
| Qdrant | `http://localhost:6333` | Document vector store (shared with KGB) |
| Ollama (ontology-extender) | `http://localhost:18135` | qwen3-next 79.7B Q4_K_M (H200 GPU) |
| Ollama (kg-builder) | `http://localhost:18134` | Shared LLM for KGB |

## Stub Modules — Implementation Priority

### Tier 1: Core Pipeline (blocks everything)

| # | Module | File | Depends On |
|---|---|---|---|
| 1 | Gap Analyzer | `discovery/gap_analyzer.py` | Fuseki SPARQL, Ollama embeddings |
| 2 | Class Generator | `discovery/class_generator.py` | Ollama LLM, Fuseki for parent matching |
| 3 | Relation Generator | `discovery/relation_generator.py` | Ollama LLM, existing classes |

### Tier 2: Schema Management (needed for persistence)

| # | Module | File | Depends On |
|---|---|---|---|
| 4 | Schema Manager | `schema/manager.py` | rdflib, seed ontology |
| 5 | SHACL Generator | `schema/shacl_generator.py` | rdflib, ProposedClass + relations |
| 6 | Version Manager | `schema/version_manager.py` | Fuseki named graphs API |

### Tier 3: Evaluation (needed for iteration loop)

| # | Module | File | Depends On |
|---|---|---|---|
| 7 | CQ Evaluator | `evaluation/cq_evaluator.py` | Fuseki SPARQL |
| 8 | Completeness | `evaluation/completeness.py` | Fuseki SPARQL, checkpoint reader |

### Tier 4: Human Review (needed for HITL)

| # | Module | File | Depends On |
|---|---|---|---|
| 9 | CLI Review | `review/cli.py` | Rich, proposals JSON |
| 10 | Web Dashboard | `review/web.py` | Streamlit (optional) |

---

## Module 1: GapAnalyzer — `discovery/gap_analyzer.py`

**Current state**: Partially implemented. `_load_checkpoint()` works. `_get_ontology_classes()` is a stub. `_classify_entities()` uses string matching only. `_build_gap_candidates()` groups by type but no semantic grouping.

**What to implement**:

1. **`_get_ontology_classes()`** — SPARQL query against Fuseki
   - Use `httpx.Client` to POST to `{fuseki_url}/{dataset}/sparql`
   - Query: `SELECT DISTINCT ?class ?label WHERE { ?class a owl:Class . OPTIONAL { ?class rdfs:label ?label } }`
   - Parse JSON response, return list of class labels
   - Reference: KGB `FusekiOntologyService.get_all_classes()`

2. **`_classify_entities()`** — Add embedding-based semantic matching
   - For each entity, compute embedding via `POST {ollama_url}/api/embed`
   - Compare cosine similarity against ontology class label embeddings
   - If max similarity > `similarity_threshold` → covered
   - Otherwise → uncovered, store `closest_seed_class` and `semantic_distance`

3. **`_build_gap_candidates()`** — Add embedding-based grouping
   - Group uncovered entities by semantic similarity (not just exact type)
   - Use agglomerative clustering or simple pairwise merge

---

## Module 2: ClassDefinitionGenerator — `discovery/class_generator.py`

**Current state**: Scaffold exists. `_generate_single()` returns hardcoded placeholder. `_suggest_default_properties()` returns static properties.

**What to implement**:

1. **`_generate_single()`** — LLM call via httpx
   - Build prompt with: entity_type, examples, frequency, avg_confidence
   - Include existing ontology classes for parent matching
   - Request JSON output: `{ "label", "definition", "parent_class", "properties": [...] }`
   - Parse LLM response with `json.loads()`, fallback to regex extraction
   - Validate parent_class exists in ontology
   - Reference: KGB `LLMEntityExtractor._build_prompt()`

2. **`_get_parent_candidates()`** — SPARQL query for potential parents
   - Query Fuseki for all classes with `rdfs:subClassOf` hierarchy
   - Return as `list[dict]` with URI, label, depth
   - LLM picks the best parent from this list

3. **`_call_llm()`** — Shared Ollama call
   - `POST {ollama_url}/api/generate` with `model`, `prompt`, `stream=False`
   - Parse `response["response"]`
   - Handle timeout (300s), retry on 5xx

---

## Module 3: RelationProposalGenerator — `discovery/relation_generator.py`

**Current state**: Minimal scaffold. `suggest_relations()` returns empty list.

**What to implement**:

1. **`suggest_relations()`** — LLM-based relation inference
   - Build prompt with: proposed class label/definition/examples, existing class labels
   - Ask LLM: "What relationships connect {proposed} to existing classes?"
   - Request JSON: `[{"name", "domain", "range", "description", "inverse_name", "cardinality"}]`
   - Parse and validate: domain/range must be known classes
   - Reference: KGB `OntologyRelationDef` schema

2. **`_get_existing_relations()`** — SPARQL for existing ObjectProperties
   - Query Fuseki for all `owl:ObjectProperty` with domain/range
   - Prevents proposing duplicate relations

3. **`_validate_relation()`** — Check domain/range constraints
   - Verify domain class and range class exist in ontology

---

## Module 4: OntologySchemaManager — `schema/manager.py`

**Current state**: `apply_decisions()` works. `export_owl()` and `export_updated_cqs()` raise NotImplementedError.

**What to implement**:

1. **`export_owl()`** — Build OWL graph with rdflib
   - Load seed ontology: `Graph().parse(self.seed_ontology_path)`
   - For each accepted class: add `owl:Class`, `rdfs:subClassOf`, `rdfs:label`, `rdfs:comment`
   - For each property: add `owl:DatatypeProperty` with `rdfs:domain`, `rdfs:range`
   - For each relation: add `owl:ObjectProperty` with `rdfs:domain`, `rdfs:range`
   - Serialize: `graph.serialize(output_path, format="xml")` (OWL/XML)

2. **`export_updated_cqs()`** — Generate CQs for new classes
   - For each accepted class, generate 2-3 CQs
   - Format: `"What {relation} does {class} have?"`, `"Which {class} are related to {other}?"`
   - Merge with existing CQs, save as JSON

---

## Module 5: SHACLGenerator — `schema/shacl_generator.py`

**Current state**: Basic turtle generation for properties only. No relations, no proper namespaces.

**What to implement**:

1. **`generate_shape()`** — Full SHACL with proper namespaces
   - Add `@prefix` declarations (sh, ex, xsd, owl, rdfs)
   - Generate `sh:property` for each `PropertyDef` with correct `sh:datatype`
   - Generate `sh:property` for each `RelationDef` with `sh:class` and `sh:nodeKind`
   - Handle cardinality: `sh:minCount`, `sh:maxCount` from `cardinality` string
   - Return complete valid Turtle

2. **`generate_all_shapes()`** — Batch generation
   - Accept `list[ProposedClass]`, return combined Turtle document
   - Include proper prefix header once

3. **`validate_with_pyshacl()`** — Validate data against shapes
   - Use `pyshacl.validate(data_graph, shacl_graph=shapes_graph)`
   - Return `(conforms, results_graph, results_text)`

---

## Module 6: OntologyVersionManager — `schema/version_manager.py`

**Current state**: Creates in-memory version records. All Fuseki operations are stubs.

**What to implement**:

1. **`create_version()`** — Create named graph in Fuseki
   - `PUT {fuseki_url}/{dataset}/data?graph={graph_uri}` with Turtle payload
   - Graph URI format: `urn:ontology:staging:v{N}`

2. **`compute_diff()`** — SPARQL-based diff
   - Query triples in `from_version` graph not in `to_version` (removed)
   - Query triples in `to_version` graph not in `from_version` (added)
   - Populate `OntologyDiff` fields

3. **`promote_staging_to_main()`** — Graph copy
   - SPARQL UPDATE: `COPY GRAPH <staging> TO GRAPH <main>`
   - Or: read staging, write to main dataset

4. **`create_snapshot()`** — Snapshot main graph
   - `COPY GRAPH <main> TO GRAPH <snapshot-{timestamp}>`

---

## Module 7: CQEvaluator — `evaluation/cq_evaluator.py`

**Current state**: Returns placeholder dict.

**What to implement**:

1. **`evaluate_coverage()`** — Load CQs + test each
   - Load CQ JSON: `[{"id", "question", "sparql_pattern"}]`
   - For each CQ with SPARQL pattern: execute against Fuseki
   - For CQs without SPARQL: use LLM to construct SPARQL query
   - Score: answerable if query returns ≥1 result
   - Return per-CQ results + aggregate coverage_pct

2. **`_cq_to_sparql()`** — Convert natural language CQ to SPARQL
   - LLM prompt: "Given ontology classes [...], convert this CQ to SPARQL: {cq}"
   - Validate syntax, execute, return result count

---

## Module 8: CompletenessAnalyzer — `evaluation/completeness.py`

**Current state**: Returns placeholder dict.

**What to implement**:

1. **`measure_schema_coverage()`** — Entity-to-class matching
   - Load checkpoint (reuse GapAnalyzer._load_checkpoint pattern)
   - Get ontology classes from Fuseki
   - For each extracted entity type: check if ontology has a matching class
   - Use embedding similarity as fallback (like GapAnalyzer)
   - Return: covered_entities, total_entities, coverage_pct, gap breakdown

---

## Module 9: CLI Review — `review/cli.py`

**Current state**: Has `review` and `status` commands. Review command is a stub.

**What to implement**:

1. **`review` command** — Interactive Rich loop
   - Load proposals JSON
   - For each proposal, display with Rich Panel:
     - Label, definition, parent, examples, properties
   - Prompt for decision: [a]ccept / [r]eject / [s]kip / [e]dit
   - For accept/reject: prompt for rationale
   - For edit: prompt for changes (label, definition, parent)
   - Save decisions to JSON file incrementally

2. **`export` command** — Export decisions summary
   - Read decisions JSON, produce summary table

---

## Module 10: Web Dashboard — `review/web.py` (Optional)

**Current state**: Empty placeholder.

**What to implement**: Streamlit app with:
- Sidebar: filter by status
- Main: proposal cards with accept/reject buttons
- Summary stats dashboard
- CQ coverage chart

---

## Testing Strategy

Each stub implementation should have corresponding tests in `tests/`.
Existing test files: `test_gap_analyzer.py`, `test_class_generator.py`,
`test_relation_generator.py`, `test_manager.py`, `test_shacl_generator.py`,
`test_version_manager.py`, `test_cq_evaluator.py`, `test_completeness.py`.

Tests should:
- Mock httpx calls (no real Fuseki/Ollama in unit tests)
- Test happy path + error cases
- Verify data model construction
- Check SPARQL query format (string assertions)

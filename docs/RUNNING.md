# Running the OntologyExtender: Standalone & Coupled Mode

> Complete guide for running the system in either mode.

## Quick Reference

| | **Standalone Mode** | **Coupled Mode** |
|---|---|---|
| **What it does** | Documents → Ontology | Documents → Ontology ↔ Knowledge Graph (iterative) |
| **Required services** | Ollama, Qdrant | Ollama, Qdrant, Fuseki, Neo4j, KGB |
| **External repo needed?** | No | Yes — KnowledgeGraphBuilder |
| **Seed ontology** | Optional | Recommended |
| **Neo4j** | Optional (legal enrichment only) | Required |
| **Gap analysis** | Skipped | Active — drives targeted class proposals |
| **Best for** | Quick ontology draft, benchmarking, new domains | Production, iterative refinement, KG-coupled domains |

---

## 1. Prerequisites (Both Modes)

### 1.1 Clone & install

```bash
git clone git@github.com:DataScienceLabFHSWF/OntologyExtender.git
cd OntologyExtender
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 1.2 Core services

**Ollama** (LLM inference):
```bash
# Option A: Docker (recommended — uses GPU)
docker compose up -d ollama-ontology-extender

# Option B: Native Ollama on custom port
OLLAMA_HOST=0.0.0.0:18135 ollama serve

# Pull required models
ollama pull qwen3-next          # 79.7B — main model
ollama pull llama3.2:3b          # 3B — fast baseline
ollama pull qwen3-embedding      # embedding model
```

**Qdrant** (document store):
```bash
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest
```

### 1.3 Ingest documents into Qdrant

Before running either mode, your domain documents must be chunked and embedded in Qdrant:

```bash
# Example: ingest PDFs from a directory
python scripts/ingest_documents.py \
  --input-dir /path/to/domain/documents/ \
  --collection kgbuilder \
  --chunk-size 512 \
  --overlap 64
```

> **Note**: If using the KnowledgeGraphBuilder (coupled mode), it handles document ingestion into Qdrant as part of its pipeline. You don't need to ingest separately.

### 1.4 Environment configuration

Create a `.env` file in the project root:

```bash
# === Required ===
HITL_OLLAMA_URL=http://localhost:18135
HITL_OLLAMA_MODEL=qwen3-next
HITL_QDRANT_URL=http://localhost:6333
HITL_QDRANT_COLLECTION=kgbuilder

# === Domain (set for your domain, empty = auto-detect) ===
HITL_DOMAIN_NAME="nuclear decommissioning"
# HITL_DOMAIN_NAME=""   # leave empty for domain-agnostic (e.g. benchmarking)

# === Optional: Seed ontology ===
HITL_SEED_ONTOLOGY_PATH=data/seed_ontology/plan-ontology-v1.0.owl
# Comment out or set to "" if starting from scratch

# === Optional: Fuseki ===
HITL_FUSEKI_URL=http://localhost:3030
HITL_FUSEKI_DATASET=kgbuilder
HITL_FUSEKI_PASSWORD=admin

# === Optional: Neo4j (required for coupled mode) ===
HITL_NEO4J_URI=bolt://localhost:7687
HITL_NEO4J_HTTP_URL=http://localhost:7474
HITL_NEO4J_USERNAME=neo4j
HITL_NEO4J_PASSWORD=changeme

# === Optional: Legal enrichment ===
HITL_LEGAL_ENRICHMENT_ENABLED=true  # Set false if no legal KG

# === Optional: W&B tracking ===
HITL_WANDB_ENABLED=true
HITL_WANDB_PROJECT=ontology-hitl
HITL_WANDB_API_KEY=your-key-here

# === Module flags (all default to true) ===
# HITL_ENTITY_LINKING_ENABLED=true      # Module B: external ontology linking
# HITL_EMBEDDING_ADVISOR_ENABLED=true   # Module C: embedding-based hierarchy
# HITL_ENSEMBLE_ENABLED=true            # Module E: ensemble strategy
# HITL_FEEDBACK_LEARNING_ENABLED=true   # Module F: learning from corrections
# HITL_PROVENANCE_ENABLED=true          # Module D: evidence tracking
```

---

## 2. Standalone Mode

Standalone mode generates an ontology directly from documents in Qdrant. No external knowledge graph involved.

### 2.1 Architecture

```
Documents (Qdrant) ──► Multi-Agent Debate (7 Ont-101 phases) ──► OWL + SHACL + CQs
                              │
                              ├── Optional: Fuseki seed ontology introspection
                              ├── Optional: Neo4j legal enrichment
                              └── Optional: Entity linking to BFO/DOLCE/Wikidata
```

### 2.2 Required services

| Service | Required? | Purpose |
|---------|-----------|---------|
| Ollama | **Yes** | LLM inference |
| Qdrant | **Yes** | Document chunks |
| Fuseki | Optional | Seed ontology queries |
| Neo4j | Optional | Legal enrichment only |

### 2.3 Run

```bash
source .venv/bin/activate

# Basic run (auto-detect domain from documents)
python -m ontology_hitl.core.loop_orchestrator \
  --mode standalone \
  --max-iterations 4

# With explicit domain and seed ontology
python -m ontology_hitl.core.loop_orchestrator \
  --mode standalone \
  --max-iterations 6 \
  --seed-ontology data/seed_ontology/plan-ontology-v1.0.owl \
  --experiment-name "nuclear-decom-standalone"

# With auto-review (no HITL pauses — fully automated)
python -m ontology_hitl.core.loop_orchestrator \
  --mode standalone \
  --auto-review \
  --max-iterations 4
```

### 2.4 Outputs

After each iteration, artefacts are saved to `data/iterations/{version}/`:

| File | Content |
|------|---------|
| `ontology_{version}.owl` | OWL ontology (classes, properties, axioms) |
| `shapes_{version}.ttl` | SHACL validation shapes |
| `cqs_{version}.json` | Competency questions |
| `mapping_{version}.yarrrml.yml` | YARRRML data mappings |
| `convergence_report.json` | Per-iteration metrics, convergence status |
| `provenance_{version}.json` | Evidence trail linking every class to source passages |
| `debate_log_{version}.json` | Full debate transcripts |

### 2.5 When to use standalone mode

- **New domain exploration**: No existing ontology or KG
- **Benchmarking**: OntoURL, model comparison experiments
- **Quick prototyping**: Get a draft ontology fast
- **Domains without a knowledge graph**: Just documents

---

## 3. Coupled Mode

Coupled mode integrates with the **KnowledgeGraphBuilder** (KGB) — a separate repository/module that extracts entities and relations from documents and populates a Neo4j knowledge graph.

### 3.1 Architecture

```
    ┌──────────────────────────────────────────────────────────┐
    │                  Iteration Loop                          │
    │                                                          │
    │  ┌─────────────┐    ┌──────────────────┐                │
    │  │    KGB       │    │ OntologyExtender │                │
    │  │  (separate   │◄──►│  (this project)  │                │
    │  │   module)    │    │                  │                │
    │  └──────┬───────┘    └────────┬─────────┘                │
    │         │                     │                          │
    │    Neo4j (ABox)         Fuseki (TBox)                    │
    │    entities +           classes +                        │
    │    relations            properties                      │
    │         │                     │                          │
    │         └─────────┬───────────┘                          │
    │                   │                                      │
    │           Gap Analyzer                                   │
    │     "What's in Neo4j but                                │
    │      not in the ontology?"                              │
    │                   │                                      │
    │         New class proposals                              │
    │         fed back to debate                               │
    └──────────────────────────────────────────────────────────┘
```

### 3.2 Required services

| Service | Required? | Purpose |
|---------|-----------|---------|
| Ollama | **Yes** | LLM inference |
| Qdrant | **Yes** | Document chunks |
| Fuseki | **Yes** | Ontology (TBox) storage, SPARQL queries |
| Neo4j | **Yes** | Knowledge graph (ABox), legal enrichment |
| KGB | **Yes** | Entity/relation extraction, Neo4j population |

### 3.3 External dependency: KnowledgeGraphBuilder

The coupled mode requires the **KnowledgeGraphBuilder** module, which is maintained as a separate repository.

```bash
# Clone the KGB repo (internal — contact the team for access)
git clone git@github.com:DataScienceLabFHSWF/KnowledgeGraphBuilder.git
cd KnowledgeGraphBuilder
pip install -e .
```

The KGB is responsible for:
1. **Document ingestion** → Qdrant (chunking, embedding)
2. **Entity extraction** → NER on document chunks
3. **Relation extraction** → linking entities
4. **Triple generation** → RDF triples from extracted relations
5. **Neo4j population** → loading triples into the knowledge graph
6. **Extraction checkpoint** → `extraction_checkpoint.json` consumed by the gap analyzer

### 3.4 Setup Neo4j + Fuseki

```bash
# Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/changeme \
  -v neo4j_data:/data \
  neo4j:5-community

# Fuseki (staging instance for OntologyExtender)
docker compose up -d fuseki-staging

# Upload seed ontology to Fuseki
curl -X POST "http://localhost:3031/kgbuilder-staging/data" \
  -H "Content-Type: application/rdf+xml" \
  --data-binary @data/seed_ontology/plan-ontology-v1.0.owl
```

### 3.5 Run coupled mode

```bash
source .venv/bin/activate

# Step 1: Run KGB to populate Neo4j (in KGB repo)
cd /path/to/KnowledgeGraphBuilder
python -m kgbuilder.extract \
  --documents /path/to/documents/ \
  --output extraction_checkpoint.json

# Step 2: Run OntologyExtender in coupled mode
cd /path/to/OntologyExtender
python -m ontology_hitl.core.loop_orchestrator \
  --mode coupled \
  --checkpoint /path/to/extraction_checkpoint.json \
  --max-iterations 6 \
  --experiment-name "nuclear-decom-coupled"
```

### 3.6 What happens in coupled mode

For each iteration:

1. **Plan**: Orchestrator checks if KGB re-extraction is needed (iteration > 1)
2. **Gap Analysis**: `OntologyGapAnalyzer` compares extraction checkpoint entities against Fuseki ontology classes
   - Exact label matching
   - Semantic similarity via Ollama embeddings (threshold ≥ 0.65)
   - Uncovered entity types become gap candidates
3. **Class Proposals**: `ClassDefinitionGenerator` produces `ProposedClass` objects from gap candidates (via LLM)
4. **Relation Proposals**: `RelationProposalGenerator` suggests properties between new and existing classes
5. **7-Phase Debate**: Standard Ont-101 pipeline, enriched with gap-driven proposals
6. **Export**: Updated OWL uploaded to Fuseki
7. **KGB Re-extraction** (if iteration > 1): KGB re-runs with updated ontology schema → better extraction
8. **Convergence Check**: Entity coverage improvement < 2%? CQ answerability ≥ 80%?

### 3.7 When to use coupled mode

- **Production deployment**: Full pipeline with iterative refinement
- **Large document corpora**: Where a KG provides structured access
- **Domains with complex entity relationships**: KG captures what the ontology formalizes
- **Legal/regulatory domains**: Neo4j + LawGraph for legal enrichment

---

## 4. Running Benchmarks

Benchmarks run in standalone mode (no KG needed) to evaluate LLM ontology capabilities.

### 4.1 OntoURL benchmark

```bash
source .venv/bin/activate

# Quick test (50 examples, small model)
python scripts/run_ontourl_benchmark.py \
  --model llama3.2:3b \
  --max-examples 50

# Full run (all 15 tasks, one model)
python scripts/run_ontourl_benchmark.py \
  --model qwen3-next \
  --resume

# Full sweep (3 models × 6 strategies × 15 tasks)
# Estimated: 3-5 days on 2×H200
bash scripts/run_full_ontourl.sh
```

Results saved to `results/ontourl/`, tracked in W&B.

### 4.2 Model comparison (strategy matrix)

```bash
source .venv/bin/activate

# Small model experiments
python scripts/run_model_comparison.py \
  --experiments experiments/small_model_experiments.json \
  --output results/small_model_results.json

# Large model experiments
python scripts/run_model_comparison.py \
  --experiments experiments/large_model_experiments.json \
  --output results/large_model_results.json
```

### 4.3 LLM4ACOE / baseline comparison

```bash
source .venv/bin/activate

# Initialize (generates config, shows setup instructions)
python scripts/run_benchmark.py init

# Clone baseline repos (manual step)
mkdir -p /tmp/baselines
cd /tmp/baselines
git clone https://github.com/... Agent-OM
git clone https://github.com/... LLM4ACOE
git clone https://github.com/... NLP-W2V

# Run comparison
cd /path/to/OntologyExtender
python scripts/run_benchmark.py run --config benchmark_config.json
python scripts/run_benchmark.py evaluate
python scripts/run_benchmark.py report
```

---

## 5. Monitoring & Results

### W&B dashboard

All runs log to [wandb.ai/dsfhswf/ontology-hitl](https://wandb.ai/dsfhswf/ontology-hitl):
- Per-iteration metrics (coverage, quality, debate outcomes)
- OntoURL task accuracy per model/strategy
- Model comparison matrices

### Log files

```
logs/
├── ontourl/           # OntoURL benchmark logs per model
├── experiments/       # Model comparison experiment logs
└── ontourl_*.log      # nohup run outputs
```

### Result files

```
results/
├── ontourl/                     # OntoURL per-task results (JSON)
├── small_model_results.json     # Strategy matrix results
├── large_model_results.json
└── comparison_report.md         # Generated comparison report
```

### Iteration artefacts

```
data/iterations/
├── v1/
│   ├── ontology_v1.owl
│   ├── shapes_v1.ttl
│   ├── cqs_v1.json
│   ├── mapping_v1.yarrrml.yml
│   └── provenance_v1.json
├── v2/
│   └── ...
└── convergence_report.json
```

---

## 6. Troubleshooting

| Problem | Solution |
|---------|----------|
| `ConnectionError: Ollama` | Check `docker ps` for ollama container, verify port 18135 |
| `Model not found` | Run `ollama pull qwen3-next` |
| Qdrant empty collection | Run document ingestion first |
| Fuseki 404 | Create dataset: `curl -X POST localhost:3031/$/datasets -d "dbName=kgbuilder-staging&dbType=tdb2"` |
| Neo4j auth error | Check `HITL_NEO4J_PASSWORD` matches Docker `-e NEO4J_AUTH=neo4j/...` |
| Tests hang on `test_class_generator` | Run with `pytest -m "not slow"` — those tests make real LLM calls |
| W&B not logging | Set `HITL_WANDB_API_KEY` or `HITL_WANDB_ENABLED=false` |

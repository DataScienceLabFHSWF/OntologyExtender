# Interface Contract with KnowledgeGraphBuilder

## Overview

OntologyExtender operates in two modes:

- **Standalone** — uses Qdrant documents directly, no KGB dependency
- **Coupled** — exchanges artefacts with KGB for iterative co-evolution

In both modes, the multi-agent system (OntologyEngineer, DomainExpert, Critic)
runs the Ont-101 seven-phase pipeline internally. The interface contract below
defines how artefacts flow between the two systems.

## Inputs FROM KGB (Coupled Mode)

| Artifact | Path | Description |
|----------|------|-------------|
| Extraction checkpoint | `output/extraction_checkpoint.json` | All extracted entities/relations |
| KG metrics | `output/kg_metrics.json` | Entity counts, coverage stats |

### Checkpoint JSON Format

```json
{
  "pipeline_run_id": "baseline_33docs_20260209_0929",
  "timestamp": "2026-02-09T09:29:28",
  "ontology_version": "plan-ontology-v1.0",
  "entities": [
    {
      "id": "ent_xxxxx",
      "label": "Entity Name",
      "entity_type": "TypeName",
      "confidence": 0.87,
      "evidence": [
        {
          "chunk_id": "chunk_042",
          "document": "doc_15.pdf",
          "text_snippet": "..."
        }
      ]
    }
  ],
  "relations": [...],
  "metrics": {
    "total_entities": 450,
    "unique_entity_types": 35,
    "avg_confidence": 0.72
  }
}
```

## Inputs FROM Qdrant (Both Modes)

| Artifact | Source | Description |
|----------|--------|-------------|
| Document chunks | `QdrantDocumentSource.fetch_chunks()` | Top-k relevant passages per query |
| Entity summaries | `QdrantDocumentSource.extract_entities()` | Entity type frequencies from collection |

The DomainExpert agent receives document context from Qdrant to ground
its reviews in actual evidence. The `AgentTeam.set_document_context()` method
updates this context at each iteration.

## Outputs TO KGB

| Artifact | KGB CLI Flag | Description |
|----------|-------------|-------------|
| Extended ontology OWL | `--ontology-path` | New ontology with accepted classes |
| Updated CQ JSON | `--questions` | New/refined competency questions |
| SHACL shapes | (optional) | Validation constraints for the extended ontology |
| YARRRML mappings | (optional) | RDF mapping rules for re-extraction |

### Usage

```bash
# In KnowledgeGraphBuilder repo:
python scripts/full_kg_pipeline.py \
  --ontology-path ../OntologyExtender/data/exports/ontology_v2.0.owl \
  --questions ../OntologyExtender/data/exports/cq_v2.0.json \
  --max-iterations 1
```

## Internal Data Flow

```
Qdrant ──▸ QdrantDocumentSource ──▸ document_context ──▸ DomainExpert
                                                          │
KGB checkpoint ──▸ gap_analyzer ──▸ seed data ──▸ Ont101Pipeline
                                                          │
                                    ┌─────────────────────┘
                                    ▼
                              AgentTeam (7 debates)
                                    │
                              ┌─────┴─────┐
                              ▼           ▼
                         Ont101Iteration  AgentQuestions
                              │           │
                              ▼           ▼
                         OWL export    HITL review
                              │
                              ▼
                         KGB re-extraction
```

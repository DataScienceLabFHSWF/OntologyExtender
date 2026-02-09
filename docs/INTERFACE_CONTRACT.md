# Interface Contract with KnowledgeGraphBuilder

## Inputs FROM KGB

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

## Outputs TO KGB

| Artifact | KGB CLI Flag | Description |
|----------|-------------|-------------|
| Extended ontology OWL | `--ontology-path` | New ontology with accepted classes |
| Updated CQ JSON | `--questions` | New/refined competency questions |

### Usage

```bash
python scripts/full_kg_pipeline.py \
  --ontology-path ../ontology-hitl/data/exports/ontology_v2.0.owl \
  --questions ../ontology-hitl/data/exports/cq_v2.0.json \
  --max-iterations 1
```
